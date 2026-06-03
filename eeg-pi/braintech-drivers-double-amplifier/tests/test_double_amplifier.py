# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
import threading
import time
from typing import Optional, List

import numpy as np
import pytest

from braintech.drivers.double_amplifier.double_amplifier_peer import DoubleAmplifier, DoublePerunAmp
from braintech.obci.core.drivers.eeg.eeg_amplifier import EEGAmplifier, AmplifierDescription, ChannelDescription
from braintech.obci.signal_processing.signal.containers import Impedance, SamplePacket


class ConstantAmplifier(EEGAmplifier):

    @classmethod
    def get_available_amplifiers(cls, device_type: Optional[str] = None) -> List[str]:
        return ["Constant1", "Constant2"]

    _description = AmplifierDescription("ConstantAmplifier",
                                        [1000],
                                        [
                                            ChannelDescription(
                                                name="Ch_%d" % i,
                                                impedance=Impedance.UNKNOWN if i == 0 else Impedance.PRESENT,
                                            ) for i in range(3)
                                        ])

    def _get_samples(self, samples_per_packet):
        ch_num = self.description.ch_num
        samples = np.empty((samples_per_packet, ch_num))
        samples[:, :] = range(0, ch_num)
        samples = self._reindex_samples(samples)
        t0 = time.time()
        ts = np.linspace(t0, t0 + 1 / self.sampling_rate * samples_per_packet, samples_per_packet)
        impedance = self._get_impedance(samples_per_packet)
        return SamplePacket(ts=ts, samples=samples, impedance=impedance)

    def _get_impedance(self, samples_per_packet) -> Impedance:
        flags = [ch.impedance for ch in self.get_active_channels()]
        values = []
        for i, ch in enumerate(self.get_active_channels()):
            if ch.impedance == Impedance.PRESENT:
                values.append(ch.index * 10)
        impedance_channels = sum(flag == Impedance.PRESENT for flag in flags)
        data = np.empty((samples_per_packet, impedance_channels))
        data[:, :] = values
        return Impedance(ids=flags, data=data)


class _TestDoubleAmplifier(DoubleAmplifier):
    MASTER_AMPLIFIER_CLASS = ConstantAmplifier
    OTHER_AMPLIFIER_CLASS = ConstantAmplifier


def test_double_amplifier():
    constant_amps = ConstantAmplifier.get_available_amplifiers()
    constant_amp_desc = ConstantAmplifier.get_description(constant_amps[0])
    available = _TestDoubleAmplifier.get_available_amplifiers()
    assert len(available) == len(constant_amps) ** 2
    print(available)
    chosen = available[0]
    desc = _TestDoubleAmplifier.get_description(chosen)
    assert desc.ch_num == constant_amp_desc.ch_num * 2 + 2
    double = _TestDoubleAmplifier(chosen)
    double.sampling_rate = 1000
    double.active_channels = ["Ch_1-0", "Ch_2-1", "Ch_2-0", "Ch_0-0", "Ch_0-0", "Ch_1-1"]
    expected_impedances = [10, 20, 20, Impedance.UNKNOWN, Impedance.UNKNOWN, 10]
    expected_samples = [1, 2, 2, 0, 0, 1]
    double.start_sampling()
    packet = double.get_samples(10)
    assert np.array_equal(packet.samples, np.array([
        expected_samples for i in range(10)
    ]))

    for i in range(len(double.active_channels)):
        imp = packet.impedance.for_channel(i)
        if isinstance(imp, np.ndarray):
            assert np.array_equal(imp, np.array([expected_impedances[i]] * 10))
        else:
            assert imp == expected_impedances[i]


def test_perun_double_amplifier():
    amp_ids = DoublePerunAmp.get_available_amplifiers()
    if not amp_ids:
        pytest.skip("No double Perun")
    amp = DoublePerunAmp(amp_ids[0])
    amp.start_sampling()
    for s in range(10):
        amp.get_samples(10)
        print("GET SAMPLES")
    amp.stop_sampling()
