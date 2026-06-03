# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
import time

import pytest

from braintech.drivers.perun32.amplifier import Perun32Amplifier
from braintech.drivers.perun32.device import PerunAmp32Device, SampleData
from braintech.drivers.perun8.perun_timestamp_correcter import PerunAmpTimestampCorrecter


def test_pars_ads_data():
    data = b'0' * SampleData.PKT_LEN * 2
    packets = list(SampleData.parse_ads_data(data))
    assert len(packets) == 2


perun_not_connected = lambda: not any(PerunAmp32Device.find_devices())


@pytest.mark.skipif('perun_not_connected()')
def test_perun32_device():
    devices = list(PerunAmp32Device.find_devices())
    device = devices[0]
    device.open()
    for sampling_rate in [500, 1000, 2000, 4000, 8000]:
        device.set_sampling_rate(sampling_rate)
        device.start()
        for i in range(sampling_rate):
            device.get_samples()
        device.stop()
        print("QueueSize for sampling_rate", sampling_rate, device._queue.qsize())


@pytest.mark.skipif('perun_not_connected()')
def test_perun32_amplifier():
    available_amplifiers = Perun32Amplifier.get_available_amplifiers()
    assert len(available_amplifiers) > 0
    amp = Perun32Amplifier(available_amplifiers[0])
    amp.sampling_rate = 1000
    assert amp.sampling_rate == 1000
    amp.active_channels = ['ExG_5', 'AUX_1']
    current_description = amp.current_description
    assert current_description.sampling_rates == [1000]
    assert len(current_description.channels) == 2
    amp.start_sampling()
    try:
        start = time.time()
        samples_per_packet = amp.sampling_rate // 10
        samples = amp.get_samples(samples_per_packet)
        assert time.time() - start < 0.15
        assert samples.sample_count == samples_per_packet
        assert samples.channel_count == 2
    finally:
        amp.stop_sampling()


@pytest.mark.skipif('perun_not_connected()')
def test_perun32_amplifier_fast():
    available_amplifiers = Perun32Amplifier.get_available_amplifiers()
    amp = Perun32Amplifier(available_amplifiers[0])
    amp.sampling_rate = 8000
    amp.start_sampling()
    samples_per_packet = amp.sampling_rate
    for i in range(0, int(amp.sampling_rate * 10), samples_per_packet):
        amp.get_samples(samples_per_packet)
        print(i)
    amp.stop_sampling()


@pytest.mark.skipif('perun_not_connected()')
def test_perun32_amplifier_events():
    amp = Perun32Amplifier()
    amp.sampling_rate = 8000
    amp.active_channels = ['Events']
    amp.start_sampling()
    last = None
    for i in range(0, int(amp.sampling_rate * 100)):
        samples = amp.get_samples(1)
        events = samples.samples[0][0]
        if events != last:
            print(samples.ts[0], "{0:b}".format(events))
            last = events


@pytest.mark.skipif('perun_not_connected()')
def test_perun32_amplifier_timestamps():
    amp = Perun32Amplifier()
    amp.sampling_rate = 500
    amp.active_channels = ['Events']
    amp.start_sampling()
    duration = 100
    amp._timestamp_correcter = PerunAmpTimestampCorrecter(sampling_rate=amp.sampling_rate,
                                                          first_correction_after_s=10,
                                                          correction_fit_buffer_length_s=10)
    for i in range(0, int(amp.sampling_rate * duration)):
        samples = amp.get_samples(1)
        if i % amp.sampling_rate == 0:
            print(time.time() - samples.ts[0], amp._timestamp_correcter._correction_coeff)
