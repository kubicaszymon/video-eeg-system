# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.
import time
import warnings
from collections import deque

import numpy as np
from scipy.stats import linregress


class DebugModeVisualisationException(Exception):
    pass


class PerunAmpTimestampCorrecter:
    def __init__(self, debug=False, correction_every_s=5, correction_fit_buffer_length_s=200,
                 first_correction_after_s=200, sampling_rate=500):
        self.sampling_rate = sampling_rate
        self._correction_every_s = correction_every_s
        self.debug = debug
        self._last_update = time.monotonic()
        self.debug_data_deque = deque(maxlen=int(self.sampling_rate * 60 * 60))
        self._buffer = deque(maxlen=int(self.sampling_rate * correction_fit_buffer_length_s))
        self._first_correction_after_s = first_correction_after_s
        self._ready_for_first_correction = False

        self._first_sample_ts = None
        self._first_10_seconds_passed = False
        self._time_slowing_factor_while_smoothing = 0.5

        if self.debug:
            try:
                from bci_panel.bci_panels import BCIPanelProcess
            except ImportError:
                raise DebugModeVisualisationException("Debug mode requires obci-ugm for visualisation, please install")
            self._panel = BCIPanelProcess()
            self._last_panel_update = time.monotonic()

        self._correction_coeff = 1
        self._correction_offset = lambda x: 0
        self._radio_time_offset = None
        self._last_correction_ts = time.monotonic()

    def get_corrected_timestamps(self, received_timestamps, original_timestamps):
        if self._first_sample_ts is None:
            self._first_sample_ts = original_timestamps[-1]
            self._last_correction_ts = original_timestamps[-1]
            return original_timestamps
        corrected_timestamps = self._correct_timestamps(original_timestamps)

        # don't do anything in first 10 seconds - let signal stabilize
        if not self._first_10_seconds_passed:
            self._first_10_seconds_passed = ((original_timestamps[-1] - self._first_sample_ts) < 10)
            return original_timestamps

        if not self._ready_for_first_correction:
            self._ready_for_first_correction = ((original_timestamps[-1]
                                                 - self._first_sample_ts) > self._first_correction_after_s)

        self._insert_packet_to_buffors(received_timestamps, original_timestamps, corrected_timestamps)

        if self.debug:
            self._debug_visualisation()

        enough_time_passed_since_last_correction = (original_timestamps[-1] -
                                                    self._last_correction_ts) > self._correction_every_s
        if enough_time_passed_since_last_correction and self._ready_for_first_correction:
            self._recalculate_correction()

        return corrected_timestamps

    def _correct_timestamps(self, timestamps):
        noncorrected_ts = timestamps - self._first_sample_ts

        corrected_ts = noncorrected_ts * self._correction_coeff + self._correction_offset(noncorrected_ts)
        corrected_ts += self._first_sample_ts

        if self._radio_time_offset is not None:
            corrected_ts += self._radio_time_offset

        return corrected_ts

    def _insert_packet_to_buffors(self, received_timestamps, original_timestamps, corrected_timestamps):
        for nr, i in enumerate(original_timestamps):
            pc_ts_signal = received_timestamps[nr] - self._first_sample_ts
            pc_ts_packet = corrected_timestamps[nr] - self._first_sample_ts
            pc_ts_packet_uncorr = original_timestamps[nr] - self._first_sample_ts

            if self.debug:
                self.debug_data_deque.append([pc_ts_packet, pc_ts_signal, pc_ts_packet_uncorr])
            self._buffer.append([pc_ts_packet_uncorr, pc_ts_packet, pc_ts_signal])

    def _debug_visualisation(self):
        min_debug_time = int(10 * self.sampling_rate)
        debug_panel_update_every = (time.monotonic() - self._last_panel_update) > 2
        if debug_panel_update_every and len(self.debug_data_deque) > min_debug_time:
            data = np.array(self.debug_data_deque)
            data = data.T

            y_data = [np.diff(data[1, :])]
            x_data = [np.arange(len(y_data[0])), ]

            self._panel.update_plot(x_data=x_data,
                                    y_data=y_data,
                                    labels=['pc_timestamp_delta'],
                                    )

            y_data = [data[0, :], data[2, :], data[1, :]]
            x_data = [data[1, :] - data[1, :][0]] * 3
            self._panel.update_plot(feature='corrected vs uncorrected',
                                    x_data=x_data,
                                    y_data=y_data,
                                    labels=['pc_timestamp', 'pc_timestamp_uncorr', 'pc_signal'],
                                    )
            self._last_panel_update = time.monotonic()

    def _recalculate_correction(self):
        fitting_data = np.array(self._buffer).T
        pc_ts_packet_uncorr = fitting_data[0, :]
        pc_ts_packet = fitting_data[1, :]
        pc_ts_signal = fitting_data[2, :]

        # taking only the different timestamp (all samples in packet have the same timestamp)
        mask = np.hstack((False, np.abs(np.diff(pc_ts_signal)) > 0))

        pc_ts_packet_uncorr = pc_ts_packet_uncorr[mask]
        pc_ts_packet = pc_ts_packet[mask]
        pc_ts_signal = pc_ts_signal[mask]

        if self._radio_time_offset is None:
            radio_offset_stop = int(10 * self.sampling_rate)
            self._radio_time_offset = np.mean(pc_ts_packet_uncorr[:radio_offset_stop]
                                              - pc_ts_signal[:radio_offset_stop])

        try:
            rvalue = 0
            skip = 1
            signal_l = 11
            while rvalue < 0.9999 and signal_l > 1:
                l = len(pc_ts_signal)
                start = int(l - l / skip)
                slope, intercept, rvalue, pvalue, stderr = linregress(pc_ts_signal[start:],
                                                                      pc_ts_packet_uncorr[start:])
                skip *= 2
                start = int(l - l / skip)
                signal_l = len(pc_ts_signal[start:]) / self.sampling_rate
        except np.linalg.linalg.LinAlgError:
            warnings.warn("Couldn't correct drift - estimation error.")
        else:
            self._correction_coeff = 1 / slope
            fixed_correction_offset = -(intercept / slope)

            old_ts = pc_ts_packet[-1]
            new_ts = pc_ts_packet_uncorr[-1] * self._correction_coeff + fixed_correction_offset

            if new_ts < old_ts:
                delta = old_ts - new_ts

                def _floating_offset(uncorrected_ts):
                    t0 = pc_ts_packet_uncorr[-1]

                    smoothing_min = 0
                    smoothing_max = delta

                    rate = self._time_slowing_factor_while_smoothing

                    smoothing_func = -rate * (uncorrected_ts - t0) + delta
                    smoothing_func = np.clip(smoothing_func, smoothing_min, smoothing_max)

                    return fixed_correction_offset + smoothing_func

                self._correction_offset = _floating_offset
            else:
                self._correction_offset = lambda x: fixed_correction_offset

            self._last_correction_ts = pc_ts_packet_uncorr[-1] + self._first_sample_ts
