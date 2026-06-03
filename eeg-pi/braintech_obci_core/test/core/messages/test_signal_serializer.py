#!/usr/bin/env python3
# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import numpy

from braintech.obci.core.broker import messages
from braintech.obci.core.drivers.eeg.eeg_amplifier import SamplePacket
from braintech.obci.signal_processing.signal.data_generic_write_proxy import Impedance, NETWORK_FLOAT32


def test_serializing():
    channel_count = 10
    sample_count = 4
    input = SamplePacket(
        ts=numpy.random.rand(sample_count),
        samples=numpy.random.random_sample((sample_count, channel_count))
    )
    serializer = messages.SignalMessage(sender='', data=input)
    ser = serializer.serialize()
    output = messages.deserialize(ser).data

    assert numpy.sum((output.ts - input.ts) ** 2) == 0.0  # float64
    assert numpy.sum((output.samples - input.samples) ** 2) < 1.0e-12


def test_default_impedance():
    channel_count = 10
    sample_count = 4
    input = SamplePacket(
        ts=numpy.random.rand(sample_count),
        samples=numpy.random.random_sample((sample_count, channel_count))
    )
    message = messages.SignalMessage(sender='', data=input)

    output = messages.deserialize(message.serialize()).data

    for i in range(10):
        assert output.impedance.for_channel(i) == Impedance.UNKNOWN


def test_impedance_data_serializing():
    channel_count = 10
    sample_count = 4

    impedance_flags = numpy.array([Impedance.UNKNOWN] * channel_count)
    impedance_flags[0:2] = Impedance.PRESENT
    impedance_flags[2:4] = Impedance.NOT_APPLICABLE
    impedance_data = numpy.random.random_sample((sample_count, 2)).astype(NETWORK_FLOAT32)

    impedance_package = Impedance(ids=impedance_flags, data=impedance_data)

    input = SamplePacket(
        ts=numpy.random.rand(sample_count),
        samples=numpy.random.random_sample((sample_count, channel_count), ),
        impedance=impedance_package,
    )

    message = messages.SignalMessage(sender='test_amp', data=input)
    output = messages.deserialize(message.serialize()).data

    expected_impedance = [impedance_data[:, 0],
                          impedance_data[:, 1],
                          Impedance.NOT_APPLICABLE,
                          Impedance.NOT_APPLICABLE
                          ] + ([Impedance.UNKNOWN] * 6)

    for i in range(channel_count):
        assert (output.impedance.for_channel(i) == expected_impedance[i]).all()


if __name__ == '__main__':
    test_serializing()
