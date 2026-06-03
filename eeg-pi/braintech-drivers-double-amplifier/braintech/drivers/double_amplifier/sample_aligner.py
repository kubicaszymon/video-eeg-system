# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
import queue
import time
from collections import namedtuple

import numpy as np

from braintech.obci.signal_processing.signal.containers import SamplePacket, Impedance


class Sample(namedtuple('Sample', 'ts,data,impedance,flags')):
    def __repr__(self):
        return "Sample(%.6f)" % self.ts


class SampleAligner:
    def __init__(self, sampling_rate, histeresis=0.25):
        self._sampling_rate = sampling_rate
        self._queue = queue.Queue()
        self._prev_sample = Sample(-1, None, None, None)
        self._next_sample = self._prev_sample
        self._last_returned = self._prev_sample.ts
        self._histeresis = histeresis * 1 / self._sampling_rate
        self._delta = 0

    def put_samples(self, sample):
        self._queue.put(sample)

    def get_matching_samples(self, requested_ts, max_wait):
        result_samples = self._get_matching_samples(requested_ts, max_wait)
        result_samples = self._exclude_already_returned_samples(result_samples)
        if len(result_samples):
            self._last_returned = result_samples[-1].ts
            if self._last_returned < requested_ts:
                self._delta = -self._histeresis
            else:
                self._delta = self._histeresis
        return result_samples

    def _exclude_already_returned_samples(self, result_samples):
        while len(result_samples) > 1 and result_samples[0].ts <= self._last_returned:
            result_samples = result_samples[1:]
        return result_samples

    def _get_matching_samples(self, requested_ts, max_wait):
        result_samples = []
        if self._prev_sample.ts >= 0:
            result_samples.append(self._prev_sample)
        if self._next_sample.ts >= 0:
            result_samples.append(self._next_sample)
        while self._next_sample.ts < requested_ts:
            cur_next = self._next_sample
            try:
                self._next_sample = self._queue.get(timeout=max_wait)
                self._prev_sample = cur_next
                result_samples.append(self._next_sample)
            except queue.Empty:
                return result_samples
        requested_ts += self._delta
        is_next_sample_further = abs(self._next_sample.ts - requested_ts) > abs(self._prev_sample.ts - requested_ts)
        is_next_too_new = self._next_sample.ts > requested_ts + 1 / self._sampling_rate
        if is_next_sample_further or is_next_too_new:
            result_samples.pop(len(result_samples) - 1)
        return result_samples


class SampleMerger:
    def __init__(self, sample_aligner: SampleAligner, prepend_ts=(True, True), max_wait=0.5):
        self._sample_aligner = sample_aligner
        self._result = []
        self._ts_idx = [
            0 if prepend_ts[0] else -1
        ]
        self._ts_idx.append(self._ts_idx[0] + 1 if prepend_ts[1] else -1)
        self._master_samples_idx = max(self._ts_idx) + 1
        self._first_ts = None
        self._max_wait = max_wait
        self._impedance_flags = [Impedance.NOT_APPLICABLE] * len(self._ts_idx)

    def _merge(self, master_sample: Sample, other_sample: Sample):
        data = np.empty((self._master_samples_idx + len(master_sample.data) + len(other_sample.data)))
        if self._ts_idx[0] >= 0:
            data[self._ts_idx[0]] = master_sample.ts
        if self._ts_idx[1] >= 0:
            data[self._ts_idx[1]] = other_sample.ts
        other_start = self._master_samples_idx + len(master_sample.data)
        data[self._master_samples_idx:other_start] = master_sample.data
        data[other_start:] = other_sample.data
        impedance = np.concatenate((master_sample.impedance, other_sample.impedance))
        return Sample(master_sample.ts + self._first_ts, data, impedance,
                      np.concatenate((self._impedance_flags, master_sample.flags, other_sample.flags)))

    def _create_sample(self, sample_packet: SamplePacket, idx):
        return Sample(sample_packet.ts[idx] - self._first_ts,
                      sample_packet.samples[idx],
                      sample_packet.impedance.data[idx],
                      sample_packet.impedance.flags)

    def put_other(self, sample_packet: SamplePacket):
        if self._first_ts is None:
            return
        for i in range(sample_packet.sample_count):
            self._sample_aligner.put_samples(self._create_sample(sample_packet, i))

    def put_master(self, sample_packet: SamplePacket):
        if self._first_ts is None:
            self._first_local_time = time.monotonic()
            self._first_ts = sample_packet.ts[0]

        for i in range(sample_packet.sample_count):
            master_sample = self._create_sample(sample_packet, i)
            expected_other_ts = master_sample.ts + self._max_wait
            now_ts = time.monotonic() - self._first_local_time
            max_wait = max(0, expected_other_ts - now_ts)
            matching = self._sample_aligner.get_matching_samples(master_sample.ts, max_wait)
            if len(matching) != 1:
                print(master_sample.ts, matching)
            for sample in matching:
                self._result.append(self._merge(master_sample, sample))

    @property
    def samples_available(self):
        return len(self._result)

    def get_sample_packet(self, samples_per_packet):
        assert samples_per_packet <= self.samples_available
        assert samples_per_packet > 0
        result = self._result[:samples_per_packet]
        self._result = result[samples_per_packet:]
        return SamplePacket(
            ts=np.array([s.ts for s in result]),
            samples=np.stack([s.data for s in result]),
            impedance=Impedance(data=np.stack([s.impedance for s in result]), ids=result[0].flags)
        )
