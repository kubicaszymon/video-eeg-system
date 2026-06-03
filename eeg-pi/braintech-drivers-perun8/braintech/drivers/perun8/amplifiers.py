# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
from typing import List, Sequence, Optional

from braintech.obci.core.broker import ObciException
from braintech.obci.signal_processing.signal.data_generic_write_proxy import SamplePacket
from braintech.utils import singleton_app
from .perun_timestamp_correcter import PerunAmpTimestampCorrecter
from braintech.drivers.native_amplifier_lib.native_amplifier_base import CppEEGAmplifier, CantConnectToAmplifier
from braintech.drivers.perun8._perun8 import PyAmplifierPerun8


class PerunCppAmplifier(CppEEGAmplifier):
    name = 'PerunCppAmplifier'
    MAX_BRAIN_AMPLIFIERS = 3

    def __init__(self, id: Optional[str] = None):
        self._hidden_pc_timestamp_added = False
        self._timestamp_correcter = None
        super().__init__(id)
        device_id = self._id_to_params(id)['device_index']
        self._lock = singleton_app.SingleProcessApplication(
            flavor_id=str(device_id), basename='obci.perunamp', autolock=False)

    def start_sampling(self):
        try:
            self._lock.acquire()
        except singleton_app.SingleInstanceException:
            raise CantConnectToAmplifier('Amplifier should already sampling')
        else:
            self._timestamp_correcter = PerunAmpTimestampCorrecter(sampling_rate=self.sampling_rate)
            self._cpp_amp.set_active_channels(tuple(list(self.active_channels) + ["PC Timestamp"]))
            self._hidden_pc_timestamp_added = True
            super().start_sampling()

    def stop_sampling(self):
        super().stop_sampling()
        self._cpp_amp.set_active_channels(self.active_channels)
        self._hidden_pc_timestamp_added = False
        self._lock.release()

    @classmethod
    def get_available_amplifiers(cls, device_type: Optional[str] = None) -> List[str]:
        if device_type is None or device_type == 'usb':
            locks = []
            try:
                for device_id in range(cls.MAX_BRAIN_AMPLIFIERS):
                    try:
                        lock = singleton_app.SingleProcessApplication(
                            flavor_id=str(device_id), basename='obci.perunamp')
                    except singleton_app.SingleInstanceException:
                        return []
                    else:
                        locks.append(lock)
                return PyAmplifierPerun8.getAvailablePerunAmplifiers()
            finally:
                for lock in locks:
                    lock.release()
        return []

    @property
    def active_channels(self) -> Sequence[str]:
        """List of active channel names"""
        if self._hidden_pc_timestamp_added:
            return super().active_channels[:-1]
        else:
            return super().active_channels

    @active_channels.setter
    def active_channels(self, active_channels):
        CppEEGAmplifier.active_channels.fset(self, active_channels)

    def get_samples(self, samples_per_packet=1):
        uncorrected_sample_packet = super().get_samples(samples_per_packet)
        if self._timestamp_correcter is not None:
            receive_timestamps = uncorrected_sample_packet.samples[:, -1]
            correct_timestamps = self._timestamp_correcter.get_corrected_timestamps(receive_timestamps,
                                                                                    uncorrected_sample_packet.ts)
            sample_packet = SamplePacket(samples=uncorrected_sample_packet.samples[:, :-1],
                                         ts=correct_timestamps,
                                         impedance=uncorrected_sample_packet.impedance)
            return sample_packet
        else:
            return uncorrected_sample_packet

    @classmethod
    def _get_cpp_amplifier_class(cls):
        return PyAmplifierPerun8

    @classmethod
    def _id_to_params(cls, id: Optional[str] = None) -> dict:
        if id is None or id == '':
            return {'device_index': 0}
        else:
            device_index_str = id.rsplit(maxsplit=1)[-1]
            try:
                device_index = int(device_index_str)
            except ValueError:
                raise ObciException("Brain Amplifier is not found!")
            else:
                expected_cpp_amplifier_index = device_index - 1
                return {'device_index': expected_cpp_amplifier_index}

