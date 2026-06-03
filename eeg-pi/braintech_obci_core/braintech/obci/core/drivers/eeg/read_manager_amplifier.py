# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import numpy
import time

from braintech.obci.signal_processing import read_manager
from .eeg_amplifier import EEGAmplifier, AmplifierDescription, ChannelDescription, SamplePacket, NoSamplesException


class ReadManagerAmplifier(EEGAmplifier):
    _description = AmplifierDescription('ReadManagerAmplifier',
                                        AmplifierDescription.UNKNOWN,
                                        AmplifierDescription.UNKNOWN)

    def __init__(self, p_info_source=None, p_data_source=None, p_tags_source=None):
        super().__init__()
        self.info_source = p_info_source
        self.data_source = p_data_source
        self.tags_source = p_tags_source
        self._mgr = None
        self._samples_iter = None
        self._tags = None
        self._tag_ind = 0
        self._ind = 0
        self._first_sample_timestamp = None

    def init(self):
        self._mgr = mgr = read_manager.ReadManager(self.info_source, self.data_source, self.tags_source)
        channel_info = (mgr.get_param('channels_names'),
                        mgr.get_param('channels_gains'),
                        mgr.get_param('channels_offsets'))
        sample_type = mgr.get_param('sample_type')
        channels = tuple(ChannelDescription(name, float(gain), float(offset), type=sample_type)
                         for name, gain, offset in zip(*channel_info))
        self._description = AmplifierDescription(self.info_source,
                                                 [float(self._mgr.get_param('sampling_frequency'))],
                                                 channels,
                                                 sample_type=mgr.get_param('sample_type'))
        self.active_channels = self.description.channel_names
        self.sampling_rate = self._description.sampling_rates[0]

        self._samples_iter = self._mgr.iter_samples()
        tags = self._mgr.get_tags()
        for tag in tags:
            tag['start_timestamp'] = int(tag['start_timestamp'] * self.sampling_rate)
            tag['end_timestamp'] = int(tag['end_timestamp'] * self.sampling_rate)
        self._tags = tags
        self._tag_ind = 0
        self._ind = 0
        self._first_sample_timestamp = None

    @property
    def duration(self):
        return float(self._mgr.get_param('number_of_samples')) / float(self.sampling_rate)

    def start_sampling(self):
        if self._mgr is None:
            self.init()
        super().start_sampling()

    def _get_samples(self, samples_per_packet) -> numpy.ndarray:
        try:
            samples = numpy.array([next(self._samples_iter) for _ in range(samples_per_packet)])
        except StopIteration:
            raise NoSamplesException()
        samples = self._reindex_samples(samples)
        if len(samples):
            if self._first_sample_timestamp is None:
                self._first_sample_timestamp = time.time()
            timestamp = self._first_sample_timestamp + self._ind / self.sampling_rate
            sample_count, _ = samples.shape
            ts = numpy.linspace(
                timestamp,
                timestamp + float(len(samples)) / self.sampling_rate,
                sample_count,
                endpoint=False,
            )
            self._ind += len(samples)
            return SamplePacket(samples=samples, ts=ts)
        else:
            raise NoSamplesException()

    def get_tags(self):
        """
        should be run after with :meth:_get_samples
        :return: list of tags which happened since last get_tags call
        """
        now = self._ind
        tags_to_send = []
        for i in self._tags[self._tag_ind:]:
            if i['start_timestamp'] <= now:
                tagout = i.copy()
                tagout['start_timestamp'] = (
                    tagout['start_timestamp'] / self.sampling_rate
                    + self._first_sample_timestamp
                )
                tagout['end_timestamp'] = (
                    tagout['end_timestamp'] / self.sampling_rate
                    + self._first_sample_timestamp
                )
                tags_to_send.append(tagout)
                self._tag_ind += 1
            else:
                break
        return tags_to_send
