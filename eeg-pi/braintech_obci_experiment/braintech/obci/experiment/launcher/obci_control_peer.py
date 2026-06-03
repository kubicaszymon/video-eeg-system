#!/usr/bin/env python3
# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import argparse
import logging
import os
import sys
import threading
import time
import uuid

import zmq

from ..common.obci_control_settings import PORT_RANGE
import braintech.obci.experiment.messages.launcher_common_types  # noqa
from braintech.obci.core.control.common import net
from ..common.message import send_msg, recv_msg, PollingObject
from .subprocess_monitor import SubprocessMonitor
from braintech.obci.core.broker import ObciException
from braintech.obci.core.broker import messages as messages_core
from braintech.obci.experiment import messages
from braintech.obci.core.broker.messages import BaseMessage
from braintech.obci.core.utils.openbci_logging import get_logger, log_crash


class HandlerCollection:
    def __init__(self):
        self.handlers = {}
        self.default = self._default_handler
        self.error = self._error_handler
        self.unsupported = self._error_handler

    def copy(self):
        new = HandlerCollection()
        new.handlers = dict(self.handlers)
        new.default = self.default
        new.error = self.error
        new.unsupported = self.unsupported
        return new

    def _default_handler(*args):
        pass

    def _error_handler(*args):
        pass

    def handler(self, message_type):
        def save_handler(fun):
            if isinstance(message_type, str):
                self.handlers[message_type] = fun
            else:
                self.handlers[message_type.__TYPE__] = fun
            return fun

        return save_handler

    def default_handler(self):
        def save_default_handler(fun):
            self.default = fun
            return fun

        return save_default_handler

    def error_handler(self):
        def save_error_handler(fun):
            self.error = fun
            return fun

        return save_error_handler

    def unsupported_handler(self):
        def save_unsupported_handler(fun):
            self.unsupported = fun
            return fun

        return save_unsupported_handler

    def handler_for(self, message_name):
        handler = self.handlers.get(message_name, None)
        return handler


class OBCIControlPeer:
    PEER_TYPE = 'control_peer'
    msg_handlers = HandlerCollection()

    def __init__(self, source_addresses=None,
                 rep_addresses=None, pub_addresses=None, name=PEER_TYPE):

        # TODO TODO TODO !!!!
        # cleaner subclassing of obci_control_peer!!!
        self.hostname = net.gethostname()
        self.source_addresses = source_addresses if source_addresses else []
        self.rep_addresses = rep_addresses
        self.pub_addresses = pub_addresses
        self._all_sockets = []
        self._pull_addr = 'inproc://publisher_msg'
        self._push_addr = 'inproc://publisher'
        self._subpr_push_addr = 'inproc://subprocess_info'
        if not (hasattr(self, 'uuid')):
            self.uuid = str(uuid.uuid4())
        self.name = str(name)
        self.type = self.peer_type()

        if not hasattr(self, 'logger'):
            self.logger = get_logger('launcher.' + self.peer_type())

        if not hasattr(self, "ctx"):
            self.ctx = zmq.Context()

        self.subprocess_mgr = SubprocessMonitor(self.ctx, self.uuid, logger=self.logger)
        self.net_init()

        if self.source_addresses:
            self.registration_response = self.register()
            self._handle_registration_response(self.registration_response)
        else:
            self.registration_response = None

        self.interrupted = False
        for handler in logging.getLogger().handlers:
            if hasattr(handler, 'extra_provider'):
                handler.extra_provider = handler

    def peer_type(self):
        return self.PEER_TYPE

    def _publisher_thread(self, pub_addrs, pull_address, push_addr):
        # FIXME aaaaahhh pub_addresses are set here, not in the main thread
        # (which reads them in _register method)
        pub_sock, self.pub_addresses = self._init_socket(
            pub_addrs, zmq.PUB)

        pull_sock = self.ctx.socket(zmq.PULL)
        pull_sock.bind(pull_address)

        push_sock = self.ctx.socket(zmq.PUSH)
        push_sock.connect(push_addr)

        send_msg(push_sock, (b'1', b'1'))
        po = PollingObject()

        while not self._stop_publishing:
            try:
                to_publish, det = po.poll_recv(pull_sock, 500)

                if to_publish:
                    send_msg(pub_sock, to_publish)

            except Exception:
                break
        pub_sock.close()
        pull_sock.close()
        push_sock.close(linger=-1)

    def _subprocess_info(self, push_addr):
        push_sock = self.ctx.socket(zmq.PUSH)
        push_sock.connect(push_addr)

        send_msg(push_sock, (b'1', b'1'))
        while not self._stop_monitoring:
            dead = self.subprocess_mgr.not_running_processes()
            if dead:
                for key, status in dead.items():
                    messages.DeadProcessMsg(
                        machine=key[0],
                        pid=key[1],
                        status=status,
                    ).send(push_sock)
            time.sleep(0.5)  # required
        push_sock.close(linger=-1)

    def _push_sock(self, ctx, addr):
        sock = ctx.socket(zmq.PUSH)
        sock.connect(addr)
        return sock

    def _prepare_publisher(self):
        tmp_pull = self.ctx.socket(zmq.PULL)
        tmp_pull.bind(self._pull_addr)
        self.pub_thr = threading.Thread(target=self._publisher_thread,
                                        args=[self.pub_addresses,
                                              self._push_addr,
                                              self._pull_addr])
        self.pub_thr.daemon = True

        self._stop_publishing = False
        self.pub_thr.start()
        recv_msg(tmp_pull)
        self._publish_socket = self._push_sock(self.ctx, self._push_addr)
        self._all_sockets.append(self._publish_socket)
        tmp_pull.close()

    def _prepare_subprocess_info(self):
        self._subprocess_pull = self.ctx.socket(zmq.PULL)
        self._subprocess_pull.bind(self._subpr_push_addr)

        self.subprocess_thr = threading.Thread(target=self._subprocess_info,
                                               args=[self._subpr_push_addr])
        self.subprocess_thr.daemon = True
        self._stop_monitoring = False

        self.subprocess_thr.start()
        recv_msg(self._subprocess_pull)

        self._all_sockets.append(self._subprocess_pull)

    def net_init(self):
        self._all_sockets = []  # TODO: check if needed
        self._prepare_publisher()
        self._prepare_subprocess_info()

        (self.rep_socket, self.rep_addresses) = self._init_socket(
            self.rep_addresses, zmq.REP)
        self.rep_socket.setsockopt(zmq.LINGER, 0)
        self._all_sockets.append(self.rep_socket)
        self.logger.debug("name: {0} peer_type: {1} uuid: {2}".format(
            self.name, self.peer_type(), self.uuid)
        )
        self.logger.debug("rep: {0}".format(self.rep_addresses))
        self.logger.debug("pub: {0}".format(self.pub_addresses))

        self.source_req_socket = self.ctx.socket(zmq.REQ)

        if self.source_addresses:
            for addr in self.source_addresses:
                self.source_req_socket.connect(addr)
        self._all_sockets.append(self.source_req_socket)
        self._set_poll_sockets()

    def _init_socket(self, addrs, zmq_type):
        addresses = addrs if addrs else ['tcp://*']

        random_port = True if not addrs else False

        sock = self.ctx.socket(zmq_type)
        try:
            for i, addr in enumerate(addresses):
                if random_port and net.is_net_address(addr):
                    port = str(sock.bind_to_random_port(addr,
                                                        min_port=PORT_RANGE[0],
                                                        max_port=PORT_RANGE[1]))
                    addresses[i] = addr + ':' + str(port)
                else:
                    sock.bind(addr)
        except Exception as e:
            self.logger.critical("CRITICAL error: %s. Cannot bind to addresses: %s", str(e), addresses)
            raise e

        advertised_addrs = []
        for addr in addresses:
            if addr.startswith('tcp://*'):
                port = addr.rsplit(':', 1)[1]
                advertised_addrs.append('tcp://' + 'localhost:' + str(port))
                if net.gethostname() != 'localhost':
                    advertised_addrs.append('tcp://' + net.gethostname() + ':' + str(port))
            else:
                advertised_addrs.append(addr)
        return sock, advertised_addrs

    def _register(self, rep_addrs, pub_addrs, params):
        message = messages.RegisterPeerMsg(peer_type=self.type,
                                           uuid=self.uuid,
                                           rep_addrs=rep_addrs,
                                           pub_addrs=pub_addrs,
                                           name=self.name,
                                           other_params=params)
        self.logger.debug("_register()  " + str(message.serialize()))
        message.send(self.source_req_socket)
        response_str = recv_msg(self.source_req_socket)
        response = messages_core.deserialize(response_str)
        if isinstance(response, messages.RqErrorMsg):
            self.logger.critical("Registration failed: {0}".format(response_str))
            sys.exit(2)
        return response

    def register(self):
        params = self.params_for_registration()
        return self._register(self.rep_addresses, self.pub_addresses, params)

    def _handle_registration_response(self, response):
        pass

    def shutdown(self):
        self.logger.info("SHUTTING DOWN")
        self.interrupted = True

    def params_for_registration(self):
        return {}

    def basic_sockets(self):
        return [self.rep_socket, self._subprocess_pull]

    def custom_sockets(self):
        """
        subclass this
        """
        return []

    def all_sockets(self):
        return self.basic_sockets() + self.custom_sockets()

    def _set_poll_sockets(self):
        self._poll_sockets = self.all_sockets()

    @log_crash  # noqa: C901
    def run(self):
        self.pre_run()
        poller = zmq.Poller()
        poll_sockets = list(self._poll_sockets)
        for sock in poll_sockets:
            poller.register(sock, zmq.POLLIN)

        try:
            while not self.interrupted:
                self._update_poller(poller, poll_sockets)
                try:
                    socks = dict(poller.poll(timeout=1000))
                except zmq.ZMQError as e:
                    if e.errno != zmq.EAGAIN:
                        self.logger.warning(": zmq.poll(): " + str(e.strerror))
                else:
                    for sock in socks:
                        if socks[sock] != zmq.POLLIN:
                            self.logger.warning("sock not zmq.POLLIN! Ignore !")
                        else:
                            while True:
                                try:
                                    msg = recv_msg(sock, flags=zmq.NOBLOCK)
                                except zmq.ZMQError as e:
                                    ignored_errno = [zmq.EAGAIN, zmq.ENOTSOCK]
                                    if e.errno not in ignored_errno and sock.getsockopt(zmq.TYPE) != zmq.REP:
                                        self.logger.fatal("handling socket read error: %s  %d  %s",
                                                          e, e.errno, sock)
                                        poller.unregister(sock)
                                        if sock in poll_sockets:
                                            poll_sockets.remove(sock)
                                        self.handle_socket_read_error(sock, e)
                                    break
                                else:

                                    self.handle_message(msg, sock)
        finally:
            self._clean_up()

    def _crash_extra_description(self, exception=None):
        return ""

    def _crash_extra_data(self, exception=None):
        return {}

    def _crash_extra_tags(self, exception=None):
        return {'obci_part': 'launcher'}

    def _update_poller(self, poller, curr_sockets):
        self._set_poll_sockets()
        new_sockets = list(self._poll_sockets)

        for sock in new_sockets:
            if sock not in curr_sockets:
                poller.register(sock, zmq.POLLIN)
        for sock in curr_sockets:
            if sock not in new_sockets:
                poller.unregister(sock)

    def handle_socket_read_error(self, socket, error):
        pass

    def pre_run(self):
        pass

    def _clean_up(self):
        time.sleep(0.01)
        self._stop_publishing = True
        self._stop_monitoring = True
        self.pub_thr.join()
        self.subprocess_thr.join()
        for sock in self._all_sockets:
            sock.close()
        self.clean_up()

    def clean_up(self):
        self.logger.info("CLEANING UP")

    # message handling ######################################

    def handle_message(self, message, sock):

        handler = self.msg_handlers.default
        log_finished = False
        try:
            msg = messages_core.deserialize(message)
            if not isinstance(msg, (messages.PingMsg, messages.RqOkMsg,
                                    braintech.obci.experiment.messages.launcher_common_types.LogMsg)):
                self.logger.debug("got message: {0}".format(msg.type))
                log_finished = True
                if isinstance(msg, messages.GetTailMsg):
                    self.logger.debug(self.msg_handlers)
        except (KeyError) as e:
            self.logger.warning("{0} [{1}], Unknown Message {2}".format(
                self.name, self.peer_type(), message))
            handler = self.msg_handlers.error
            msg = BaseMessage()
        except (ValueError, ObciException) as e:
            self.logger.error("{0} [{1}], Bad message format! {2}".format(
                self.name, self.peer_type(), message))
            if sock.getsockopt(zmq.TYPE) == zmq.REP:
                handler = self.msg_handlers.error
            msg = message
            self.logger.error(e)
        else:
            msg_type = msg.type
            handler = self.msg_handlers.handler_for(msg_type)
            if handler is None:
                handler = self.msg_handlers.unsupported
        handler(self, msg, sock)
        if log_finished:
            self.logger.debug("Finished processing message %s", msg)

    @msg_handlers.handler(messages.RegisterPeerMsg)
    def handle_register_peer(self, message, sock):
        """Subclass this."""
        messages.RqErrorMsg(
            request=vars(message),
            err_code="unsupported_peer_type",
        ).send(sock)

    @msg_handlers.handler(messages.PingMsg)
    def handle_ping(self, message, sock):
        if sock.socket_type in [zmq.REP, zmq.ROUTER]:
            messages.PongMsg(
                sender='{}, {}'.format(self.name, type(self)),
                sender_ip=self.hostname,
            ).send(sock)

    @msg_handlers.default_handler()
    def default_handler(self, message, sock):
        """Ignore message"""
        pass

    @msg_handlers.unsupported_handler()
    def unsupported_msg_handler(self, message, sock):
        if sock.socket_type in [zmq.REP, zmq.ROUTER]:
            messages.RqErrorMsg(
                request=vars(message),
                err_code="unsupported_msg_type",
                sender=self.uuid,
            ).send(sock)

    @msg_handlers.error_handler()
    def bad_msg_handler(self, message, sock):
        messages.RqErrorMsg(
            request=vars(message),
            err_code="invalid_msg_format",
        ).send(sock)

    @msg_handlers.handler(messages.KillMsg)
    def handle_kill(self, message, sock):
        if not message.receiver or message.receiver == self.uuid:
            messages.RqOkMsg(
                params=dict(pid=os.getpid(), machine=self.hostname),
            ).send(sock)
            self.cleanup_before_net_shutdown(message, sock)
            self._clean_up()
            self.shutdown()

    @msg_handlers.handler(messages.DeadProcessMsg)
    def handle_dead_process(self, message, sock):
        pass

    def cleanup_before_net_shutdown(self, kill_message, sock=None):
        for sock in self._all_sockets:
            sock.close()


class RegistrationDescription:

    def __init__(self, uuid, name, rep_addrs, pub_addrs, machine, pid, other=None):
        self.machine_ip = machine
        self.pid = pid
        self.uuid = uuid
        self.name = name
        self.rep_addrs = rep_addrs
        self.pub_addrs = pub_addrs
        self.other = other

    def info(self):
        return dict(machine=self.machine_ip, pid=self.pid, uuid=self.uuid, name=self.name,
                    rep_addrs=self.rep_addrs, pub_addrs=self.pub_addrs, other=self.other)


def basic_arg_parser():
    parser = argparse.ArgumentParser(add_help=False,
                                     description='Basic OBCI control peer with public PUB and REP sockets.')
    parser.add_argument('--sv-addresses', nargs='+',
                        help='REP Addresses of the peer supervisor,\
    for example an OBCI Experiment controller may need OBCI Server addresses')
    parser.add_argument('--rep-addresses', nargs='+',
                        help='REP Addresses of the peer.')
    parser.add_argument('--pub-addresses', nargs='+',
                        help='PUB Addresses of the peer.')

    return parser


class OBCIControlPeerError(ObciException):
    pass


class MessageHandlingError(OBCIControlPeerError):
    pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(parents=[basic_arg_parser()])
    parser.add_argument('--name', default=OBCIControlPeer.PEER_TYPE,
                        help='Human readable name of this process')
    args = parser.parse_args()

    peer = OBCIControlPeer(args.sv_addresses,
                           args.rep_addresses, args.pub_addresses, args.name)

    peer.run()
