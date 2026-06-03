# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
import threading
import time

import numpy as np
import pytest

from braintech.drivers.double_amplifier.sample_aligner import SampleAligner, Sample, SampleMerger
from braintech.obci.signal_processing.signal.containers import Impedance, SamplePacket


def assert_aligner_result(s_a, ts, expected):
    result = s_a.get_matching_samples(ts, 0.1)
    assert len(result) == len(expected), "length should by the same:%s %s" % (result, expected)
    for expected, sample in zip(expected, result):
        if not isinstance(expected, (list, tuple)):
            expected = expected, [expected]
        expected_ts, expected_samples = expected
        assert expected_ts == sample.ts and np.array_equal(expected_samples, sample.data), \
            "Expected %s  received:%s" % (expected, sample)


def get_sample(ts):
    return Sample(ts, np.array([ts]), np.array([]), [Impedance.NOT_APPLICABLE])


def test_sample_aligner():
    s_a = SampleAligner(10)

    def assert_result(ts, expected):
        return assert_aligner_result(s_a, ts, expected)

    assert_result(1, [])
    s_a.put_samples(get_sample(2))
    assert_result(1, [])
    assert_result(2, [2])
    assert_result(3, [2])
    s_a.put_samples(get_sample(4))
    s_a.put_samples(get_sample(5))
    s_a.put_samples(get_sample(6))
    assert_result(3, [2])
    assert_result(4.3, [4])
    assert_result(4.7, [4])
    assert_result(4.95, [5])
    assert_result(5.9, [6])
    assert_result(7, [6])
    assert_result(8, [6])
    s_a.put_samples(get_sample(7))
    s_a.put_samples(get_sample(8))
    s_a.put_samples(get_sample(9))
    assert_result(9, [7, 8, 9])
    assert_result(10, [9])
    assert_result(11, [9])
    s_a.put_samples(get_sample(10))
    s_a.put_samples(get_sample(11))
    s_a.put_samples(get_sample(12))
    s_a.put_samples(get_sample(13))
    s_a.put_samples(get_sample(14))
    assert_result(12.2, [10, 11, 12])
    assert_result(13.6, [13])
    assert_result(13.95, [14])


def test_sample_aligner_histeresis():
    s_a = SampleAligner(1)

    def assert_result(ts, expected):
        return assert_aligner_result(s_a, ts, expected)
    for i in range(20):
        s_a.put_samples(get_sample(i))
    assert_result(0, [0])
    assert_result(0.9, [1])
    assert_result(1.8, [2])
    assert_result(2.7, [3])
    assert_result(3.4, [4])
    assert_result(3.7, [4])
    assert_result(4.8, [5])
    assert_result(5.7, [6])
    assert_result(6.6, [7])
    assert_result(7.2, [7])
    assert_result(8.3, [8])
    assert_result(9.4, [9])
    assert_result(10.5, [10])
    assert_result(11.6, [11])
    assert_result(12.7, [12])
    assert_result(13.8, [13,14])
    assert_result(14.5, [15])

def test_sample_merger():
    sampling_rate = 10
    s_a = SampleAligner(sampling_rate)
    s_m = SampleMerger(sample_aligner=s_a, prepend_ts=(True, True), max_wait=0.5)
    samples_per_packet = 2
    channels = 2

    def sample_packet(base_ts, base=None):
        if base is None:
            base = base_ts * 10
        ts = []
        samples = []
        impedances = []
        for s in range(samples_per_packet):
            ts.append(base_ts + s / sampling_rate)
            samples.append([(base + i) + s / sampling_rate for i in range(channels)])
            impedances.append([base + s / sampling_rate])
        return SamplePacket(
            samples=np.array(samples),
            ts=np.array(ts),
            impedance=Impedance(ids=[Impedance.NOT_APPLICABLE, Impedance.PRESENT], data=np.array(impedances))
        )

    start = time.monotonic()
    s_m.put_master(sample_packet(1))
    assert s_m.samples_available == 0, "No samples should be available"
    assert time.monotonic() - start > 0.5, "Sample merger should try to wait"
    s_m.put_master(sample_packet(1.2))
    assert s_m.samples_available == 0, "No samples should be available"
    assert time.monotonic() - start < 1, "Sample merger should not wait anymore"
    s_m.put_other(sample_packet(1))
    s_m.put_master(sample_packet(1.4))
    assert s_m.samples_available == 3, "Three samples should be available - one 'old' from other, and two matches"
    with pytest.raises(AssertionError):
        s_m.get_sample_packet(4)
    result = s_m.get_sample_packet(3)
    assert list(result.ts) == [1.4, 1.4, 1.5]
    assert np.allclose(result.samples, np.array([[0.4, 0.0, 14.0, 15.0, 10.0, 11.0],
                                                 [0.4, 0.1, 14.0, 15.0, 10.1, 11.1],
                                                 [0.5, 0.1, 14.1, 15.1, 10.1, 11.1]]))
    assert s_m.samples_available == 0
    event = threading.Event()

    def _put_other():
        event.wait()
        time.sleep(0.3)
        s_m.put_other(sample_packet(2.65))
        s_m.put_other(sample_packet(2.85))

    threading.Thread(target=_put_other, daemon=True).start()
    start = time.monotonic()
    event.set()
    s_m.put_master(sample_packet(2.6))
    assert time.monotonic() - start > 0.2
    assert s_m.samples_available == 2
    result = s_m.get_sample_packet(2)
    assert np.allclose(result.ts, [2.6, 2.7])
    assert np.allclose(result.samples, [[1.6, 1.65, 26.0, 27.0, 26.5, 27.5],
                                        [1.7, 1.75, 26.1, 27.1, 26.6, 27.6],
                                        ])
