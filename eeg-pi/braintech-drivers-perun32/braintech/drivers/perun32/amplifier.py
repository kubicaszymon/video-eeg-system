# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
from collections import deque
from copy import deepcopy
from typing import Optional

from braintech.drivers.perun32.perun32_versions_channels_table import PERUNAMP_GAIN, DESCRIPTION_TABLE
from braintech.drivers.perun8.perun_timestamp_correcter import PerunAmpTimestampCorrecter
import numpy as np
from scipy.signal import iirnotch, iirpeak, lfilter_zi, lfilter

from braintech.obci.core.broker import ObciException
from braintech.obci.core.drivers.eeg.eeg_amplifier import EEGAmplifier, AmplifierDescription, ChannelDescription
from braintech.obci.signal_processing.signal.containers import Impedance, SamplePacket
from .device import PerunAmp32Device

class ImpedanceNotchFilter:
    def __init__(self, sampling_rate=128):
        """
        :param sampling_rate: Float in Hz
        :param filter_notification_callback: function which accepts list of lists of b, a weights:
                [[b1, a1,], [b2, a2], ...]
        """
        self._sampling_rate = sampling_rate
        self._init_filters()

    def get_b_a(self):
        return self._b, self._a

    def _init_filters(self):
        self._zi = None
        self._b, self._a = self._get_filter()

    def _get_filter(self):
        bandwidth = 5  # Hz
        w0 = (self._sampling_rate / 4) / (self.sampling_rate / 2)
        Q = self._sampling_rate / 4 / bandwidth
        b, a = iirnotch(w0, Q=Q)
        return b, a

    def filter(self, samples):
        """Do multichannel filtering.

        :param samples: array (samples x channels)
        """

        if self._zi is None:
            self._prepare_zi(samples)
        try:
            filtered, zi = lfilter(self._b, self._a, samples, axis=0, zi=self._zi)
        except ValueError:
            self._prepare_zi(samples)
            filtered, zi = lfilter(self._b, self._a, samples, axis=0, zi=self._zi)
        self._zi = zi
        return filtered

    def _prepare_zi(self, samples):
        n = samples.shape[1]
        zis = []
        for i in range(n):
            zi = lfilter_zi(self._b, self._a) * samples[0, i]
            zis.append(zi)
        self._zi = np.array(zis).T

    @property
    def sampling_rate(self):
        return self._sampling_rate


class ImpedancePeakFilter(ImpedanceNotchFilter):
    def _get_filter(self):
        bandwidth = 5  # Hz
        w0 = (self._sampling_rate / 4) / (self.sampling_rate / 2)
        Q = self._sampling_rate / 4 / bandwidth
        b, a = iirpeak(w0, Q=Q)
        return b, a


class ImpedanceCalculator:
    # correction from calibration (measuring known set of resistors):
    # 2 amps, different channels: EXG0, EXG1, EXG2, AUX0, AUX1, AUX7 at 500 and 4000 Hz sampling rate
    # results in quite good (10%) measurement, to getter better results we would need calibration for every channel
    # on every amp
    PERUNAMP32_CALIBRATION_OFFSET = 0.39693829
    PERUNAMP32_CALIBRATION_GAIN = 0.72519778
    IMPEDANCE_MEASURING_CURRENT_NAMPS = 6  # nanoAmperes

    def __init__(self, sampling_rate, flags):

        self._filter = ImpedancePeakFilter()

        # will be changed when starting amplifier
        self._flags = flags
        self._channel_number = len(flags)
        self._indexes = [i for i in range(self._channel_number) if flags[i] == Impedance.PRESENT]

        self._samples_per_packet = 8
        self._rms_size = 16
        self._kernel = np.ones(self._rms_size) / self._rms_size
        self._sampling_rate = sampling_rate
        if sampling_rate > 1500:
            self._rms_size = 512
            self._kernel = np.ones(self._rms_size) / self._rms_size
            self._create_buffer()

    def _create_buffer(self):
        self._buffer = deque(maxlen=max([self._rms_size * 2, self._samples_per_packet * 2]))

    def get_impedances(self, samples):
        """
        Samples IN MICOVOLTS
        :param samples: array (samples x channels)
        """
        if len(self._indexes) != samples.shape[1]:
            samples = samples[:, self._indexes]
        if self._samples_per_packet != samples.shape[0]:
            self._samples_per_packet = samples.shape[0]
            self._create_buffer()
        if self._channel_number != samples.shape[1]:
            self._channel_number = samples.shape[1]
            self._create_buffer()

        mask_positive_overdrive = samples > ((2 ** 24) / 2 - 2) * PERUNAMP_GAIN
        mask_negative_overdrive = samples < - ((2 ** 24) / 2 + 2) * PERUNAMP_GAIN
        infinity_mask = np.logical_or(mask_negative_overdrive, mask_positive_overdrive)
        filtered = self._filter.filter(samples)
        squared = filtered ** 2
        self._add_to_buffer(squared)

        if len(self._buffer) == self._buffer.maxlen:
            buffor_array = np.array(self._buffer)
            # average of squared signal
            running_average = np.convolve(buffor_array.T.flatten(), self._kernel,
                                          mode='same').reshape(buffor_array.T.shape).T

            end = - (int(self._rms_size / 2) + 1)
            start = end - samples.shape[0]

            # using the latest impedance samples without convolution edge artifacts
            running_average_relevant = running_average[start:end, :]

            rms = running_average_relevant ** 0.5
            amplitude = 2 ** 0.5 * rms
            impedances = amplitude / self.IMPEDANCE_MEASURING_CURRENT_NAMPS
            # correction - from empirical measurements
            impedances = (impedances - self.PERUNAMP32_CALIBRATION_OFFSET) / self.PERUNAMP32_CALIBRATION_GAIN
            # additional heuristic for disconnection detection
            # if impedance is lower than 10 kilohms but there is big DC offset - needed for high sampling rates
            if self._sampling_rate > 2000:
                # 4000000 and 10 kOhms is from observing empirical data - from working amp
                high_dc_offset = np.logical_or((samples > 4000000 * PERUNAMP_GAIN),
                                               (samples < -4000000 * PERUNAMP_GAIN))
                low_impedance = impedances < 10
                infinity_mask = np.logical_or(infinity_mask, np.logical_and(high_dc_offset, low_impedance))
        else:
            impedances = np.ones_like(samples) * np.inf
        impedances[infinity_mask] = np.inf
        return Impedance(ids=self._flags, data=impedances)

    def _add_to_buffer(self, samples):
        for sample in samples:
            self._buffer.append(sample)





class Perun32Amplifier(EEGAmplifier):
    _description = DESCRIPTION_TABLE['old']
    PHYSICAL_CHANELL_COUNT = 33

    @classmethod
    def get_available_amplifiers(cls, device_type: Optional[str] = None):
        amplifiers = []
        if device_type is None or device_type == 'usb':
            amplifiers += [str(amp) for amp in PerunAmp32Device.find_devices()]
        return amplifiers

    @classmethod
    def get_description(cls, id: Optional[str] = None) -> AmplifierDescription:
        """Get description of an amplifier with given id"""
        perun32 = None
        for dev in PerunAmp32Device.find_devices():
            if str(dev) == id or not id:
                perun32 = dev
                break
        if perun32:
            model = perun32.model
            return DESCRIPTION_TABLE[model]
        else:
            return DESCRIPTION_TABLE['old']

    def __init__(self, id=None):
        self._impedance_filter_instance = None
        self._impedance_calculator = None
        self._measure_impedance = False
        self.impedance_filter = False
        for dev in PerunAmp32Device.find_devices():
            if str(dev) == id or not id:
                self._device = dev
                break
        else:
            raise ObciException("Perun32Amplifier is not found!")
        self._description = DESCRIPTION_TABLE[dev.model].replace(name=id)
        super(Perun32Amplifier, self).__init__(id)
        self.sampling_rate = 500
        self._device.open()
        if self._device.model in ['b', 'c', 'd']:
            self._reindex_array = self._db25_friendly_reindex
        elif self._device.model == 'a':
            self._reindex_array = self._db25_friendly_reindex[0:23] + self._db25_friendly_reindex[24:]
        elif self._device.model == 'old':
            self._reindex_array = list(range(33))

    @property
    def measure_impedance(self):
        return self._measure_impedance

    @measure_impedance.setter
    def measure_impedance(self, b):
        self._measure_impedance = b
        del self.current_description

    def _get_current_description(self):
        current_desc = super()._get_current_description()
        channels = deepcopy(current_desc.channels)
        for channel in channels:
            if channel.impedance is Impedance.NOT_APPLICABLE:
                continue
            elif self.measure_impedance:
                b, a = self._impedance_filter_instance.get_b_a()
                channel.impedance = Impedance.PRESENT
                channel.filters = [{'b': b.tolist(), 'a': a.tolist()}]
            else:
                channel.impedance = Impedance.UNKNOWN
        current_desc.channels = channels
        return current_desc

    def start_sampling(self):
        super(Perun32Amplifier, self).start_sampling()
        self._device.sampling_rate = self.sampling_rate
        self._device.measure_impedance = self.measure_impedance
        # Pi Zero 2W can't afford the default 200 s / 100k-sample drift
        # regression every 5 s (it saturates the CPU and starves the USB
        # reader). Use a short fit window so the correction stays cheap.
        self._timestamp_correcter = PerunAmpTimestampCorrecter(
            sampling_rate=self.sampling_rate,
            correction_fit_buffer_length_s=30,
            first_correction_after_s=30)
        self._impedance_calculator = ImpedanceCalculator(self.sampling_rate,
                                                         [ch.impedance for ch in self.get_active_channels()])
        self._device.start()

    def stop_sampling(self):
        self._device.stop()
        super(Perun32Amplifier, self).stop_sampling()

    def _get_samples(self, samples_per_packet):
        timestamps = np.empty((samples_per_packet,))
        receive_ts = np.empty((samples_per_packet,))
        samples = np.empty((samples_per_packet, self.PHYSICAL_CHANELL_COUNT))
        for i in range(samples_per_packet):
            sample_data = self._device.get_samples(30.0)
            timestamps[i] = sample_data.timestamp
            receive_ts[i] = sample_data.receive_timestamp
            samples[i] = sample_data.ch_data_with_events
        timestamps = self._timestamp_correcter.get_corrected_timestamps(receive_ts, timestamps)
        samples = self._reindex_samples(samples)
        if self.measure_impedance:
            microvolt_samples = samples * self._gains
            impedance = self._impedance_calculator.get_impedances(microvolt_samples)
        else:
            impedance = None
        if self.impedance_filter:
            samples = self._impedance_filter_instance.filter(samples)
        return SamplePacket(samples, timestamps, impedance=impedance)

    @property
    def _db25_friendly_reindex(self):
        """This reorders samples packet in a way that custom made db25 cap has EEG channels sorted in
        logical way (front to back), and custom db25 adapter has labels so that channels number labels correspond
        corretly to logical channel numbering seen in Svarog.

        This table might explain everything. ADC channel is the raw ordering of sample packet.
        Svarog order    Label on cap	Driver label	ADC_channel	    DB25 Pin number	    Label on db25 adapter
        0               Fp1             Exg_1           0               1                   1
        1               Fp2             Exg_2           1               14                  2
        2               F7              Exg_3           18              6                   3
        3               F3              Exg_4           2               2                   4
        4               Fz              Exg_5           9               10                  5
        5               F4              Exg_6           3               15                  6
        6               F8              Exg_7           19              19                  7
        7               M1              Exg_8           13              12                  8
        8               T3              Exg_9           20              7                   9
        9               C3              Exg_10          4               3                   10
        10              Cz              Exg_11          8               22                  11
        11              C4              Exg_12          5               16                  12
        12              T4              Exg_13          21              20                  13
        13              M2              Exg_14          15              13                  14
        14              T5              Exg_15          22              8                   15
        15              P3              Exg_16          6               4                   16
        16              Pz              Exg_17          10              23                  17
        17              P4              Exg_18          7               17                  18
        18              T6              Exg_19          23              21                  19
        19              O1              Exg_20          16              5                   20
        20              O2              Exg_21          17              18                  21
        21              A1              Exg_22          11              11                  22
        22              A2              Exg_23          12              24                  23
        23              AFz/GND         Exg_24          14              25                  24/GND
                        REF                             REF             9                   REF
        """
        try:
            return self._db25_friendly_reindex_value
        except AttributeError:
            aux = [24, 25, 26, 27, 28, 29, 30, 31]
            events = [32, ]
            db25_adc_channels_order = [0, 1, 18, 2, 9, 3, 19, 13, 20, 4, 8, 5, 21, 15, 22, 6, 10, 7, 23, 16,
                                       17, 11, 12, 14]
            self._db25_friendly_reindex_value = db25_adc_channels_order + aux + events
            return self._db25_friendly_reindex_value

    def _reindex_samples(self, samples):
        """Reindex samples to fit the DB25 adapter so the (EXG1 == channel 1)"""

        samples = samples[:, self._reindex_array]
        return super()._reindex_samples(samples)

    def _wait(self, samples: Optional[int] = 1):
        pass

    def _sampling_rate_set(self, sampling_rate):
        super()._sampling_rate_set(sampling_rate)
        self._impedance_filter_instance = ImpedanceNotchFilter(sampling_rate=sampling_rate)

    def _active_channels_set(self, active_channels):
        super()._sampling_rate_set(active_channels)
        self._gains = np.array(self.current_description.channel_gains)
        self._offsets = np.array(self.current_description.channel_offsets)
