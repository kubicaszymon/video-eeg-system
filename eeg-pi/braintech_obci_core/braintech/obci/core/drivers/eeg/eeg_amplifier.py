# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import copy
import time
from threading import Event
from typing import Optional, Sequence, Union, Tuple, List

from braintech.obci.core.broker import ObciException
from braintech.obci.signal_processing.signal.data_generic_write_proxy import SamplePacket, Impedance
from braintech.obci.core.utils import is_windows
from braintech.obci.core.utils.properties import cached_property


# note: SamplePacket is imported from many places from here.


class AmplifierException(ObciException):
    pass


class AmplifierNotStarted(AmplifierException):
    pass


class NoSamplesException(AmplifierException):
    pass


class SamplingRateNotAvailable(AmplifierException):
    pass


class ChannelDescription:
    def __init__(self, name: str,
                 gain: float = 1.0,
                 offset: float = 0.0,
                 filters: List[dict] = (),
                 impedance=Impedance.UNKNOWN,
                 **other_params):
        """
        Represents one channel
        """
        self.name = name
        self.gain = float(gain)
        self.offset = float(offset)
        self.idle = 0
        self.index = None
        self.filters = filters
        self.impedance = impedance
        for k, v in other_params.items():
            setattr(self, k, v)

    def info(self):
        return {key: getattr(self, key) for key in ('name', 'gain', 'offset', 'idle', 'filters', 'impedance')}

    def __repr__(self):
        return '<ChannelDescription: {} {}>'.format(self.index, self.name)


class AmplifierDescription:
    UNKNOWN = 'unknown'
    ALL = 'all'
    VARIABLE = 'variable'

    @staticmethod
    def from_dict(dict):
        channels = []
        for ch in dict['channels']:
            channels.append(ChannelDescription(**ch))
        return AmplifierDescription(name=dict['name'],
                                    sampling_rates=dict['sampling_rates'],
                                    channels=channels,
                                    physical_channels=dict['physical_channels'],)

    def __init__(self, name: str,
                 sampling_rates: Union[Sequence[float], str],
                 channels: Union[Sequence[ChannelDescription], str],
                 physical_channels: Optional[int] = None,
                 sample_type: Optional[str] = 'FLOAT'):
        """
        Represents amplifier capabilities
        :param sampling_rates: Sampling rates that this amplifier can produce
        :param channels: List of channels descriptions
        """
        self.name = name
        assert sampling_rates in [AmplifierDescription.ALL, AmplifierDescription.VARIABLE] or len(sampling_rates)
        self.sampling_rates = sampling_rates
        assert channels == AmplifierDescription.UNKNOWN or len(channels)
        if channels == AmplifierDescription.UNKNOWN:
            channels = []
        self.channels = channels
        self.sample_type = sample_type
        for i, ch in enumerate(channels):
            if ch.index is None:
                ch.index = i
        self.physical_channels = physical_channels or 0

    def get_channels(self, name_list: Sequence[str]) -> List[ChannelDescription]:
        by_name = {ch.name: ch for ch in self.channels}
        result = []
        for name in name_list:
            if name in by_name:
                result.append(by_name[name])
            elif isinstance(name, int) or name.isdigit():
                result.append(self.channels[int(name)])
            else:
                raise AmplifierException("No such channel: {}".format(name))
        return result

    @property
    def channel_gains(self) -> Tuple[float]:
        return tuple(ch.gain for ch in self.channels)

    @property
    def channel_offsets(self) -> Tuple[float]:
        return tuple(ch.offset for ch in self.channels)

    @property
    def channels_info(self) -> List[dict]:
        return [ch.info() for ch in self.channels]

    @property
    def channel_names(self) -> List[str]:
        return tuple(ch.name for ch in self.channels)

    @channel_names.setter
    def channel_names(self, new_names):
        assert len(new_names) == len(self.channels)
        for ch, new_name in zip(self.channels, new_names):
            ch.name = new_name

    def replace(self, **kwargs):
        desc = copy.copy(self)
        for key, val in kwargs.items():
            setattr(desc, key, val)
        return desc

    def to_dict(self) -> dict:
        """
        Returns dict as required for driver discovery
        :return: dict with amplifier parameters
        """
        d = {'name': self.name,
             'physical_channels': self.physical_channels,
             'channels': self.channels_info
             }
        if self.sampling_rates in [AmplifierDescription.ALL, AmplifierDescription.VARIABLE]:
            d['sampling_rates'] = [float(i) for i in [128, 256, 500, 512, 1024, 2048]]
        else:
            d['sampling_rates'] = [float(i) for i in self.sampling_rates]
        return d

    def __repr__(self):
        string = '<{}: {}>'.format(self.__class__.__name__, str(self.to_dict()))
        return string

    def is_sampling_rate_valid(self, sampling_rate):
        return self.sampling_rates == AmplifierDescription.ALL or sampling_rate in self.sampling_rates

    @property
    def ch_num(self):
        return len(self.channels)


_MIN_SLEEP_TIME = 0.015 if is_windows() else 0.002


class EEGAmplifier:
    _description = None
    DESCRIPTION_LIST = [AmplifierDescription.UNKNOWN, AmplifierDescription.ALL, AmplifierDescription.VARIABLE]
    sample_type = 'FLOAT'

    @classmethod
    def get_available_amplifiers(cls, device_type: Optional[str] = None) -> List[str]:
        """Returns how many amplifiers of this type are available in this system."""
        return []

    @classmethod
    def get_description(cls, id: Optional[str] = None) -> AmplifierDescription:
        """Get description of an amplifier with given id"""
        return cls._description

    def __init__(self, id: Optional[str] = None):
        """
        Base class for signal amplifiers.
        """
        self._id = id
        self._indexes = None
        self._sleep_time = 0
        self._sampling_rate = None
        if not isinstance(self.description, AmplifierDescription):
            raise NotImplementedError("self.description is invalid")

        try:
            if self._description.sampling_rates not in self.DESCRIPTION_LIST:
                self.sampling_rate = self._description.sampling_rates[0]

        except (TypeError, AttributeError):
            # sampling_rates not defined
            pass
        self._impedance_flags = []
        self._is_sampling = False
        self._next_sample_time = None
        self.__wait_lock = Event()
        self.active_channels = self.description.channel_names

    @property
    def sampling_rate(self) -> float:
        return self._sampling_rate

    @sampling_rate.setter
    def sampling_rate(self, sampling_rate: float):
        if not self.description.is_sampling_rate_valid(sampling_rate):
            raise SamplingRateNotAvailable
        self._sleep_time = 1.0 / sampling_rate
        self._sampling_rate = sampling_rate
        del self.current_description
        self._sampling_rate_set(sampling_rate)

    def _sampling_rate_set(self, sampling_rate):
        # to be implemented when needed
        pass

    @property
    def active_channels(self) -> Sequence[str]:
        """List of active channel names"""
        return self._active_channels

    @active_channels.setter
    def active_channels(self, active_channels):
        if self.is_sampling and not active_channels:
            raise AmplifierException("Active channels cannot be empty while amplifier is sampling")
        # validate channels
        self.description.get_channels(active_channels)
        self._active_channels = active_channels
        del self.current_description

        if active_channels != self.description.channel_names:
            self._indexes = [ch.index for ch in self.get_active_channels()]
        else:
            self._indexes = None

        self._impedance_flags = [ch.impedance for ch in self.get_active_channels()]
        self._active_channels_set(active_channels)

    def _active_channels_set(self, active_channels):
        # to be implemented when needed
        pass

    @property
    def description(self) -> AmplifierDescription:
        if self._description is None:
            self._description = self.get_description(self._id)
        return self._description

    @cached_property
    def current_description(self) -> AmplifierDescription:
        return self._get_current_description()

    def _get_current_description(self):
        description = self.description
        return description.replace(sampling_rates=[self.sampling_rate],
                                   channels=description.get_channels(self.active_channels))

    @property
    def is_sampling(self) -> bool:
        return self._is_sampling

    def get_active_channels(self) -> List[ChannelDescription]:
        return self.current_description.channels

    def start_sampling(self):
        if self.sampling_rate is None:
            raise AmplifierException("Sampling rate not set!")
        if len(self.active_channels) == 0:
            raise AmplifierException("No active channels set!")
        self._is_sampling = True
        self._next_sample_time = None

    def stop_sampling(self):
        self._is_sampling = False

    def _wait(self, samples: Optional[int] = 1) -> None:
        current_time = time.time()
        if self._next_sample_time:
            self._next_sample_time = self._next_sample_time + self._sleep_time * samples
        else:
            self._next_sample_time = current_time
        sleep_time = self._next_sample_time - current_time
        if sleep_time >= _MIN_SLEEP_TIME:
            time.sleep(sleep_time)

    def _get_data(self, generator, wait_duration):
        if not self._is_sampling:
            raise AmplifierNotStarted("Amplifier is not sampling")
        data = generator()
        self._wait(wait_duration)
        return data

    def get_samples(self, samples_per_packet=1) -> SamplePacket:
        """
        Returns packet of multiple samples as defined in samples_per_packet
        """
        return self._get_data(lambda: self._get_samples(samples_per_packet), samples_per_packet)

    def _get_samples(self, samples_per_packet) -> SamplePacket:
        raise NotImplementedError()

    def _reindex_samples(self, samples):
        """Reorders samples according to user decided ordering and hides which needed.
        """
        if self._indexes:
            return samples[:, self._indexes]
        return samples

    def __del__(self):
        self.stop_sampling()
