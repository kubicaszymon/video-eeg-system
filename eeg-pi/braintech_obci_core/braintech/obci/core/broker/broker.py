# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""The Broker module defines classes which act as message proxy and/or router between peers."""
import asyncio
import json
import time
import logging
import threading
import urllib.parse
import uuid
import collections
import tempfile

from typing import Optional, Iterable

import zmq
import zmq.asyncio
from asyncio.streams import IncompleteReadError, LimitOverrunError

from braintech.obci.core.control.common.net import filter_local, filter_not_local
from braintech.obci.core.broker import messages
from braintech.obci.core.broker.base_peer import PeerCapabilities
from braintech.obci.core.broker.message_handler_mixin import register_message_handler, subscribe_message_handler

from . import (TCP_MAGIC_BYTES_OBCI,
               BROKER_TCP_IP_DEFAULT_PORT,
               DEFAULT_HEARTBEAT_DELAY,
               HEARTBEAT_ERROR_INTERVAL,
               HEARTBEAT_WARNING_INTERVAL,
               HEARTBEAT_JITTER_WARNING,
               ObciException)
from .base_peer import BasePeer
from .url_utils_mixin import UrlUtilsMixin
from ..utils.asyncio import wait_for_condition

__all__ = ('Broker',)


class PeerInfo:

    def __init__(self, peer_id: str, rep_urls: Iterable[str]) -> None:
        """
        Used by Broker to hold information about connected peer.

        :param peer_id: unique peer ID
        :param rep_urls: URLs of peer's REP socket
        """
        super().__init__()
        self._id = peer_id
        self.rep_urls = list(rep_urls)

        # heartbeats hold approximately 1 second of heartbeat timestamps
        self.heartbeats = collections.deque(maxlen=int(1.0 / DEFAULT_HEARTBEAT_DELAY))
        self.hb_error = False
        self.hb_warning = False
        self.hb_jitter_warning = False

    @property
    def id(self) -> str:
        """Read only peer ID."""
        return self._id

    def find_rep_url(self, peer_info: 'PeerInfo') -> str:
        # TODO: better logic
        if '0.0.0.0' in self.rep_urls:
            raise ObciException("not possible")

        if filter_local(peer_info.rep_urls):
            return filter_local(self.rep_urls)[0]
        else:
            return filter_not_local(self.rep_urls)[0]


class MsgProxy(UrlUtilsMixin):

    def __init__(self,
                 xpub_urls: Iterable[str],
                 xsub_urls: Iterable[str],
                 io_threads: int = 1,
                 hwm: int = 1000) -> None:
        """
        Message proxy routes messages from multiple publishers to multiple subscribers.

        Message proxy is an integral part of Broker.

        :class:`MsgProxy` opens an XSUB socket, an XPUB socket, and binds them to
        specified IP addresses and ports. Then, all peers connect to the proxy,
        instead of to each other. By using such pattern it becomes trivial to
        add more subscribers or publishers.

        :param xpub_urls: list of URLs to bind XPUB socket to
        :param xsub_urls: list of URLs to bind XSUB socket to
        :param io_threads: size of the ZMQ threads pool to handle I/O operations
        :param hwm: High Water Mark set on all ZMQ sockets
        """
        super().__init__()

        self.ready = False
        self.xpub_urls = set()
        self.xsub_urls = set()

        self._ctx = zmq.Context(io_threads=io_threads)
        self._hwm = hwm

        self._debug = False

        self._logger = logging.getLogger('MsgProxy')

        self._thread = threading.Thread(target=self.__run,
                                        name='MsgProxy',
                                        args=(xpub_urls, xsub_urls))
        self._thread.daemon = True
        self._thread.start()

    def shutdown(self) -> None:
        """Shutdown message proxy. Release all associated resources."""
        self._ctx.term()
        self._thread.join()

    def __run(self,
              xpub_urls_to_bind: Iterable[str],
              xsub_urls_to_bind: Iterable[str]
              ) -> None:
        xpub = self._ctx.socket(zmq.XPUB)
        xsub = self._ctx.socket(zmq.XSUB)

        xpub.set_hwm(self._hwm)
        xsub.set_hwm(self._hwm)

        xpub.set(zmq.LINGER, 0)
        xsub.set(zmq.LINGER, 0)

        self.xpub_urls = self._bind_to_urls(xpub, xpub_urls_to_bind)
        self.xsub_urls = self._bind_to_urls(xsub, xsub_urls_to_bind)

        self._logger.info("\nMsgProxy listening on:\nXPUB: {}\nXSUB: {}\n"
                          .format(', '.join(self.xpub_urls),
                                  ', '.join(self.xsub_urls)))

        self.ready = True

        try:
            if self._debug:
                poller = zmq.Poller()
                poller.register(xpub, zmq.POLLIN)
                poller.register(xsub, zmq.POLLIN)
                while True:
                    events = dict(poller.poll(1000))
                    if xpub in events:
                        message = xpub.recv_multipart()
                        self._logger.debug("[BROKER_PROXY] subscription message: %s", message)
                        xsub.send_multipart(message)
                    if xsub in events:
                        message = xsub.recv_multipart()
                        self._logger.debug("[BROKER_PROXY] publishing message: %s", message)
                        xpub.send_multipart(message)
            else:
                zmq.proxy(xsub, xpub)
        except zmq.ContextTerminated:
            self.ready = False
            xsub.close(linger=0)
            xpub.close(linger=0)
        finally:
            self.ready = False


class Broker(BasePeer):
    """Base class for Broker. It is started once per experiment. Every Peer connects to Broker on initialization."""

    def __init__(self,
                 broker_ip_address: Optional[str] = None,
                 rep_urls: Optional[Iterable[str]] = None,
                 xpub_urls: Optional[Iterable[str]] = None,
                 xsub_urls: Optional[Iterable[str]] = None,
                 asyncio_loop: Optional[zmq.asyncio.ZMQEventLoop] = None,
                 zmq_context: Optional[zmq.asyncio.Context] = None,
                 zmq_io_threads: int = 1,
                 hwm: int = 1000,
                 msg_proxy_io_threads: int = 1,
                 msg_proxy_hwm: int = 1000) -> None:
        """
        Broker is as essential component of BCI-Framework experiment.

        It consists of REP socket, XPUB/XSUB message proxy and internal peer
        (with ID 'Broker'). Every peer connects to broker on initialization and registers.
        Broker also acts as a message proxy and/or router between peers.

        Broker created using default parameters is reachable only from
        localhost. By default Broker binds to all sockets to ``127.0.0.1``.

        When ``broker_ip_address`` is set to string containing ``ip_address:port``
        Broker starts server on specified `broker_ip_address`. If
        ``broker_ip_address`` is ``None`` it will be assumed as ``127.0.0.1:23821``.
        If port is not specified 23821 is assumed. Usually you may want to pass
        ``0.0.0.0`` to listen on all interfaces on default port.

        When ``xpub_urls`` and/or ``xsub_urls`` parameters are set to ``None`` Broker
        binds them only locally to ``tcp://127.0.0.1:*``.

        :param rep_urls: list of URLs to bind REP socket to
        :param xpub_urls: list of URLs to bind message proxy XPUB socket to
        :param xsub_urls: list of URLs to bind message proxy XSUB socket to
        :param asyncio_loop: existing message loop to use or `None` if new message loop is requested
        :param zmq_context: existing ZMQ asyncio context or `None` if new context is requested
        :param zmq_io_threads: number of ZMQ I/O threads to use in broker
        :param hwm: ZMQ High Water Mark for broker
        :param msg_proxy_io_threads: number of ZMQ I/O threads to use in message proxy
        :param msg_proxy_hwm: ZMQ High Water Mark for message proxy
        """
        broker_name = self.__class__.__name__

        self._broker_ip_address = '127.0.0.1:{}'.format(BROKER_TCP_IP_DEFAULT_PORT) \
            if broker_ip_address is None \
            else str(broker_ip_address)  # type: str

        self._rep_urls = {'tcp://127.0.0.1:*'} if rep_urls is None else set(rep_urls)
        self._xpub_urls = {'tcp://127.0.0.1:*'} if xpub_urls is None else set(xpub_urls)
        self._xsub_urls = {'tcp://127.0.0.1:*'} if xsub_urls is None else set(xsub_urls)
        if self.capabilities.has_ipc():
            temp_url_id = uuid.uuid1()
            tempfolder = tempfile.gettempdir()

            rep_ipc_id = 'broker_rep_{}.ipc'.format(temp_url_id)

            self._rep_ipc = 'ipc://{}/{}'.format(tempfolder, rep_ipc_id)
            self._xsub_ipc = 'ipc://{}/broker_xsub_{}.ipc'.format(tempfolder, temp_url_id)
            self._xpub_ipc = 'ipc://{}/broker_xpub_{}.ipc'.format(tempfolder, temp_url_id)
            self._rep_urls.add(self._rep_ipc)
            self._xpub_urls.add(self._xpub_ipc)
            self._xsub_urls.add(self._xsub_ipc)

        self._peers = {}

        # self._query_handlers are stored as follows:
        # {
        #   'msg_type_1': set([peer_1_info, peer_2_info]),
        #   'msg_type_2': set([peer_1_info, peer_2_info])
        # }
        self._query_handlers = {}

        self._log_messages = True

        # run XPUB & XSUB proxy in different thread
        self._msg_proxy = MsgProxy(self._xpub_urls,
                                   self._xsub_urls,
                                   io_threads=msg_proxy_io_threads,
                                   hwm=msg_proxy_hwm)

        self.heartbeat_error_interval = HEARTBEAT_ERROR_INTERVAL
        self.heartbeat_warning_interval = HEARTBEAT_WARNING_INTERVAL

        super().__init__(peer_id=broker_name,
                         peer_name=broker_name,
                         asyncio_loop=asyncio_loop,
                         zmq_context=zmq_context,
                         zmq_io_threads=zmq_io_threads,
                         hwm=hwm)

        self.register_message_handler(messages.ConfigServerUrlQuery, self._handle_config_server_url_query)

    @property
    def broker_ip(self) -> str:
        """Broker ipv4 address with port, which can be used by peers for broker urls autodiscovery."""
        return self._broker_ip_address

    def _add_peer(self, peer_id: str, **kwargs) -> PeerInfo:
        """
        Add peer to a internal list of peers.

        :param peer_id: peer ID
        :param kwargs: PeerInfo parameters
        :return: newly created PeerInfo object
        """
        pi = PeerInfo(peer_id, **kwargs)
        self._peers[pi.id] = pi
        return pi

    def _remove_peer(self, peer_id: str) -> PeerInfo:
        """
        Remove peer from a internal list of peers.

        :param peer_id: peer ID
        :return: PeerInfo object for deleted peer or None if peer had not existed
        """
        if peer_id in self._peers:
            pi = self._peers[peer_id]
            self._unregister_peer_from_query_handler(pi)
            del self._peers[peer_id]
        else:
            pi = None
        return pi

    def _handle_config_server_url_query(self, msg):
        # TODO: when doing messaging refactor make config server use normal query and delete this method
        try:
            cs = self._peers['config_server']
        except KeyError:  # 37578
            return messages.InternalError(data='No peer')
        query_pi = self._peers[msg.sender]
        urls = cs.find_rep_url(query_pi)
        return messages.ConfigServerUrlAnswer(url=urls)

    @register_message_handler(messages.PeerUrlQuery)
    def _handle_peer_url_query(self, msg):
        target_peer_info = self._peers[msg.target]
        sender_info = self._peers[msg.sender_id]
        target_url = target_peer_info.find_rep_url(sender_info)
        return messages.PeerUrlQuery(target=msg.target, target_url=target_url, sender_id=self.id)

    async def _establish_connections(self) -> None:
        # wait until MsgProxy is ready
        await wait_for_condition(lambda: self._msg_proxy.ready,
                                 timeout=10.0,
                                 sleep_duration=0.05,
                                 name='wait until MsgProxy is ready')

        self._xpub_urls = self._msg_proxy.xpub_urls
        self._xsub_urls = self._msg_proxy.xsub_urls
        self._rep_urls = self._bind_to_urls(self._rep, self._rep_urls)

        self._logger.info("Broker: URL lists after postprocessing: \nREP: {}\nXPUB: {}\nXSUB: {}\n"
                          .format(', '.join(self._rep_urls),
                                  ', '.join(self._xpub_urls),
                                  ', '.join(self._xsub_urls)))

        host_ip, host_port = self._split_ipv4_address(self._broker_ip_address, BROKER_TCP_IP_DEFAULT_PORT)

        self._logger.info('Starting broker TCP/IP server at: %s:%s', host_ip, host_port)
        coro = asyncio.start_server(self._handle_tcp_ip_request,
                                    host=host_ip,
                                    port=host_port,
                                    loop=self._loop)

        self.create_task(coro)

        ip = '127.0.0.1'
        xsub_url = 'tcp://{}:{}'.format(ip, self._find_port_for_ip(self._xsub_urls, ip))
        xpub_url = 'tcp://{}:{}'.format(ip, self._find_port_for_ip(self._xpub_urls, ip))
        self._pub.connect(xsub_url)  # connect PUB to XSUB
        self._sub.connect(xpub_url)  # connect SUB to XPUB

    async def _connections_established(self) -> None:
        await super()._connections_established()
        self.create_task(self._monitor_heartbeats())

    async def _handle_tcp_ip_request(self,
                                     reader: asyncio.StreamReader,
                                     writer: asyncio.StreamWriter
                                     ) -> None:

        peer_address = writer.get_extra_info('peername')  # type: Tuple[str, int]
        broker_address = writer.get_extra_info('sockname')  # type: Tuple[str, int]

        # If TCP/IP server is listening on 0.0.0.0 and host has two IPs
        # (lets assume 127.0.0.1 and 10.0.0.10) than peer_address
        # depends on what URL peer connected to:
        #  - if peer connected to 127.0.0.1, then peer_address == 127.0.0.1
        #  - if peer connected to 10.0.0.10, then peer_address == 10.0.0.10
        # That means if peer connects to broker using 127.0.0.1, it will be
        # available only to local peers (its TCP/IP address will be detected
        # as 127.0.0.1).
        #
        # Always Remember:
        #
        #     Peer should use external IP address when connecting to Broker,
        #     otherwise it will not be available to peers running on different
        #     hosts.
        #

        self._logger.debug('Broker received TCP/IP request: peer_address: %s, broker_address %s',
                           peer_address, broker_address)
        try:
            data = await asyncio.wait_for(
                reader.readuntil(separator=b"\n"),
                timeout=1.0)
            data = data[:-1]
        except IncompleteReadError as error:
            data = error.partial
        except LimitOverrunError:
            self._logger.warning('Peer %s send too much data!', peer_address)
            return

        if not data.startswith(TCP_MAGIC_BYTES_OBCI):
            self._logger.warning('Peer %s send bad request: %s', peer_address, data)
            return
        client_capabilities = PeerCapabilities(data[len(TCP_MAGIC_BYTES_OBCI):])

        # try do determine Broker's REP port number as seen from Peer
        rep_port = self._find_port_for_ip(self._rep_urls, broker_address[0])

        if rep_port is None:
            msg = ('Could not determine broker REP port number for peer:\n'
                   'peer_address: {}\n'
                   'broker_address: {}\n'
                   'Broker TCP/IP server listening at: {}\n'
                   'Broker REP URLs are: {}\n') \
                .format(peer_address,
                        broker_address,
                        self._broker_ip_address,
                        self._rep_urls)
            self._logger.fatal(msg)
            raise ObciException(msg)
        data = {'broker_url': 'tcp://{}:{}'.format(broker_address[0], rep_port),
                'pub_urls': ['tcp://{}:*'.format(peer_address[0]), ],
                'rep_urls': ['tcp://{}:*'.format(peer_address[0]), ],
                }

        if broker_address[0] == peer_address[0]:
            if self.capabilities.has_ipc() and client_capabilities.has_ipc():
                data['broker_url'] = self._rep_ipc
                data['pub_urls'].append('ipc://{}/{}.ipc'.format(tempfile.gettempdir(), uuid.uuid4()))
                data['rep_urls'].append('ipc://{}/{}.ipc'.format(tempfile.gettempdir(), uuid.uuid4()))
            else:
                local = '127.0.0.1'
                data['broker_url'] = 'tcp://{}:{}'.format(local, rep_port)
                data['pub_urls'].append('tcp://{}:*'.format(local))
                data['rep_urls'].append('tcp://{}:*'.format(local))
        self._logger.debug('Broker TCP/IP answer: %s', data)

        writer.write(json.dumps(data, ensure_ascii=True, separators=(',', ':')).encode('ascii'))
        await asyncio.wait_for(writer.drain(), timeout=1.0)
        writer.close()

    @register_message_handler(messages.BrokerHelloMsg)
    async def _handle_hello(self, msg: messages.BrokerHelloMsg) -> messages.BaseMessage:
        if msg.sender in self._peers:
            return messages.InvalidRequest(sender='0', data='Peer with such ID is already registered')

        # Peer informs broker under what URL its REP port can be reached.
        # It is peer's responsibility to provide publicly addressable IP if
        # peer wants other peers to talk to him directly.

        peer_url = msg.peer_url
        broker_url = msg.broker_url
        pi = self._add_peer(msg.sender, rep_urls=peer_url)

        # broker url should've been given to connecting client by TCP autodiscovery mechanism
        # now we return message proxy addressesses to Peer dependently where on the net he is and how he
        # found broker (local, remote, local ipc).
        if broker_url.startswith('ipc'):
            xpub_url = self._xpub_ipc
            xsub_url = self._xsub_ipc
        else:
            broker_url = urllib.parse.urlparse(broker_url)
            broker_host = broker_url.hostname
            xpub_port = self._find_port_for_ip(self._xpub_urls, broker_host)
            xsub_port = self._find_port_for_ip(self._xsub_urls, broker_host)

            if xpub_port is None or xsub_port is None:
                raise ObciException('Cannot determine XPUB or XSUB URLs for peer {}'
                                    .format(pi.id))

            xpub_url = 'tcp://{}:{}'.format(broker_host, xpub_port)
            xsub_url = 'tcp://{}:{}'.format(broker_host, xsub_port)
        return messages.BrokerHelloResponseMsg(sender='0', xpub_url=xpub_url,
                                               xsub_url=xsub_url)

    @register_message_handler(messages.BrokerGoodbyeMsg)
    async def _handle_goodbye(self, msg: messages.BrokerGoodbyeMsg) -> messages.BaseMessage:
        self._remove_peer(msg.sender)
        if msg.error_msg:
            self._logger.error('Peer %s shutting down with error: %s', msg.sender, msg.error_msg)
        return messages.OkMsg(sender='0')

    @register_message_handler(messages.BrokerRegisterQueryHandlerMsg)
    async def _handle_register_query_handler(self, msg: messages.BrokerRegisterQueryHandlerMsg) -> messages.BaseMessage:
        if msg.sender not in self._peers:
            return messages.InvalidRequest(sender='0', data='Say HELLO first!')
        peer = self._peers[msg.sender]
        msg_type = msg.msg_type
        if msg_type not in self._query_handlers:
            self._query_handlers[msg_type] = set()
            self.register_message_handler(msg_type, self._query_message_handler)
        self._query_handlers[msg_type].add(peer)
        return messages.OkMsg(sender='0')

    def _unregister_peer_from_query_handler(self, peer: PeerInfo, requested_msg_type: Optional[str] = None):
        if requested_msg_type is None:
            # unregister all types for current peer
            for msg_type in self._query_handlers.keys():
                self._query_handlers[msg_type].discard(peer)
        else:
            # unregister only given msg_type for current peer
            assert requested_msg_type in self._query_handlers
            self._query_handlers[requested_msg_type].discard(peer)

        # remove msg_type entries with empty handlers list
        for msg_type, handlers in list(self._query_handlers.items()):
            if len(handlers) == 0:
                self.unregister_message_handler(msg_type)
                del self._query_handlers[msg_type]

    @register_message_handler(messages.BrokerUnregisterQueryHandlerMsg)
    async def _handle_unregister_query_handler(
            self, msg: messages.BrokerUnregisterQueryHandlerMsg) -> messages.BaseMessage:
        if msg.sender not in self._peers:
            return messages.InvalidRequest(sender='0', data='Say HELLO first!')
        peer = self._peers[msg.sender]
        requested_msg_type = msg.msg_type
        self._unregister_peer_from_query_handler(peer, requested_msg_type)
        return messages.OkMsg(sender='0')

    async def _query_message_handler(self, msg: messages.BaseMessage) -> messages.BaseMessage:
        assert msg.type in self._query_handlers
        handlers = self._query_handlers[msg.type]
        query_pi = self._peers[msg.sender]
        assert len(handlers) >= 1, 'if len(handlers) == 0 there is possibly ' \
                                   'some error in handle_unregister_query_handler'
        handlers = [(pi.id, pi.find_rep_url(query_pi)) for pi in handlers]
        return messages.RedirectMsg(sender='0', peers=handlers)

    def _handle_message_handler_exception(self, ex: Exception) -> bool:
        return False  # Broker ignores exceptions in message handlers

    async def _peer_heartbeat_state_changed(self, pi: PeerInfo) -> None:
        if pi.hb_error:
            await self.send_panic('Peer {} has stopped sending heartbeats'.format(pi.id))

    @subscribe_message_handler(messages.HeartbeatMsg)
    async def _handle_heartbeat(self, msg: messages.BaseMessage) -> None:
        if msg.sender not in self._peers:
            return
        self._peers[msg.sender].heartbeats.append(time.monotonic())

    async def _monitor_heartbeats(self):
        while True:
            await asyncio.sleep(0.5)  # required

            now = time.monotonic()
            for pi in self._peers.values():  # type: PeerInfo
                hb = pi.heartbeats
                if len(hb) == 0:
                    continue

                # interval between last heartbeat timestamp and current timestamp (in seconds)
                interval_now = now - hb[-1]
                hb_error = interval_now >= self.heartbeat_error_interval
                hb_warning = interval_now >= self.heartbeat_warning_interval

                if hb_error != pi.hb_error:
                    if hb_error:
                        self._logger.fatal("Heartbeat error for peer '%s'", pi.id)
                    else:
                        self._logger.info("Heartbeat: peer '%s' recovered from error state", pi.id)
                    pi.hb_error = hb_error
                    await self._peer_heartbeat_state_changed(pi)

                if hb_warning != pi.hb_warning:
                    if hb_warning:
                        self._logger.warning("Heartbeat warning for peer '%s'", pi.id)
                    else:
                        self._logger.info("Heartbeat: peer '%s' recovered from warning state", pi.id)
                    pi.hb_warning = hb_warning
                    await self._peer_heartbeat_state_changed(pi)

                # calculate jitter - require at least 5 heartbeat timestamps
                if len(hb) < 5:
                    continue

                hb_jitter_warning = self.heartbeat_jitters(hb)

                if hb_jitter_warning != pi.hb_jitter_warning:
                    if hb_jitter_warning:
                        self._logger.debug("Heartbeat jitter warning for peer '%s'", pi.id)
                    else:
                        self._logger.debug("Heartbeat: peer '%s' recovered from jitter warning state", pi.id)
                    pi.hb_jitter_warning = hb_jitter_warning
                    await self._peer_heartbeat_state_changed(pi)

    def heartbeat_jitters(self, heartbeats: collections.deque) -> bool:
        """Given list of heartbeat timestams tell if heartbeat jitter warning should be raised."""
        latencies = tuple(heartbeats[idx + 1] - heartbeats[idx] for idx in range(len(heartbeats) - 1))
        diff = tuple(abs(latencies[idx + 1] - latencies[idx]) for idx in range(len(latencies) - 1))
        jitter = sum(diff) / len(diff)
        return jitter >= HEARTBEAT_JITTER_WARNING

    async def _shutting_down(self) -> None:
        await self._send_message(messages.BrokerShutdownMsg(msg='Shut down all peers.'))
        await super()._shutting_down()

    def _cleanup(self) -> None:
        self._peers = {}
        self._msg_proxy.shutdown()
        super()._cleanup()
