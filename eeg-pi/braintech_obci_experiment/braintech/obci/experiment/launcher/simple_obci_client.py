# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
import logging

import zmq

from braintech.obci.core.conf import settings
from braintech.obci.core.control.common import net
from ..common.message import PollingObject
from braintech.obci.core.broker import messages as messages_core
from braintech.obci.experiment import messages

logger = logging.getLogger(__name__)


class ServerResponseInvalid(Exception):
    pass


class EmptyResponse:
    def __init__(self, details):
        self.type = "no_data"
        self.details = details

    def raw(self):
        return self.details.encode('utf-8')


class SimpleOBCIClient:
    PEER_TYPE = 'obci_client'
    default_timeout = 10000

    def __init__(self, server_addresses=None, zmq_context=None):
        if server_addresses is None:
            server_addresses = ['tcp://localhost:%d' % settings.rep_port]
        self.ctx = zmq_context if zmq_context else zmq.Context()
        self.ctx.setsockopt(zmq.LINGER, 0)

        self.server_addresses = server_addresses
        self.server_req_socket = None
        self.init_server_socket(server_addresses)

        self.poller = PollingObject()
        self.dns = net.DNS()

    def init_server_socket(self, srv_addrs):
        if self.server_req_socket is not None:
            logger.debug("server socket restart")
            self.server_req_socket.close()

        self.server_req_socket = self.ctx.socket(zmq.REQ)

        for addr in srv_addrs:
            logger.debug("Server address: %s", addr)
            self.server_req_socket.connect(addr)

    def ping_server(self, timeout=50):
        msg = messages.PingMsg()
        response, details = self._send_recv(self.server_req_socket, msg, timeout)
        return response

    def get_experiment_contact(self, strname):
        msg = messages.GetExperimentContactMsg(
            strname=strname,
        )
        response, details = self._send_recv(self.server_req_socket, msg, self.default_timeout)
        return response

    def get_experiment_details(self, strname, peer_id=None):
        response = self.get_experiment_contact(strname)
        if isinstance(response, (messages.RqErrorMsg, EmptyResponse)):
            return response

        sock = self.ctx.socket(zmq.REQ)
        try:
            for addr in response.rep_addrs:
                sock.connect(addr)

            if peer_id:
                msg = messages.GetPeerInfoMsg(peer_id=peer_id)
            else:
                msg = messages.GetExperimentInfoMsg()
            response, details = self._send_recv(sock, msg, timeout=self.default_timeout)
            return response
        finally:
            sock.close()

    def _send_recv(self, socket, msg, timeout=default_timeout):
        msg.send(socket)
        response, details = self.poll_recv(socket, timeout)
        if isinstance(response, EmptyResponse):
            logger.warning("Timeout (%d) while waiting on response for %s ", timeout, msg)
        return response, details

    def poll_recv(self, socket, timeout):
        result, details = self.poller.poll_recv(socket, timeout)
        if result:
            result = messages_core.deserialize(result)
        else:
            result = EmptyResponse(details)
            if socket is self.server_req_socket:
                # existing REQ socket is invalid after timeout
                self.init_server_socket(self.server_addresses)

        return result, details

    def server_req(self, msg, timeout=default_timeout):
        return self._send_recv(self.server_req_socket, msg, timeout)

    def srv_kill(self):
        msg = messages.KillMsg()
        return self._send_recv(self.server_req_socket, msg, 2000)[0]
