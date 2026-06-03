# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Package providing OBCI launcher base Message types, converted from message template dicts."""
from braintech.obci.core.broker.messages import BaseMessage
from braintech.obci.core.broker.messages.fields import Field


class LauncherMessageBare(BaseMessage):
    """
    Class containing basic compatability methods for Launcher messages.

    Contains no fields, only methods, required for compatability.
    Allows code written for old OBCI Launcher messages to function
    almost without changes.
    """

    def SerializeToString(self):
        """
        Serialize Message for sending.

        Now it is a tuple of bytes, not string. Left for compatibility reasons.
        """
        return self.serialize()

    def dict(self):
        """Compatability method."""
        result = {}
        result.update({'type': self.type})
        result.update(self.data_dict)
        return result

    def raw(self):
        """Compatability method."""
        return b''.join(self.serialize())

    def decode(self):
        """Compatability method."""
        return self.raw().decode()

    def send(self, socket):
        from braintech.obci.experiment.common.message import send_msg
        return send_msg(socket, self.serialize())


class LauncherMessageBase(LauncherMessageBare):
    """
    Base message typ for all OBCI Launcher messages.

    Devised from legacy OBCI messages templates.
    """

    receiver = Field(str)
    sender_ip = Field(str)


class PubAddrRqMsg(LauncherMessageBase):
    __TYPE__ = 'pub_addr_rq'


class KillMsg(LauncherMessageBase):
    __TYPE__ = 'kill'
    force = Field(bool)


class PubAddrMsg(LauncherMessageBase):
    __TYPE__ = 'pub_addr'
    pub_addresses = Field(str)
    request = Field(str)


class HeartbeatMsg(LauncherMessageBase):
    __TYPE__ = 'heartbeat'


class PongMsg(LauncherMessageBase):
    __TYPE__ = 'pong'


class PingMsg(LauncherMessageBase):
    __TYPE__ = 'ping'


class RqOkMsg(LauncherMessageBase):
    __TYPE__ = 'rq_ok'
    status = Field(str, None)
    params = Field(dict, None)
    request = Field(str, None)


class RqErrorMsg(LauncherMessageBase):
    __TYPE__ = 'rq_error'
    request = Field(str, dict, list, tuple)
    details = Field(str, list)
    err_code = Field(str)


class LogMsg(LauncherMessageBare):
    __TYPE__ = 'log_msg'
    msg = Field(str)
    timestamp = Field(float)
    subsource = Field(str)
    log_type = Field(str)
    source = Field(str)
