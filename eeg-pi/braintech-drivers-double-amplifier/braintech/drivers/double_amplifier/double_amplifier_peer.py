# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
import copy
from itertools import product
from threading import Thread
from typing import Optional, List

from  braintech.drivers.perun8.amplifiers import PerunCppAmplifier
from braintech.drivers.perun32.amplifier import Perun32Amplifier
from braintech.drivers.double_amplifier.event_tag_sender import EventTagSender
from braintech.obci.core.drivers.eeg.eeg_amplifier import EEGAmplifier, AmplifierDescription, AmplifierException, ChannelDescription
from braintech.obci.core.drivers.eeg.random_amplifier import RandomAmplifier
from braintech.obci.experiment.peers.drivers.amplifiers.amplifier_peer import AmplifierPeer, register_amplifier_peer
from braintech.obci.signal_processing.signal.containers import Impedance
from braintech.obci.signal_processing.signal.data_generic_write_proxy import SamplePacket

from .sample_aligner import SampleAligner, SampleMerger

class DoubleAmplifier(EEGAmplifier):
    MASTER_AMPLIFIER_CLASS = RandomAmplifier
    OTHER_AMPLIFIER_CLASS = RandomAmplifier
    _descriptions = {}

    @classmethod
    def get_available_amplifiers(cls, device_type: Optional[str] = None) -> List[str]:
        master = cls.MASTER_AMPLIFIER_CLASS.get_available_amplifiers(device_type)
        if master:
            other = cls.OTHER_AMPLIFIER_CLASS.get_available_amplifiers(device_type)
        if master and other:
            return ["%s and %s" % (master_id, other_id) for master_id, other_id in product(master, other)]
        return []

    @classmethod
    def _merge_descriptions(cls, master_desc: AmplifierDescription, other_desc: AmplifierDescription):
        merged_desc = copy.deepcopy(master_desc)
        other_channels = copy.deepcopy(other_desc.channels)
        merged_desc.channels.extend(other_channels)
        names = set()
        merged_desc.sampling_rates = sorted(set(master_desc.sampling_rates) and set(other_desc.sampling_rates))
        for i, ch in enumerate(merged_desc.channels):
            ch.index = i
            ch.source_amplifier = 0 if i < len(master_desc.channels) else 1
            ch.name = cls._amp_channel_name(ch.name, ch.source_amplifier)
        for i in range(2):
            ch_desc = ChannelDescription("Timestamp_%d" % i, impedance=Impedance.NOT_APPLICABLE)
            ch_desc.source_amplifier = -2 + i
            ch_desc.index = len(merged_desc.channels)
            merged_desc.channels.append(ch_desc)
        return merged_desc

    @classmethod
    def _strip_ch_name(cls, name):
        return name.split('-')[0]

    @classmethod
    def _amp_channel_name(cls, name, source_amplifier):
        return name + "-%d" % source_amplifier

    @classmethod
    def get_description(cls, id: Optional[str] = None) -> AmplifierDescription:
        if id in cls._descriptions:
            return cls._descriptions[id]
        master_id, other_id = cls._split_ids(id)
        description = cls._merge_descriptions(
            cls.MASTER_AMPLIFIER_CLASS.get_description(master_id),
            cls.OTHER_AMPLIFIER_CLASS.get_description(other_id)
        )
        description.name = id
        cls._descriptions[id] = description
        return description

    @classmethod
    def _split_ids(cls, id):
        try:
            master_id, other_id = id.split(' and ')
        except Exception:
            raise AmplifierException("Amplifier not found: %s" % id)
        return master_id, other_id

    def __init__(self, id: Optional[str] = None):
        super().__init__(id)
        master_id, other_id = self._split_ids(id)
        self._master = self.MASTER_AMPLIFIER_CLASS(master_id)
        self._other = self.OTHER_AMPLIFIER_CLASS(other_id)
        self._amplifiers = [self._master, self._other]

    def start_sampling(self):
        super().start_sampling()
        active_channels = self.get_active_channels()
        sorted_channels = sorted(active_channels, key=lambda ch: (ch.source_amplifier, ch.index))
        impedance_channels = [ch for ch in sorted_channels if ch.impedance == Impedance.PRESENT]
        self._indexes = [sorted_channels.index(ch) for ch in active_channels]
        self._impedance_indexes = [
            impedance_channels.index(ch) for ch in active_channels if ch.impedance == Impedance.PRESENT
        ]

        for amp_index, amp in enumerate(self._amplifiers):
            amp.sampling_rate = self.sampling_rate
            amp.active_channels = [self._strip_ch_name(ch.name) for ch in sorted_channels if
                                   ch.source_amplifier == amp_index]
            amp.start_sampling()
        self._sample_aligner = SampleAligner(self.sampling_rate)
        timestamp_channels = [ch.source_amplifier for ch in sorted_channels if ch.source_amplifier < 0]
        self._sample_merger = SampleMerger(sample_aligner=self._sample_aligner,
                                           prepend_ts=(-2 in timestamp_channels, -1 in timestamp_channels))
        self._other_sampling_thread = Thread(target=self._get_other_samples,
                                             name="DoublePerunAmp-" + self._split_ids(self._id)[1], daemon=True)
        self._other_sampling_thread.start()
        self._ready_samples = []

    def _get_other_samples(self):
        while self.is_sampling:
            sample_packet = self._other.get_samples(1)
            self._sample_merger.put_other(sample_packet)

    def stop_sampling(self):
        super().stop_sampling()
        for amp_index, amp in enumerate(self._amplifiers):
            amp.stop_sampling()

    def get_samples(self, samples_per_packet) -> SamplePacket:
        while self._sample_merger.samples_available < samples_per_packet:
            missing = samples_per_packet - self._sample_merger.samples_available
            master_samples = self._master.get_samples(missing)
            self._sample_merger.put_master(master_samples)
        result = self._sample_merger.get_sample_packet(samples_per_packet)
        return SamplePacket(
            result.samples[:, self._indexes],
            result.ts,
            Impedance(self._impedance_flags, result.impedance.data[:, self._impedance_indexes])
        )

    def _wait(self, samples: Optional[int] = 1):
        pass


class DoublePerunAmp(DoubleAmplifier):
    MASTER_AMPLIFIER_CLASS = PerunCppAmplifier
    OTHER_AMPLIFIER_CLASS = Perun32Amplifier

    @classmethod
    def _merge_descriptions(cls, master_desc: AmplifierDescription, other_desc: AmplifierDescription):
        description = super()._merge_descriptions(master_desc, other_desc)
        excluded_channels = ["RSSI", "Dongle Timestamp", "PC Timestamp",
                             "Head Timestamp", "Sample_Counter"]
        description.channels = [ch for ch in description.channels if ch.name not in excluded_channels]
        return description

    def start_sampling(self):
        self._master.measure_impedance = True
        self._other.measure_impedance = False
        super(DoublePerunAmp, self).start_sampling()

    @classmethod
    def _amp_channel_name(cls, name, source_amplifier):
        return name


@register_amplifier_peer
class DoublePerunAmpAmplifierPeer(AmplifierPeer):
    AmplifierClass = DoublePerunAmp

    def start_sampling(self):
        super().start_sampling()
        self._tag_sender = EventTagSender(self, [ch.name for ch in self._amplifier.get_active_channels()])

    def stop_sampling(self):
        super().stop_sampling()
        self._tag_sender.stop()

    async def _get_packet(self):
        packet = await super()._get_packet()
        if packet is not None:
            self._tag_sender.send_events(packet)
        return packet
