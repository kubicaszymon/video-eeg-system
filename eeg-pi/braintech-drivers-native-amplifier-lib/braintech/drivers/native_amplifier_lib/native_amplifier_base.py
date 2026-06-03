# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
import logging
from typing import List, Sequence, Optional

from braintech.drivers.native_amplifier_lib.native_lib._native_lib import PyAmplifier
from braintech.obci.core.drivers.eeg.eeg_amplifier import AmplifierDescription, EEGAmplifier
from braintech.obci.signal_processing.signal.data_generic_write_proxy import Impedance, SamplePacket


class CantConnectToAmplifier(RuntimeError):
    pass


class ConnectionAlreadyMade(RuntimeError):
    pass


class CppEEGAmplifier(EEGAmplifier):
    name = 'CppAmplifier'

    @classmethod
    def _get_cpp_amplifier_class(cls):
        raise NotImplementedError()

    @classmethod
    def get_available_amplifiers(cls, device_type: Optional[str] = None) -> List[str]:
        raise NotImplementedError()

    @classmethod
    def get_description(cls, id: Optional[str] = None) -> AmplifierDescription:
        try:
            amplifier = cls._get_cpp_amplifier(id)
        except RuntimeError as exc:
            raise ConnectionAlreadyMade(
                "Try accesing description from 'current_description' property "
                "on instance.".format(name=cls.name, id=id)
            ) from exc
        else:
            description = amplifier.get_description()
            del amplifier
            return AmplifierDescription.from_dict(description)

    @classmethod
    def _id_to_params(cls, id: Optional[str] = None) -> dict:
        raise NotImplementedError()

    def __init__(self, id: Optional[str] = None):
        try:
            self._cpp_amp = self._get_cpp_amplifier(id)
        except RuntimeError as exc:
            raise CantConnectToAmplifier from exc
        self._description = AmplifierDescription.from_dict(self._cpp_amp.get_description())
        super().__init__(id)

    @property
    def sampling_rate(self) -> int:
        return self._cpp_amp.get_sampling_rate()

    @sampling_rate.setter
    def sampling_rate(self, sampling_rate: int):
        self._cpp_amp.set_sampling_rate(sampling_rate)
        EEGAmplifier.sampling_rate.fset(self, sampling_rate)

    @property
    def active_channels(self) -> Sequence[str]:
        return self._cpp_amp.get_active_channels()

    @active_channels.setter
    def active_channels(self, active_channels):
        self._cpp_amp.set_active_channels(active_channels)
        EEGAmplifier.active_channels.fset(self, active_channels)

    def start_sampling(self):
        super().start_sampling()
        self._cpp_amp.start_sampling()

    def stop_sampling(self):
        self._cpp_amp.stop_sampling()
        super().stop_sampling()

    def _get_samples(self, samples_per_packet=1) -> SamplePacket:
        samples, timestamps, impedances = self._cpp_amp.get_samples_vec(samples_per_packet)
        impedance = Impedance(self._impedance_flags, impedances)
        return SamplePacket(samples=samples, ts=timestamps, impedance=impedance)

    def _wait(self, samples: Optional[int] = 1):
        pass

    @classmethod
    def _get_cpp_amplifier(cls, id: Optional[str] = None) -> PyAmplifier:
        amplifier_class = cls._get_cpp_amplifier_class()
        params = cls._id_to_params(id)
        logger = logging.getLogger(cls.name)
        instance = amplifier_class(params, logger.info)
        return instance
