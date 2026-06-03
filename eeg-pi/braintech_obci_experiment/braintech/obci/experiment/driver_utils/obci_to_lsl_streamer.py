import sys
import time
from typing import List

import numpy
import pylsl
from braintech.obci.experiment.error_reporting import install_sentry
from numpy import ascontiguousarray
from pylsl import StreamInfo, StreamOutlet, local_clock

from argparse import ArgumentParser
from traceback import print_exc
from braintech.obci.experiment.driver_utils.driver_discovery import get_amp_classes_defs
from braintech.obci.experiment.peers.drivers.amplifiers.amplifier_peer import BaseAmplifierPeer

from braintech.obci.core.drivers.eeg.eeg_amplifier import ChannelDescription
from braintech.obci.signal_processing.signal.containers import Impedance, SamplePacket


class LSLStreamer:
    def __init__(self, stream_name, sampling_rate, channels: List[ChannelDescription], send_impendace=False):
        self._stream_name = stream_name
        self._sampling_rate = sampling_rate
        self._channels = channels
        self._send_impedance = send_impendace
        self._init_stream()
        self._time_offset = time.time() - local_clock()

    def _init_stream(self):
        channel_count = len(self._channels)

        impedance_channel_count = 0
        if self._send_impedance:
            for c in self._channels:
                if c.impedance == Impedance.PRESENT:
                    impedance_channel_count += 1

        channel_count_to_stream = channel_count + impedance_channel_count

        self._stream_info = StreamInfo(self._stream_name,
                                       type='EEG',
                                       channel_count=channel_count_to_stream,
                                       nominal_srate=self._sampling_rate,
                                       )
        desc = self._stream_info.desc()
        desc.append_child_value("manufacturer", "BrainTech")
        channels = desc.append_child("channels")
        for c in self._channels:
            channel = channels.append_child('channel')
            channel.append_child_value("name", c.name)  # svarog compat
            channel.append_child_value("label", c.name)  # openvibe compat
            channel.append_child_value("unit", 'microvolts')
            channel.append_child_value("type", 'EEG')

        if self._send_impedance:
            for c in self._channels:
                if c.impedance == Impedance.PRESENT:
                    channel = channels.append_child('channel')
                    channel.append_child_value("name", c.name + '_impedance')
                    channel.append_child_value("label", c.name + '_impedance')
                    channel.append_child_value("unit", 'ohms')
                    channel.append_child_value("type", 'impedance')
        self._stream = StreamOutlet(self._stream_info)

    def push_sample_packet(self, packet: SamplePacket, gains, offsets):
        samples_integers = packet.samples
        samples = samples_integers * gains + offsets
        impedances = packet.impedance.data

        last_timestamp = packet.ts[-1]
        timestamp_to_send = last_timestamp - self._time_offset

        if self._send_impedance:
            data_to_send = numpy.concatenate((samples, impedances), axis=1)
        else:
            data_to_send = samples

        # sends numpy arrays(channels, samples), uses only timestamp of last sample
        self._stream.push_chunk(ascontiguousarray(data_to_send).astype(numpy.float32), timestamp_to_send)


class ObciLslStreamerException(Exception):
    pass


class WrongAmplifierIDException(ObciLslStreamerException):
    pass


class WrongChannelsException(ObciLslStreamerException):
    pass


class WrongSamplingRateException(ObciLslStreamerException):
    pass


class NameAlreadyTakenException(ObciLslStreamerException):
    pass


class AmplifierStreamingApp:
    def __init__(self):
        self._setup_cmd()
        amps = self._detect_amps()
        self._amps = amps

    def parse_args_and_run_stream(self, args=None):
        args = self._parser.parse_args(args=args)
        if args.list:
            self.list_amps()
        else:
            self._validate_streaming_args_and_run_stream(args)

    def list_amps(self):
        amp_descs = []
        for id, amp_class in self._amps.items():
            description = amp_class.get_description(id)
            name = description.name
            channels = ' '.join(description.channel_names)
            sampling_rates = description.sampling_rates
            if isinstance(sampling_rates, list):
                sampling_rates = ' '.join([str(i) for i in sampling_rates])
            else:
                sampling_rates = sampling_rates
            info = ('* {}\n'
                    '\tid: "{}"\n'
                    '\tavailable channels: \n'
                    '\t\t{} \n'
                    '\tavailable sampling rates: \n'
                    '\t\t{}').format(
                name, id, channels, sampling_rates
            )

            amp_descs.append(info)

        print("\n\nAvailable amplifiers:")
        for i in sorted(amp_descs):
            print(i)

    def _validate_streaming_args_and_run_stream(self, args):
        amp_id = args.amp_id
        self._validate_amplifier_id(amp_id)

        if args.stream_name is None:
            name = '{} {}'.format(self._amps[amp_id].get_description().name, amp_id)
        else:
            name = args.stream_name

        self._validate_stream_name(name)

        amp_class = self._amps[amp_id]
        amp = amp_class(amp_id)

        sampling_rate = args.sampling_rate
        channels = args.channel_names
        send_impedance = args.send_impedance
        self._validate_amplifier_params(amp, sampling_rate, channels)
        self._stream_amp(amp, channels, sampling_rate, name, send_impedance)

    def _setup_cmd(self):
        parser = ArgumentParser("OBCI LSL Streamer",
                                description="OBCI compatable amplifier streamer to LSL, CTRL-C to stop streaming.")
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument('-a', '--amp-id', help='Amplifier id to stream, as listed in --list')
        group.add_argument('-l', '--list', action='store_true',
                           help='Print available amplifiers and their capabilities')
        parser.add_argument('-c', '--channel-names', nargs='*', default=[],
                            help='Channels to stream, as listed in --list, '
                                 'space seperated')
        parser.add_argument('-n', '--stream-name', default=None, help='LSL stream name')
        parser.add_argument('-s', '--sampling-rate', default=None, type=float,
                            help='Amplifier sampling rate, available sampling rates per '
                                 'amplifier are listed in --list command')
        parser.add_argument('-i', '--send-impedance', action='store_true',
                            help='Append channels which contain impedance of electrodes in kOhms')
        self._parser = parser

    @staticmethod
    def _detect_amps():
        amps = {}
        amp_clases = [i[0] for i in get_amp_classes_defs()]

        for amp_class in amp_clases:
            try:
                for id in amp_class.get_available_amplifiers():
                    amps[id] = amp_class
            except Exception:
                print_exc()
        return amps

    @staticmethod
    def _validate_stream_name(name):
        streams_running = pylsl.resolve_streams()
        for stream in streams_running:
            if name == stream.name():
                raise NameAlreadyTakenException(
                    'Stream name "{}" already taken, please change to another'.format(name))

    def _validate_amplifier_id(self, amp_id):
        if amp_id not in self._amps:
            msg = ('Amplifier ID: "{}" is incorrect. '
                   'Use --list command to check amplifier ids for connected amplifiers').format(
                amp_id)
            raise WrongAmplifierIDException(msg)

    def _validate_amplifier_params(self, amp, sampling_rate, channels):
        available_channels = amp.current_description.channel_names
        if not set(channels).issubset(available_channels):
            bad_channels = []
            for ch in channels:
                if ch not in available_channels:
                    bad_channels.append(ch)
            bad_chanels_str = ', '.join(bad_channels)
            msg = "You've asked to stream non-existing channels: {}".format(bad_chanels_str)
            raise WrongChannelsException(msg)

        available_sampling_rates = amp.current_description.sampling_rates
        if isinstance(available_sampling_rates, list) and available_sampling_rates[0] is not None:
            if (sampling_rate is not None) and (sampling_rate not in available_sampling_rates):
                sampling_rates_str = ', '.join([str(i) for i in available_sampling_rates])
                msg = "Can't set sampling rate {}. Available sampling rates {}".format(sampling_rate,
                                                                                       sampling_rates_str)
                raise WrongSamplingRateException(msg)

    def _stream_amp(self, amp, channels, sampling_rate, name, send_impedance):

        if sampling_rate is None:
            if isinstance(amp.description.sampling_rates, list):
                sampling_rate = amp.description.sampling_rates[0]
            else:
                sampling_rate = 128
        amp.sampling_rate = sampling_rate
        if channels:
            amp.active_channels = channels

        streamer = LSLStreamer(name,
                               sampling_rate,
                               amp.current_description.channels,
                               send_impendace=send_impedance
                               )

        gains = numpy.array([float(i) for i in amp.current_description.channel_gains])[numpy.newaxis, :]
        offsets = numpy.array([float(i) for i in amp.current_description.channel_offsets])[numpy.newaxis, :]

        amp.start_sampling()

        samples_per_packet = BaseAmplifierPeer.get_samples_per_packet(sampling_rate)
        print(
            """

            **********************************
            Started streaming. CTRL-C to stop.
            **********************************

            """
        )
        while True:
            sample_packet = amp.get_samples(samples_per_packet)
            streamer.push_sample_packet(sample_packet, gains, offsets)


def run_lsl_streaming_app(args=None):
    install_sentry()
    app = AmplifierStreamingApp()
    exit_error = ''

    # we want to exit scope, for amp to be destroyed, before printing error message
    # this makes sure all prints coming from amp are finished before printing actual, usefull error message to user
    try:
        app.parse_args_and_run_stream(args=args)
    except ObciLslStreamerException as e:
        exit_error = str(e)
    except KeyboardInterrupt:
        print("\nStopping stream")

    if exit_error:
        print("\nError while starting streaming!", file=sys.stderr)
        print(exit_error, file=sys.stderr)
        sys.exit(151)


if __name__ == '__main__':
    run_lsl_streaming_app()
