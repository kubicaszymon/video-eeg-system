# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import numpy
import pytest

from braintech.obci.core.drivers.eeg.eeg_amplifier import SamplePacket
from braintech.obci.core.broker import messages
from braintech.obci.core.broker.messages.fields import Field


class BrokerHelloMsg(messages.BaseMessage):
    # here Metamagic transforms these class attributes to message instance fields
    # Metamagic also registers deserializers for this class
    # By default OBCI messages have JsonSerializer
    # If you want to change the serializer
    # you should provide serialize(self, data) and deserialize(cls, data) methods
    #
    __TYPE__ = 'TEST_BROKER_HELLO'
    peer_url = Field(list)  # List[str]
    broker_url = Field(str)


class EEGSignalMsg(messages.SignalMessage):
    # TYPE - if not defined the network string is defined using class name
    pass


def roundtrip(data_dict, cls):
    msg = cls(**data_dict)
    serialized = msg.serialize()
    deserialized = messages.deserialize(serialized)
    assert deserialized == msg
    new_dict = deserialized.data_dict
    new_dict.update(sender=deserialized.sender)
    assert new_dict == data_dict


def test_meta_magic_roundtrip():
    msg_dict = dict(peer_url=['ipc:///tmp/e9201b75-d0ae-4512-a0b6-b7b4bc31e911.ipc', 'tcp://192.168.0.43:34168'],
                    broker_url='ipc:///tmp/broker_rep_0a7b6598-fa8f-11e6-b47a-e09467b1bf61.ipc',
                    sender='test')
    roundtrip(msg_dict, BrokerHelloMsg)

    msg_dict = dict(data=SamplePacket(numpy.zeros((10, 10)), numpy.ones(10)), sender='test')
    roundtrip(msg_dict, EEGSignalMsg)


def test_msg_field_instance_attr():
    msg = EEGSignalMsg(data=SamplePacket(numpy.zeros((10, 10)), numpy.ones(10)), sender='test')
    msg2 = EEGSignalMsg(data=SamplePacket(numpy.ones((10, 10)), numpy.ones(10)), sender='test')
    assert msg != msg2


def test_type_validation():
    with pytest.raises(TypeError):
        EEGSignalMsg(data='test_bad_data')
    with pytest.raises(TypeError):
        BrokerHelloMsg(peer_url=1, broker_url=2)


def test_all_fields_validation():
    with pytest.raises(TypeError):
        EEGSignalMsg()
