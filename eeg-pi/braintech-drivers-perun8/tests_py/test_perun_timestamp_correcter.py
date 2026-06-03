# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.
import numpy as np
import time
from braintech.drivers.perun8.perun_timestamp_correcter import PerunAmpTimestampCorrecter
VISUAL_DEBUG = False


def test_perun_timestamp_correcter():
    """A rather visual test to see how it works."""
    sampling_frequency = 500

    packetsize = 8

    radio_offset = 0.01

    drifts = [[0, 1.001], [40, 0.3], [80, 4]]

    recording_start_ts = 9000000
    pc_timeline = np.arange(0, 1000, 1 / sampling_frequency)
    pc_timeline += recording_start_ts

    headset_timeline = np.copy(pc_timeline)
    for i in drifts:
        headset_timeline[i[0] * sampling_frequency:] *= i[1]
    headset_timeline_jumps = np.nonzero(np.abs(np.diff(headset_timeline)) > 2 / sampling_frequency)[0]
    for jump in headset_timeline_jumps:
        headset_timeline[jump + 1:] += headset_timeline[jump] - headset_timeline[jump + 1] + 1 / sampling_frequency

    # headset_timeline = pc_timeline * drift
    headset_timeline += 0.1 / sampling_frequency * (np.random.random(headset_timeline.shape) * 2 - 1)
    for i in range(0, headset_timeline.shape[0], packetsize):
        headset_timeline[i:i + packetsize] = headset_timeline[i]
    signal_packet_timestamps = headset_timeline - headset_timeline[0] + recording_start_ts

    # headset_timeline = (headset_timeline % 1075) - 200

    corr = PerunAmpTimestampCorrecter(debug=VISUAL_DEBUG, first_correction_after_s=10, correction_every_s=5)

    for i in range(0, int(pc_timeline.shape[0] / packetsize), packetsize):
        pc_timeline_packet = pc_timeline[i:i + packetsize]
        ts = signal_packet_timestamps[i:i + packetsize]
        ts_corrected = corr.get_corrected_timestamps(pc_timeline_packet + radio_offset, ts)
        if VISUAL_DEBUG:
            time.sleep(1 / 100)

    print("ts_corrected", ts_corrected[-1], 'should be', pc_timeline_packet[-1], 'diff',
          ts_corrected[-1] - pc_timeline_packet[-1])

    if VISUAL_DEBUG:

        input()

    assert np.isclose(ts_corrected[-1], pc_timeline_packet[-1], rtol=0, atol=0.05)

if __name__ == '__main__':
    test_perun_timestamp_correcter()
