# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Module providing base amplifier Peer."""
import asyncio
import threading
from asyncio import CancelledError
from typing import Optional

import janus

from braintech.obci.core.broker import messages, peer
from braintech.obci.core.broker.asyncio_task_manager import ShuttingDownException
from braintech.obci.experiment.peer.configured_peer import ConfiguredPeer
from braintech.obci.core.drivers.eeg.eeg_amplifier import EEGAmplifier, AmplifierNotStarted, AmplifierDescription, \
    NoSamplesException, SamplingRateNotAvailable
from braintech.obci.signal_processing.signal.containers import SamplePacket
from braintech.obci.core.utils import streaming_debug
from braintech.obci.core.utils.properties import param_property, join_strings, split_string, split_floats, noop

NOT_SAMPLING_CHECK_INTERVAL = 0.05

SIGNAL_SOURCES = []


def register_amplifier_peer(AmplifierPeerClass):
    SIGNAL_SOURCES.append(AmplifierPeerClass)
    return AmplifierPeerClass


class BaseAmplifierPeer(peer.Peer):
    """Base class for all classes which interact with amplifiers."""
    MANUAL_READY = True
    AmplifierClass = EEGAmplifier
    msg_type = messages.SignalMessage

    def __init__(self, *args, config=None, **kwargs):
        """Initialize AmplifierPeer peer."""
        self._amplifier = None  # will be created in _connections_established
        self._amplifier_lock = threading.Lock()
        self._finish_sampling_thread = False
        if config:
            self._set_static_parameters(config)
        super().__init__(*args, **kwargs)

    def _set_static_parameters(self, config):
        def _deserialize_list(items: str, deserializer):
            return [deserializer(i) for i in items.split(';')]

        self.amplifier_id = config['amplifier_id']
        self.channel_names = _deserialize_list(config['channel_names'], str)
        self.active_channels = _deserialize_list(config['active_channels'], str)
        self.channel_gains = _deserialize_list(config['channel_gains'], float)
        self.channel_offsets = _deserialize_list(config['channel_offsets'], float)
        self._sampling_rate = int(config['sampling_rate'])
        self._sampling_rates = _deserialize_list(config['sampling_rates'], int)
        self.samples_per_packet = int(config['samples_per_packet'])
        self.sample_type = config['sample_type']
        self.channels_info = config['channels_info']

    async def _initialized(self):
        if self._amplifier is None:
            await self._setup_amplifier()
        self._samples_q = janus.Queue(loop=self._loop)
        self.create_task(self._do_sampling())  # never ending sample send task
        await super()._initialized()

    async def _setup_amplifier(self):
        with self._amplifier_lock:
            self._amplifier = await self.run_long_operation(self._create_amplifier, self.amplifier_id)
        if self.sampling_rate:
            try:
                self._amplifier.sampling_rate = self.sampling_rate
            except SamplingRateNotAvailable:
                pass
        self._manage_params()

    def _create_amplifier(self, amplifier_id: Optional[str] = None):
        return self.AmplifierClass(amplifier_id)

    @property
    def sampling_rate(self):
        return self._sampling_rate

    @sampling_rate.setter
    def sampling_rate(self, s_r):
        self._amplifier.sampling_rate = s_r
        self._sampling_rate = s_r

    @property
    def sampling_rates(self):
        return self._sampling_rates

    @sampling_rates.setter
    def sampling_rates(self, sampling_rates):
        if sampling_rates == AmplifierDescription.ALL:
            sampling_rates = [128, 256, 512, 1024, 2048]
        elif sampling_rates == AmplifierDescription.UNKNOWN:
            sampling_rates = [self.sampling_rate]
        self._sampling_rates = sampling_rates

    def _manage_params(self):
        if not self.active_channels:
            self.active_channels = self._amplifier.description.channel_names
        self._amplifier.active_channels = self.active_channels
        description = self._amplifier.current_description
        if not self.channel_names:
            # channel_names are not defined, so set them from driver
            self.channel_names = self.active_channels
        description.channel_names = self.channel_names
        # set actual data as amplifier is reporting
        for prop in 'sample_type,channel_gains,channel_offsets,channels_info,sampling_rates'.split(','):
            setattr(self, prop, getattr(description, prop))
        self._sampling_rate = self._amplifier.sampling_rate
        if self.samples_per_packet is None:
            self.samples_per_packet = self.get_samples_per_packet(self.sampling_rate)

        self.debug = streaming_debug.Debug(self.sampling_rate,
                                           self._logger,
                                           )

    async def _start(self):
        await super()._start()
        self.start_sampling()

    async def _stop(self):
        self.stop_sampling()
        await super()._stop()

    def start_sampling(self):
        """Start sample pulling thread and start sampling."""
        with self._amplifier_lock:
            if self._amplifier.is_sampling:
                return
            self._finish_sampling_thread = False
            self._sampling_thread = threading.Thread(target=self._sampling_thread_func,
                                                     name=self._thread_name + "SamplingThread")
            self._amplifier.start_sampling()
            self._sampling_thread.start()

    async def _get_packet(self) -> SamplePacket:
        packet = await self._samples_q.async_q.get()
        return packet

    def reset(self):
        """Reset the amplifier."""
        # Reimplement in your own amplifier
        pass

    def stop_sampling(self):
        """Stop sample pulling thread and stop sampling."""
        with self._amplifier_lock:
            if self._amplifier and self._amplifier.is_sampling:
                self._finish_sampling_thread = True
                try:
                    self._sampling_thread.join(5)
                except RuntimeError:
                    pass
                self._sampling_thread = None
                self._amplifier.stop_sampling()
                self._logger.info("Sampling stopped")

    @property
    def is_sampling(self):
        """Return if amplifier is currently sampling."""
        return self._amplifier.is_sampling

    def _sampling_thread_func(self):
        try:
            while not self._finish_sampling_thread:
                try:
                    packet = self._amplifier.get_samples(self.samples_per_packet)
                except NoSamplesException:
                    packet = None
                self._samples_q.sync_q.put_nowait(packet)
                if packet is None or packet.sample_count == 0:
                    return
        except AmplifierNotStarted:
            pass
        except Exception as exc:
            self.create_task(self.panic(exc))

    async def _do_sampling(self):
        """Callback will be called when packet is received."""
        self._logger.info("Sampling started")
        packet = await self._get_packet()
        await self._wait_until_ready()
        try:
            while True:
                try:
                    if packet is not None:
                        msg = self._create_msg(packet)
                        await self._send_message(msg)
                    packet = await self._get_packet()
                except (ShuttingDownException, CancelledError) as e:
                    self.stop_sampling()  # tell amplifier to stop
                    raise e  # raise exception to let task manager close this task
                if packet is None:
                    # do no stop _do_sampling it will wait on _get_packet until amp is restarted or peer is closed
                    self._logger.info("No more samples. Abort amplifier...")
                    self.stop_sampling()
                else:
                    self.debug.next_samples(packet.ts[-1], packet.sample_count)
                await self._post_send()
        finally:
            self.stop_sampling()

    async def _wait_until_ready(self):
        while not self.is_ready:
            await asyncio.sleep(0.05)

    async def _post_send(self):
        pass

    def _create_msg(self, packet):
        return messages.SignalMessage(data=packet)

    @classmethod
    def get_samples_per_packet(cls, sampling_rate):
        return 1 if sampling_rate / 32 < 1 else int(sampling_rate / 32)


class AmplifierPeer(BaseAmplifierPeer, ConfiguredPeer):
    amplifier_id = param_property('amplifier_id')
    samples_per_packet = param_property('samples_per_packet', int)
    _sampling_rate = param_property('sampling_rate', float)
    channel_names = param_property('channel_names', split_string, join_strings)
    active_channels = param_property('active_channels', split_string, join_strings)
    channel_gains = param_property('channel_gains', split_floats, join_strings)
    channel_offsets = param_property('channel_offsets', split_floats, join_strings)
    _sampling_rates = param_property('sampling_rates', serializer=noop)
    sample_type = param_property('sample_type')
    channels_info = param_property('channels_info', serializer=noop)

    async def register_config(self):
        """Finalize the set of configuration parameters and send them to Broker."""
        await self._setup_amplifier()
        await super().register_config()

    def _manage_params(self):
        super()._manage_params()
        self.set_param('amplifier_name', self._amplifier.description.name)  # Svarog can see this

    async def _wait_until_ready(self):
        # Wait until peer is ready and then inform broker about it.
        await super()._wait_until_ready()
        await self.ready()
