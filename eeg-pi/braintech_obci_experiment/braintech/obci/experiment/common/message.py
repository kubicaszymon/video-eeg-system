# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import zmq


class PollingObject:
    def __init__(self):
        self.poller = zmq.Poller()

    def poll_recv(self, socket, timeout):
        self.poller.register(socket, zmq.POLLIN)
        try:
            sockets = dict(self.poller.poll(timeout=timeout))
        except zmq.ZMQError as e:
            error_message = 'obci_client: zmq.poll(): ' + e.strerror
            return None, error_message
        finally:
            self.poller.unregister(socket)

        if socket in sockets and sockets[socket] == zmq.POLLIN:
            return recv_msg(socket), None
        else:
            return None, 'No data'


def send_msg(socket, message, flags=0):
    assert len(message) == 2
    for i in message:
        assert isinstance(i, bytes)
    return socket.send_multipart(message, flags=flags)


def recv_msg(socket, flags=0):
    return socket.recv_multipart(flags=flags)
