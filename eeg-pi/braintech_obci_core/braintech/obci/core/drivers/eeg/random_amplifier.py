# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import time
from typing import Optional, List

import numpy

from braintech.obci.core.drivers.eeg.eeg_amplifier import AmplifierDescription, ChannelDescription, EEGAmplifier
from braintech.obci.signal_processing.signal.data_generic_write_proxy import Impedance, SamplePacket


class RandomAmplifier(EEGAmplifier):
    name = "RandomAmplifier"
    _description = AmplifierDescription(name, AmplifierDescription.ALL, AmplifierDescription.UNKNOWN)

    @classmethod
    def get_available_amplifiers(cls, device_type: Optional[str] = None) -> List[str]:
        if device_type is None or device_type == 'virtual' and cls._description:
            return [cls.name]
        return []

    @classmethod
    def get_description(cls, id: Optional[str] = None) -> AmplifierDescription:
        if id is None or id == cls.name:
            return cls()._description
        raise Exception('Invalid amplifier id.')

    def __init__(self, id: Optional[str] = None, channel_names=None, *args, **kwargs):
        if channel_names is None:
            channel_names = ['Random{}'.format(i) for i in range(30)]
        self.next_saw_value = 0
        self.last_counter_value = 0
        self._indexes = None
        self._create_amplifier_description(channel_names)
        super().__init__(*args, **kwargs)

    def _create_amplifier_description(self, channel_names):
        self._description = AmplifierDescription(
            name=self._description.name,
            sampling_rates=self._description.sampling_rates,
            channels=(
                self._get_random_channels_descriptions(channel_names) + self._get_standard_channels_descriptions()),
        )
        del self.current_description

    def _get_standard_channels_descriptions(self) -> List[ChannelDescription]:
        return [
            ChannelDescription(
                name=channel_name,
                impedance=Impedance.NOT_APPLICABLE,
                type='ZAAG',
            ) for channel_name in ['Saw', 'Sample_Counter']
        ]

    def _get_random_channels_descriptions(self, channel_names: List[str]) -> List[ChannelDescription]:
        random_channels = []

        for idx, channel_name in enumerate(channel_names):
            if idx % 2:
                channel_description = ChannelDescription(
                    name=channel_name,
                    impedance=Impedance.PRESENT,
                    type='EEG',
                    gain=20.0,
                )
            else:
                channel_description = ChannelDescription(
                    name=channel_name,
                    impedance=Impedance.NOT_APPLICABLE,
                    type='TECH',
                    gain=20.0,
                )

            random_channels.append(channel_description)

        return random_channels

    def _get_samples(self, samples_per_packet) -> SamplePacket:
        all_channel_count = len(self._description.channels)
        assert all_channel_count >= 2
        samples = numpy.random.rand(samples_per_packet, all_channel_count)
        for i in range(samples_per_packet):
            samples[i][-2] = self.next_saw_value  # saw
            if self.next_saw_value == 100:
                self.next_saw_value = 0
            else:
                self.next_saw_value += 1
            self.last_counter_value += 1
            samples[i][-1] = self.last_counter_value  # sample counter
        samples = self._reindex_samples(samples)
        t0 = time.time()
        ts = numpy.linspace(t0, t0 + 1 / self.sampling_rate * samples_per_packet, samples_per_packet)
        impedance = self._get_impedance(samples_per_packet)
        return SamplePacket(ts=ts, samples=samples, impedance=impedance)

    def _get_impedance(self, samples_per_packet) -> Impedance:
        flags = [ch.impedance for ch in self.get_active_channels()]
        impedance_channels = sum(flag == Impedance.PRESENT for flag in flags)
        data = numpy.random.rand(samples_per_packet, impedance_channels) + numpy.arange(impedance_channels)
        return Impedance(ids=flags, data=data)
