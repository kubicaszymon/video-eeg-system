# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""
Module providing Signal Saver for EEG amplifiers.

 Author:
     Mateusz Kruszyński <mateusz.kruszynski@titanis.pl>
"""
import time
from collections import namedtuple

from braintech.obci.core.broker import messages
from braintech.obci.experiment.peer.configured_peer import ConfiguredPeer, SignalReceiverMixin
from braintech.obci.core.broker.message_handler_mixin import subscribe_message_handler
from braintech.obci.core.broker.peer import Peer, HeartbeatDisablerMixin
from braintech.obci.signal_processing import writers as signal_writers
from braintech.obci.core.utils.properties import (
    param_property, join_strings, split_string, split_floats, extract_path,
    bool_property)

__all__ = ('SignalSaver',)


class SignalSaverPeerMixin(SignalReceiverMixin, Peer):
    """Saves signal from given amplifier."""
    FILE_EXTENSIONS = signal_writers.SignalWriter.FILE_EXTENSIONS

    def __init__(self, urls, *args, **kwargs):
        """Initialize SignalSaver peer."""
        super().__init__(urls, *args, **kwargs)
        self._session_is_active = False
        self._signal_writer = None

    async def _start(self):
        await super()._start()
        self._init_saving_session()

        if self.debug_on:
            from braintech.obci.core.utils import streaming_debug
            self.debug = streaming_debug.Debug(self.freq,
                                               self._logger,
                                               )
        self._session_is_active = True

    async def _stop(self):
        await self._finish_saving_session()
        await super()._stop()

    async def _signal_message_handler(self, msg):
        if self._session_is_active:
            packet = msg.data
            is_this_first_packet = self._signal_writer.first_sample_timestamp is None
            if is_this_first_packet:
                self._set_first_timestamp(packet)
                self._signal_writer.impedance_flags = packet.impedance.flags

            if not (len(packet.ts) == packet.sample_count == self._samples_per_packet):
                raise Exception("Received sample is not of a good size. Writing aborted!")

            self._signal_writer.write(
                sample_packet=msg.data,
                samples_count=self._samples_per_packet,
            )

            if self.debug_on:
                # Log module real sampling rate
                self.debug.next_samples(count=packet.sample_count)

    def _set_first_timestamp(self, packet):
        first_sample_timestamp = packet.ts[0]
        self._logger.info("REAL SAMPLES PER PACKET: %s ", packet.sample_count)
        self._logger.info("First sample sample ts: %s", first_sample_timestamp)
        self._logger.info("First sample system ts: %s", time.time())
        self._logger.info("REAL NUM OF CHANNELS: %s", packet.channel_count)
        self._signal_writer.first_sample_timestamp = first_sample_timestamp

    async def _handle_tag(self, msg: messages.TagMsg):
        if self._session_is_active:
            l_tag = msg.data_dict
            self._logger.info(''.join(['Tag saver got tag: ',
                                       'start_timestamp:',
                                       repr(l_tag['start_timestamp']),
                                       ', end_timestamp: ',
                                       repr(l_tag['end_timestamp']),
                                       ', name: ',
                                       l_tag['name'],
                                       '. <Change debug level to see desc.>']))

            self._logger.debug("Signal saver got tag: " + str(l_tag))
            self._signal_writer.add_tag(l_tag)

    @subscribe_message_handler(messages.AcquisitionControlMessage)
    async def _acquisition_control_message_handler(self, msg):
        ctr = msg.data
        if ctr == 'finish':
            self._logger.info("Signal saver got finish saving _message.")
            self._logger.info("Last sample ts ~ " + repr(time.time()))
            await self._stop()

    def _init_saving_session(self):
        """Start storing data..."""
        if self._session_is_active:
            self._logger.error(
                "Attempting to start saving signal to file while not closing previously opened file!")
            return

        self._signal_writer = signal_writers.SignalWriter(
            active_channels=self.ch_nums,
            sampling_rate=self.freq,
            channel_names=self.ch_names,
            channel_gains=self.ch_gains,
            channel_offsets=self.ch_offsets,
            save_file_path=str(self.l_f_dir),
            save_file_name=str(self.l_f_name),
            append_timestamps=bool(self.append_ts),
            use_own_buffer=bool(self.use_own_buffer),
            save_tags=bool(self.save_tags),
            save_impedance=bool(self.save_impedance),
            sample_type=self.sample_type,
            channels_info=self.ch_info,
            file_extensions=self.FILE_EXTENSIONS,
        )

        if self.save_tags:
            self.subscribe_for_all_msg_subtype(messages.TagMsg, self._handle_tag)

    async def _finish_saving_session(self):
        """Save info and tags file.

        Also perform finish_saving_info and _tags on data_proxy - it might be a long operation...
        """
        if not self._session_is_active:
            self._logger.error("Attempting to stop saving signal to file while no file being opened!")
            return
        self._session_is_active = False
        await self._loop.run_in_executor(None, self._signal_writer.finish_saving_signal)

        self._logger.info("Signal files have been saved.")
        if self.save_tags:
            self.unsubscribe_message_handler(messages.TagMsg)

    async def _shutting_down(self):
        """Shutdown saver (while finalizing saving)."""
        if self._session_is_active:
            await self._finish_saving_session()
        await super()._shutting_down()

    @property
    def signal_saving_session_active(self):
        return self._session_is_active


class SignalSaver(SignalSaverPeerMixin, ConfiguredPeer):
    append_ts = param_property('append_timestamps', int)

    use_own_buffer = param_property('use_own_buffer', int)

    save_impedance = param_property('save_impedance', int)

    _samples_per_packet = param_property('samples_per_packet', int)

    # external params
    freq = param_property('sampling_rate', float)

    sample_type = param_property('sample_type')

    l_f_name = param_property('save_file_name')

    l_f_dir = param_property('save_file_path', extract_path)

    save_tags = param_property('save_tags', int)

    ch_info = param_property('channels_info')

    ch_nums = param_property('active_channels', split_string, join_strings)

    ch_names = param_property('channel_names', split_string, join_strings)

    ch_gains = param_property('channel_gains', split_floats, join_strings)

    ch_offsets = param_property('channel_offsets', split_floats, join_strings)

    debug_on = bool_property('debug_on')

    is_essential = bool_property('is_essential')


SaverConfig = namedtuple('SaverConfig', ('append_ts',
                                         'save_impedance',
                                         'save_file_name',
                                         'save_file_path',
                                         'save_tags',
                                         'amp_params',
                                         )
                         )


class PanicNotificationMixin:
    async def panic(self, exc=None):
        self.panic_reason = exc
        await super().panic(exc)

    @property
    def is_failed(self):
        try:
            self.panic_reason
            return True
        except AttributeError:
            return False


class LiteSignalSaverPeer(HeartbeatDisablerMixin, PanicNotificationMixin, SignalSaverPeerMixin, Peer):
    is_essential = False

    def __init__(self, urls, saver_config: SaverConfig, *args, **kwargs):
        class LiteSaverMockConfig:
            launch_deps = ['signal_source']

            def get_param(self, x):
                return "amplifier"

        self.append_ts = saver_config.append_ts
        self.use_own_buffer = False
        self.save_impedance = saver_config.save_impedance
        self._samples_per_packet = int(saver_config.amp_params['samples_per_packet'])
        self.freq = float(saver_config.amp_params['sampling_rate'])
        self.sample_type = saver_config.amp_params['sample_type']
        self.l_f_name = saver_config.save_file_name
        self.l_f_dir = saver_config.save_file_path
        self.save_tags = saver_config.save_tags
        self.ch_info = saver_config.amp_params['channels_info']
        self.ch_nums = split_string(saver_config.amp_params['active_channels'])
        self.ch_names = split_string(saver_config.amp_params['channel_names'])
        self.ch_gains = split_floats(saver_config.amp_params['channel_gains'])
        self.ch_offsets = split_floats(saver_config.amp_params['channel_offsets'])
        self.debug_on = True
        self.config = LiteSaverMockConfig()
        super().__init__(urls, *args, **kwargs)
