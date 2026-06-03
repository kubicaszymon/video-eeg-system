# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import time

import numpy
import pylsl

from braintech.obci.core.drivers.eeg.eeg_amplifier import AmplifierDescription
from braintech.obci.core.drivers.eeg.eeg_amplifier import ChannelDescription
from braintech.obci.core.drivers.eeg.eeg_amplifier import EEGAmplifier
from braintech.obci.signal_processing.signal.data_generic_write_proxy import Impedance
from braintech.obci.signal_processing.signal.data_generic_write_proxy import SamplePacket


USED_STREAM_TYPES = ['signal', 'eeg']
GAIN = 1
OFFSET = 0
IMPEDANCE = Impedance.UNKNOWN

MINDWAVE_STREAM_NAME = 'mindwave'
MINDWAVE_GAIN = ((1.8 / 4096) / 2000) * 1000000
# ^ https://web.archive.org/web/20180509090508/http://openvibe.inria.fr/forum/viewtopic.php?f=5&t=9572

# Channels names fetch from OpenBCI_Python
GANGLION_EEG_STREAM_NAME = 'OpenBCI_EEG'
GANGLION_AUX_STREAM_NAME = 'OpenBCI_AUX'

GANGLION_EEG_GAIN = 1000
GANGLION_AUX_GAIN = 2


class NoLSLStreamAvailable(Exception):
    pass


class RequestedLSLStreamMissing(Exception):
    pass


class MultipleStreamsMatched(Exception):
    pass


class LSLAmplifierAdapter(EEGAmplifier):
    name = "LSLAmplifierAdapter"
    _description = AmplifierDescription(name, AmplifierDescription.ALL,
                                        AmplifierDescription.UNKNOWN)

    @classmethod
    def get_available_amplifiers(cls, device_type: str = None) -> [str]:
        if device_type == 'virtual':
            return list({stream.name() for stream in _get_streams()})
        else:
            return []

    @classmethod
    def get_description(cls, id: str = None) -> AmplifierDescription:
        stream = _get_stream_by_name(id)
        return cls._get_stream_description(stream)

    def __init__(self, id: str = None):
        if id:
            selected_stream = _get_stream_by_name(id)
        else:
            selected_stream = _get_newest_stream()
        self._update_description(selected_stream)
        self._inlet = pylsl.StreamInlet(selected_stream)
        self._time_recounter = TimeConverter(self._inlet)
        super().__init__(id)

    def _update_description(self, selected_stream):
        self._description = self._get_stream_description(selected_stream)
        self.sampling_rate = self._description.sampling_rates[0]
        del self.current_description

    @classmethod
    def _get_stream_description(cls, stream) -> AmplifierDescription:
        if stream.name().lower() == MINDWAVE_STREAM_NAME:
            gain = MINDWAVE_GAIN
        elif stream.name() == GANGLION_EEG_STREAM_NAME:
            gain = GANGLION_EEG_GAIN
        elif stream.name() == GANGLION_AUX_STREAM_NAME:
            gain = GANGLION_AUX_GAIN
        else:
            gain = GAIN
        channels_descriptions = [
            ChannelDescription(label, gain=float(gain), offset=float(OFFSET),
                               impedance=IMPEDANCE)
            for label in _get_channel_names(stream)
        ]
        return AmplifierDescription(
            name=stream.name(),
            sampling_rates=[stream.nominal_srate()],
            physical_channels=stream.channel_count(),
            channels=channels_descriptions,
        )

    def _get_samples(self, samples_per_packet) -> SamplePacket:
        samples, relative_timestamps = self._get_chunk(samples_per_packet)
        samples = samples.reshape((samples_per_packet,
                                   self._inlet.channel_count))
        samples = self._reindex_samples(samples)
        absolute_timestamps = [self._time_recounter.remote_lsl_to_local_unix(ts)
                               for ts in relative_timestamps]
        return SamplePacket(ts=numpy.array(absolute_timestamps),
                            samples=samples)

    def _get_chunk(self, samples_per_packet):
        samples = numpy.empty(samples_per_packet * self._inlet.channel_count,
                              dtype=self._inlet.value_type)
        chunk = self._inlet.pull_chunk(timeout=2,
                                       max_samples=samples_per_packet,
                                       dest_obj=samples)
        _, relative_timestamps = chunk
        return samples, relative_timestamps


def _get_newest_stream():
    streams = _get_streams()
    if streams:
        streams_newest_first = sorted(streams, key=_calculate_creation_time,
                                      reverse=True)
        return streams_newest_first[0]
    else:
        raise NoLSLStreamAvailable


def _calculate_creation_time(stream):
    inlet = pylsl.StreamInlet(stream)
    local_pylsl_time = pylsl.local_clock()
    stream_creation_delta = inlet.info().created_at()
    pylsl_time_difference = inlet.time_correction()
    stream_age = local_pylsl_time - stream_creation_delta - pylsl_time_difference
    local_time = time.time()
    return local_time - stream_age


def _get_stream_by_name(name):
    matching = [stream for stream in _get_streams()
                if stream.name() == name]
    if len(matching) == 0:
        raise RequestedLSLStreamMissing
    elif len(matching) == 1:
        return matching[0]
    else:
        raise MultipleStreamsMatched


def _get_streams():
    return [stream for stream in pylsl.resolve_streams()
            if stream.type().lower() in USED_STREAM_TYPES]


def _get_channel_names(stream):
    inlet = pylsl.StreamInlet(stream)
    info = inlet.info()
    channel = info.desc().child("channels").child("channel")
    for idx in range(1, info.channel_count() + 1):
        yield channel.child_value("label") or channel.child_value("name") or 'ExG{}'.format(idx)
        channel = channel.next_sibling()
    inlet.close_stream()


class TimeConverter:
    def __init__(self, inlet):
        self._inlet = inlet
        self._consume_first_long_time_correcton_execution()
        self._start_unix_time = time.time()
        self._start_local_lsl_time = pylsl.local_clock()

    def _consume_first_long_time_correcton_execution(self):
        self._inlet.time_correction()

    def remote_lsl_to_local_unix(self, lsl_time_there):
        local_lsl = self._remote_lsl_to_local_lsl(lsl_time_there)
        return self._local_lsl_to_local_unix(local_lsl)

    def _remote_lsl_to_local_lsl(self, lsl_time_there):
        return lsl_time_there + self._inlet.time_correction()

    def _local_lsl_to_local_unix(self, lsl_time_here):
        current_unix_time = time.time()
        elapsed_unix_time = current_unix_time - self._start_unix_time
        current_lsl_time = pylsl.local_clock()
        lsl_elapsed_here = current_lsl_time - self._start_local_lsl_time
        if lsl_elapsed_here:
            lsl_elapsed_there = lsl_time_here - self._start_local_lsl_time
            requested_lsl_elapsed_ratio = lsl_elapsed_there / lsl_elapsed_here
            requested_unix_elapsed_time = requested_lsl_elapsed_ratio * elapsed_unix_time
            return self._start_unix_time + requested_unix_elapsed_time
        else:
            return self._start_unix_time
