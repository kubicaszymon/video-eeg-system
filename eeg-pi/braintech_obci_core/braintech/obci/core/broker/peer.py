# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Provides a standard Peer implementation for all peers connecting to and communicating with the Broker."""

import argparse
import asyncio
import collections
import json
import logging
import time
import urllib.parse
from typing import Iterable, List, Optional, Union

import zmq.asyncio

from braintech.obci.core.broker import messages
from braintech.obci.core.utils import DEFAULT_TIMEOUT
from . import ObciException, TCP_MAGIC_BYTES_OBCI, BROKER_TCP_IP_DEFAULT_PORT, DEFAULT_HEARTBEAT_DELAY
from .base_peer import BasePeer, ensure_connected, NotInitializedException, HandlerNotRegisteredException, PeerState
from .message_handler_mixin import (AlreadyRegisteredException,
                                    NotRegisteredException,
                                    QueryHandler,
                                    QueryDataType,
                                    subscribe_message_handler)
from .zmq_asyncio_task_manager import ensure_not_inside_msg_loop
from braintech.obci.core.utils.asyncio import wait_for_condition
from braintech.obci.core.utils.zmq import TimeoutException

__all__ = (
    'Peer',
    'PeerInitUrls',
    # type annotation helpers
    'QueryDataType',
    'QueryHandler',
    # exceptions
    'NotInitializedException',
    'HandlerNotRegisteredException',
    'AlreadyRegisteredException',
    'MultiplePeersAvailable',
    'NotRegisteredException',
    'QueryAnswerUnknown',
    'TooManyRedirectsException',
)


class PeerInitUrls(collections.namedtuple('PeerInitUrls',
                                          ['pub_urls', 'rep_urls', 'broker_rep_url'])):
    """
    List of initial URL addresses.

    :param list pub_urls: list of PUB URL's to bind to
    :param list rep_urls: list of REP URL's to bind to
    :param str broker_rep_url: broker's REP URL
    """


class TooManyRedirectsException(ObciException):
    """Raised when too many redirects occurred in Peer.query method."""


class QueryAnswerUnknown(ObciException):
    """Raised when answer to query is unknown."""


class MultiplePeersAvailable(ObciException):
    """
    Raised when more that one peer can answer specified :meth:`Peer.query`.

    When caught, caller of the :meth:`Peer.query` method must decide
    which peer to ask and reissue query by calling :meth:`Peer.query` method
    with ``initial_peer`` parameter set to one of supplied peers.
    """

    def __init__(self, peers: Iterable[str], *args, **kwargs):
        """
        Raise the exception with given list of available peers.

        :param peers: list of peers
        """
        super().__init__(*args, **kwargs)
        self.peers = peers

    def __str__(self):
        """
        Return a human-readable representation of this exception.

        The returned description consists of the exception name and a list of available peers.
        """
        return super().__str__() + ': ' + ', '.join(str(peer) for peer in self.peers)


class PeerNotFound(ObciException):
    pass


class HeartbeatDisablerMixin:
    async def _heartbeat(self):
        pass


class Peer(BasePeer):
    """
    A regular peer. All peers derive from this class.

    On top of the functionality of :class:`BasePeer`, :class:`Peer` implements connecting to broker,
    sending heartbeats and IP auto-discovery.
    """

    def __init__(self,
                 urls: Union[str, PeerInitUrls],
                 peer_id: Optional[str] = None,
                 asyncio_loop: Optional[zmq.asyncio.ZMQEventLoop] = None,
                 zmq_context: Optional[zmq.asyncio.Context] = None,
                 zmq_io_threads: int = 1,
                 hwm: int = 1000,
                 autostart: bool = True,
                 autoshutdown: bool = True,
                 **kwargs) -> None:
        """
        Create a new peer.

        Peer will be initialized automatically.

        :param urls: string or PeerInitUrls with initial bootstrap addresses
        :param peer_id: globally unique identifier
        :param asyncio_loop: existing ZMQ asyncio message loop or ``None`` if loop is requested
        :param zmq_context: existing ZMQ asyncio context or ``None`` if new context is requested
        :param zmq_io_threads: number of ZMQ I/O threads
        :param hwm: ZMQ high water mark
        :param autostart: whether this peer should be started automatically
        :param autoshutdown: whether this peer should be closed automatically
        """
        assert isinstance(urls, (str, PeerInitUrls))
        assert isinstance(urls.pub_urls, (list, tuple)) if isinstance(urls, PeerInitUrls) else True
        assert isinstance(urls.rep_urls, (list, tuple)) if isinstance(urls, PeerInitUrls) else True
        assert isinstance(urls.broker_rep_url, str) if isinstance(urls, PeerInitUrls) else True

        self._query_handlers = []
        self._log_handlers_to_finalize = None

        if isinstance(urls, PeerInitUrls):
            self._ip_autodiscovery = False
            # assume peer is accessible to other peers under first provided URL
            self._peer_url = None
            self._peer_url_initial = urls.rep_urls[0]
            self._pub_urls = set(urls.pub_urls)
            self._rep_urls = list(urls.rep_urls)
            self._broker_tcp_ip_address = None
            self._broker_rep_url = urls.broker_rep_url
        else:
            self._ip_autodiscovery = True
            self._pub_urls = None
            self._rep_urls = None
            self._broker_tcp_ip_address = self._split_ipv4_address(urls, BROKER_TCP_IP_DEFAULT_PORT)
            self._broker_rep_url = None
            self._peer_url = None
            self._peer_url_initial = None

        # heartbeat
        self._heartbeat_enabled = True
        self._heartbeat_delay = DEFAULT_HEARTBEAT_DELAY

        self._max_query_redirects = 10

        self.autostart = autostart
        self.autoshutdown = autoshutdown

        super().__init__(peer_id=peer_id,
                         asyncio_loop=asyncio_loop,
                         zmq_context=zmq_context,
                         zmq_io_threads=zmq_io_threads,
                         hwm=hwm)

    @classmethod
    def create_peer(cls, argv: List[str]) -> 'Peer':
        """Parse supplied argv and create new Peer instance."""
        parser = cls.create_parser(argv)
        options, unknown_args = parser.parse_known_args(argv)
        return cls._create_peer(options, unknown_args)

    @classmethod
    def _create_peer(cls, options, unknown_args):
        if options.broker_ip is not None:
            urls = options.broker_ip
        else:
            urls = PeerInitUrls(pub_urls=options.pub_urls,
                                rep_urls=options.rep_urls,
                                broker_rep_url=options.broker_rep_url)
        exclude_list = ['broker_ip', 'pub_urls', 'rep_urls', 'broker_rep_url']
        peer = cls(urls, **{k: v for k, v in vars(options).items()
                            if k not in exclude_list})
        return peer

    @classmethod
    def create_parser(cls, argv, add_help=True) -> argparse.ArgumentParser:
        """Create a ArgumentParser instance for parsing this peer's command line parameters."""
        parser = argparse.ArgumentParser(add_help=add_help)
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument('--broker-ip')
        group.add_argument('--broker-rep-url')
        parser.add_argument('--pub-urls', nargs='+', required=False)
        parser.add_argument('--rep-urls', nargs='+', required=False)
        parser.add_argument('--peer_id', metavar='name', type=str, nargs='?')
        return parser

    async def ask_peer_by_id(self, peer_id: str, message: messages.BaseMessage):
        urls = await self._get_peer_url(peer_id)
        return await self.ask_peer(urls, message)

    async def _get_peer_url(self, peer_id: str):
        message = messages.PeerUrlQuery(target=peer_id, target_url='',
                                        sender_id=self.peer_id)
        response = await self.ask_broker(message)
        if getattr(response, 'target_url', None) and getattr(response, 'target') == peer_id:
            return response.target_url
        else:
            raise PeerNotFound("Couldn't get peer url! Actual answer: {}"
                               .format(response))

    @ensure_connected
    async def ask_broker(self, msg: messages.BaseMessage, timeout: float = 5.0) -> messages.BaseMessage:
        """
        Send message to Broker and return answer.

        :param msg: message object to send
        :param timeout: timeout in seconds
        :return: response message
        """
        return await self._ask_broker(msg, timeout)

    async def _ask_broker(self, msg: messages.BaseMessage, timeout: float = 5.0) -> messages.BaseMessage:
        return await self.ask_peer(self._broker_rep_url, msg, timeout)

    @ensure_not_inside_msg_loop
    def query(self,
              query_msg: messages.BaseMessage,
              initial_peer: Optional[Union[List[str], str]] = None
              ) -> QueryDataType:
        """
        Send query message to Broker (or any other peer in `initial_peer` is specified).

        Returned value can be any JSON-serializable object.

        :param query_type: Query message, with filled in params,
          if it doesn't have sender param set, it will be set automatically
        :param initial_peer: if specified this peer will be asked instead of Broker
        :return: query response
        """
        # TODO: Change task to critical after redmine: #34058 is done
        return self.create_task(self.query_async(query_msg, initial_peer), critical=False).result()

    @ensure_connected
    async def query_async(self,
                          query_msg: messages.BaseMessage,
                          initial_peer: Optional[Union[List[str], str]] = None
                          ) -> messages.BaseMessage:
        """Async version of :func:`Peer.query`."""
        url = self._broker_rep_url if initial_peer is None else initial_peer
        redirects = 0
        while True:
            response = await self.ask_peer(url, query_msg)
            if isinstance(response, messages.RedirectMsg):
                urls = response.peers
                assert len(urls) > 0
                if len(urls) == 1:
                    url = urls[0][1]
                elif len(urls) > 1:
                    raise MultiplePeersAvailable(urls, 'Multiple peers can answer this query')
            elif isinstance(response, (messages.InvalidRequest, messages.InternalError)):
                raise QueryAnswerUnknown('Cannot answer to query {}, error: {}'.format(query_msg, response))
            else:
                return response
            redirects += 1
            if redirects >= self._max_query_redirects:
                self._logger.error("max redirects ({}) reached when executing query '{}'"
                                   .format(self._max_query_redirects, query_msg))
                raise TooManyRedirectsException('max redirects reached')

    @ensure_not_inside_msg_loop
    def register_query_handler(self,
                               msg_type: Union[str, messages.BaseMessage],
                               handler: QueryHandler) -> None:
        """
        Register callback handler for specified query type.

        ``handler`` function must return a valid :class:`~obci.core.messages.Message` object.

        :param msg_type: query type, string - network ID of desired message or message class
        :param handler: function to execute when specified query is received
        """
        # TODO: Change task to critical after redmine: #34058 is done
        self.create_task(self.register_query_handler_async(msg_type, handler), critical=False).result()

    @ensure_connected
    async def register_query_handler_async(self,
                                           msg_type: Union[str, messages.BaseMessage],
                                           handler: QueryHandler) -> None:
        """Async version of :func:`Peer.register_query_handler_async`."""
        if issubclass(msg_type, messages.BaseMessage):
            msg_type = msg_type.type
        self.register_message_handler(msg_type, handler)
        response = await self.ask_broker(
            messages.BrokerRegisterQueryHandlerMsg(msg_type=msg_type)
        )
        if not isinstance(response, messages.OkMsg):
            self.unregister_message_handler(msg_type)
            raise ObciException('Could not register QUERY handler!')
        self._query_handlers.append(msg_type)

    @ensure_not_inside_msg_loop
    def unregister_query_handler(self, msg_type: Optional[Union[str, messages.BaseMessage]] = None) -> None:
        """
        Unregister callback handler.

        For specified query type or for all query
        types if ``msg_type`` is ``None``.

        :param msg_type:  query type
        """
        if not isinstance(msg_type, str) and msg_type is not None:
            msg_type = msg_type.type
        # TODO: Change task to critical after redmine: #34058 is done
        self.create_task(self.unregister_query_handler_async(msg_type), critical=False).result()

    @ensure_connected
    async def unregister_query_handler_async(self, msg_type: Optional[Union[str, messages.BaseMessage]] = None) -> None:
        """Async version of :func:`Peer.unregister_query_handler`."""
        if not isinstance(msg_type, str) and msg_type is not None:
            msg_type = msg_type.type
        response = await self.ask_broker(
            messages.BrokerUnregisterQueryHandlerMsg(msg_type=msg_type)
        )
        if not isinstance(response, messages.OkMsg):
            raise ObciException('Broker response error: {}'.format(response))
        if msg_type is None:
            for q_type in self._query_handlers:
                self.unregister_message_handler(q_type)
            self._query_handlers = []
        else:
            self.unregister_message_handler(msg_type)
            self._query_handlers.remove(msg_type)

    def _create_logger(self):
        self._initialize_log_handlers()
        return super()._create_logger()

    def _initialize_log_handlers(self):
        for handler in logging.getLogger().handlers:
            if hasattr(handler, 'setPeer'):
                handler.setPeer(self)

    def _finalize_log_handler(self):
        for handler in logging.getLogger().handlers:
            if hasattr(handler, 'setPeer'):
                handler.setPeer(None)

    async def _establish_connections(self) -> None:
        if self._ip_autodiscovery:
            self._logger.debug('Running IP autodiscovery...')
            await self.__run_ip_autodiscovery()

        self._pub_urls = self._bind_to_urls(self._pub, self._pub_urls)
        self._rep_urls = self._bind_to_urls(self._rep, self._rep_urls)

        self._normalize_url_set(self._pub_urls)
        self._normalize_url_set(self._rep_urls)

        if self._peer_url_initial.startswith('ipc'):
            self._peer_url = self._peer_url_initial
        else:
            if self._peer_url is None:
                url = urllib.parse.urlparse(self._peer_url_initial)
                port = self._find_port_for_ip(self._rep_urls, url.hostname)
                if port is None:
                    raise ObciException("Couldn't determine peer_url.\n"
                                        "_peer_url_initial: {}\n_rep_urls: {}"
                                        .format(self._peer_url_initial,
                                                self._rep_urls))
                self._peer_url = self._peer_url_initial
                self._logger.info('IP autodiscovery: peer_url: %s', self._peer_url)
            else:
                self._logger.info('No IP autodiscovery: peer_url: %s', self._peer_url)

        self._logger.debug(
            "\n"
            "Peer '%s': Initial PUB & REP bind finished.\n"
            "PUB: %s\n"
            "REP: %s\n"
            "\n",
            self.id,
            ', '.join(self._pub_urls),
            ', '.join(self._rep_urls)
        )

        # send hello to broker, receive extra URLs to bind PUB and REP sockets to

        # ask_broker normally requires ensure_connected
        # we are not fully connected here, but we know we can use this function
        response = await self._ask_broker(
            messages.BrokerHelloMsg(peer_url=list(self._rep_urls),
                                    broker_url=self._broker_rep_url),
            timeout=30.0
        )
        if not isinstance(response, messages.BrokerHelloResponseMsg):
            raise ObciException('BROKER_HELLO failed '
                                '(response type: {}, contents: {})'
                                .format(response.type, vars(response)))

        self._logger.debug(
            "\n"
            "Peer '%s': After BROKER_HELLO.\n"
            "PUB: %s\n"
            "REP: %s\n"
            "\n",
            self.id,
            ', '.join(self._pub_urls),
            ', '.join(self._rep_urls)
        )

        broker_xpub_url = response.xpub_url
        broker_xsub_url = response.xsub_url

        self._pub.connect(broker_xsub_url)  # connect PUB to XSUB
        self._sub.connect(broker_xpub_url)  # connect SUB to XPUB

        self._logger.info(
            "\n"
            "Peer '%s'. Connect to Broker finished.\n"
            "Connected to Broker at REP %s; XPUB %s; XSUB %s\n"
            "PUB URLs: %s\n"
            "REP URLs: %s\n"
            "\n",
            self.id,
            self._broker_rep_url,
            broker_xpub_url,
            broker_xsub_url,
            ', '.join(self._pub_urls),
            ', '.join(self._rep_urls)
        )

    @ensure_connected
    async def _connections_established(self) -> None:
        await super()._connections_established()
        self.create_task(self._heartbeat())

    async def _initialized(self):
        await super(Peer, self)._initialized()
        if self.autostart:
            await self._start()

    async def _start(self):
        self._state = PeerState.running

    def start(self):
        """Start the peer."""
        task = self.create_task(self._start())
        task.result(timeout=DEFAULT_TIMEOUT)

    def run(self):
        """Run the main loop in subclasses (if any) then wait for the finish."""
        self._wait_until_finished()

    async def _stop(self):
        self._state = PeerState.ready
        if self.autoshutdown:
            await self.async_shutdown()

    def stop(self):
        """Stop the peer."""
        task = self.create_task(self._stop())
        task.result(timeout=DEFAULT_TIMEOUT)

    @ensure_connected
    async def _heartbeat(self) -> None:
        """Periodically send ``HEARTBEAT`` messages."""
        self._logger.debug("Peer '%s': Starting heartbeat...", self.id)
        heartbeat_message = messages.HeartbeatMsg()
        next_heartbeat = time.monotonic()
        while True:
            if self._heartbeat_enabled:
                await self._send_message(heartbeat_message)
            cur_time = time.monotonic()
            next_heartbeat = max(next_heartbeat + self._heartbeat_delay, cur_time)
            sleep_duration = next_heartbeat - cur_time
            await asyncio.sleep(sleep_duration)

    async def __run_ip_autodiscovery(self):
        reader = None
        writer = None

        async def wait_for_connection_established():
            nonlocal reader
            nonlocal writer
            try:
                self._logger.debug('Trying to connect to: %s:%s...',
                                   self._broker_tcp_ip_address[0],
                                   self._broker_tcp_ip_address[1])
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(
                        self._broker_tcp_ip_address[0],
                        self._broker_tcp_ip_address[1],
                        loop=self._loop),
                    timeout=1.0)
                self._logger.debug('...connected')
                return True
            except Exception:
                return False

        await wait_for_condition(wait_for_connection_established,
                                 timeout=30.0,
                                 sleep_duration=0.5,
                                 name='Connecting to Broker TCP/IP server')

        try:
            writer.write(TCP_MAGIC_BYTES_OBCI + self.capabilities.serialize() + b'\n')
            asyncio.wait_for(writer.drain(), timeout=10.0)
            data = await asyncio.wait_for(reader.read(), timeout=10.0)
            data = json.loads(data.decode('ascii'))

            self._logger.debug("IP autodiscovery data for peer %s: %s", self.id, data)

            self._broker_rep_url = data['broker_url']
            self._pub_urls = data['pub_urls']
            self._rep_urls = data['rep_urls']
            self._peer_url_initial = data['rep_urls'][0]

            writer.close()
        finally:
            del reader
            del writer

    async def _send_goodbye_msg(self, error_msg=None, timeout=10.0):
        msg = messages.BrokerGoodbyeMsg(error_msg=error_msg)
        try:
            response = await self.ask_broker(msg, timeout)
            if not isinstance(response, messages.OkMsg):
                self._logger.error('Error during peer unregister, got broker response %s', response.data)
        except NotInitializedException:
            self._logger.debug('Shutting down before connection to broker is established')
        except TimeoutException:
            self._logger.warning('Broker is dead before Peer shutdown')

    @subscribe_message_handler(messages.PeerControlMessage)
    async def _handle_control_peer_message(self, msg):
        if msg.peer_id == self.id:
            if msg.action == 'start':  # starting peer
                await self._start()
            if msg.action == 'stop':  # stopping peer
                await self._stop()
            if msg.action == 'close':  # shut_down
                await self.async_shutdown()
            return messages.OkMsg(status="ok", params={}, request=msg.action,
                                  receiver='', sender_ip='')

    @subscribe_message_handler(messages.BrokerShutdownMsg)
    async def handle_broker_shutdown_message(self, msg):
        """When message "BROKER_SHUTDOWN" arrive: shuts down peer."""
        await self.async_shutdown()

    async def _shutting_down(self):
        if self.is_connected:
            error_msg = str(self._exception) if self._exception else None
            await self._send_goodbye_msg(error_msg)
        await super()._shutting_down()

    def _cleanup(self) -> None:
        self._finalize_log_handler()
        self._logger.info("Peer '%s' is closed", self.id)
        super()._cleanup()

    async def async_shutdown(self):
        """
        Shut down this peer (coroutine version).

        Can be called from coroutine running inside the message loop.
        This method implements human-friendly logging and prevents duplicate calling.
        In order to customize shutdown process, override :meth:`_shutting_down` for long tasks and :meth:`_cleanup`
        for final resource cleanup
        """
        if self.is_running:
            await self._stop()
        await super().async_shutdown()
