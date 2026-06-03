# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Predefined message types."""
from braintech.obci.core.broker.messages.base import BaseMessage
from braintech.obci.core.broker.messages.fields import Field
from braintech.obci.core.drivers.eeg.eeg_amplifier import SamplePacket


class IncompleteTagMsg(BaseMessage):
    __TYPE__ = 'INCOMPLETE_TAG'
    id = Field(str)
    start_timestamp = Field(float)  # CPython float is always 64 bit
    name = Field(str)
    channels = Field(str)
    desc = Field(dict)  # Dict[str, str]


class TagMsg(IncompleteTagMsg):
    __TYPE__ = 'TAG'
    end_timestamp = Field(float)


class SignalMessage(BaseMessage):
    __TYPE__ = 'AMPLIFIER_SIGNAL_MESSAGE'
    data = Field(SamplePacket)

    @classmethod
    def deserialize_data(cls, data: bytes):
        """
        Deserialize message data from second part of multipart message.

        Here for maximum performance this function returns not a dict for __init__ but ready to use SamplePacket.
        """
        return SamplePacket.from_bytes(data)

    @classmethod
    def deserialize(cls, data: bytes, sender: str = None):
        """
        Deserialize whole message from data bytes.

        Will be invoked in `MessageMeta` message serializer, which takes care of network
        protocol and invokes this function with sender information and payload bytes.
        :return: Instance of this class.
        """
        sample_p = cls.deserialize_data(data)
        return cls(sender=sender, data=sample_p)

    def serialize_data(self):
        """Serialize SignalMessage data to ``bytes``."""
        return self.data.to_bytes()

    def __init__(self, sender: str = '', data: SamplePacket = None):
        """
        Special Init for signal message is required for maximum performance.

        :param sender: Id of the sender
        :param data: SamplePacket with signal data to send.
        """
        if isinstance(data, SamplePacket):
            assert isinstance(sender, str)
            self._data_dict = {}
            self._sender = sender
            self._data_dict['data'] = data
        else:
            raise TypeError("Field 'data' has wrong type: {}. "
                            "Should be: SamplePacket.".format(type(data)))


class InvalidRequest(BaseMessage):
    data = Field(str)


class InternalError(BaseMessage):
    data = Field(str)


class HeartbeatMsg(BaseMessage):
    pass


class OkMsg(BaseMessage):
    pass


class RedirectMsg(BaseMessage):
    peers = Field(list)  # List[Tuple[peer_id: str, peer_url: str]]


class BrokerHelloMsg(BaseMessage):
    # external apps compat
    __TYPE__ = 'BROKER_HELLO'
    peer_url = Field(list, str)  # List[str]
    broker_url = Field(str)


class BrokerHelloResponseMsg(BaseMessage):
    # external apps compat
    __TYPE__ = 'BROKER_HELLO_RESPONSE'
    xpub_url = Field(str)
    xsub_url = Field(str)


class BrokerGoodbyeMsg(BaseMessage):
    error_msg = Field(str, None)


class BrokerRegisterQueryHandlerMsg(BaseMessage):
    msg_type = Field(str)


class BrokerUnregisterQueryHandlerMsg(BaseMessage):
    msg_type = Field(str, None)


class BrokerShutdownMsg(BaseMessage):
    msg = Field(str)


class AcquisitionControlMessage(BaseMessage):
    data = Field(str)


class ConfigServerUrlQuery(BaseMessage):
    pass


class ConfigServerUrlAnswer(BaseMessage):
    url = Field(str)


class PanicMsg(BaseMessage):
    data = Field(str, None)
    was_essential = Field(bool)


class DecisionMsg(BaseMessage):
    """Classificator decision message.

    :param decision: String "DONE LEARNING" or "CLASSIFICATION". First is used to indicate that classifier has finished
      calibration and has send it's self assesment score,
      second shows that classifier has decided on interface "button".
    :param score: Some self assesment score, or an index of interface "button"
    :param decision_type: some sort of classifier selection process identifier.
    :param start_timestamp: timestamp of the decsion
    :param end_timestamp: if decision has relevant time window, you can specify it using start and stop timestamp,
      otherwise start and stop timestamp should be the same.
    """
    decision = Field(str)
    score = Field(int, float)
    decision_type = Field(str)
    decision_averaging_type = Field(str, None)
    start_timestamp = Field(float)
    end_timestamp = Field(float)


class SaveVideoMsg(BaseMessage):
    __TYPE__ = "SAVE_VIDEO"
    PATH = Field(str)
    URL = Field(str)


class SaveVideoOKMsg(BaseMessage):
    __TYPE__ = "SAVE_VIDEO_OK"
    status = Field(str)


class SaveVideoDoneMsg(BaseMessage):
    __TYPE__ = "SAVE_VIDEO_DONE"
    status = Field(str)
    ts = Field(float)


class SaveVideoErrorMsg(BaseMessage):
    __TYPE__ = 'SAVE_VIDEO_ERROR'
    details = Field(str)
    status = Field(str)


class FinishSavingVideoMsg(BaseMessage):
    __TYPE__ = "FINISH_SAVING_VIDEO"
    pass


class PeerControlMessage(BaseMessage):
    peer_id = Field(str)
    action = Field(str)


class PeerSetParamQuery(BaseMessage):
    """Change config param in peer."""

    key = Field(str)
    value = Field(str)


class ErrorMsg(BaseMessage):
    details = Field(str, None)


class PeerUrlQuery(BaseMessage):
    """Ask broker for url of given peer OR send peer url.

    :ivar target: Id of peer whose url is needed
    :ivar target_url: [Optional, only in response] returned url
    """

    __TYPE__ = "PEER_URL_QUERY"
    target = Field(str)
    target_url = Field(str)
    sender_id = Field(str)
