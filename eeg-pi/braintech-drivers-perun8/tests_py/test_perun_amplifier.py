# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved

import os
import pickle
import threading
import time

import numpy as np
import pytest
from braintech.drivers.perun8._perun8 import PyAmplifierPerun8


perun_amp_not_connected = lambda: not any(PyAmplifierPerun8.getAvailablePerunAmplifiers())


if perun_amp_not_connected():
    if pytest.__version__ < "3.0.0":
        pytest.skip()
    else:
        pytestmark = pytest.mark.skip


def log_callback(msg):
    print('LOG: {}'.format(msg))


def test_perun_amplifier_timestamps():
    print(PyAmplifierPerun8.getAvailablePerunAmplifiers())
    amp = PyAmplifierPerun8({'device_index': 0}, log_callback)
    desc = amp.get_description()
    amp.set_active_channels([c['name'] for c in desc['channels']])
    amp.get_active_channels()
    start_timestamp = time.time()
    amp.start_sampling()
    print("time.time", start_timestamp)
    for i in range(200):
        samples, timestamps, impedance = amp.get_samples_vec(4)
    SR = 500.0
    start_timestamp = time.time()
    start_mono = time.perf_counter()
    start_brain = timestamps[-1] + 1 / SR
    first_ts = last_ts = None
    s = 0
    LEN = 1005000
    all_timestamps = np.zeros((2, LEN), dtype=np.double)
    all_timestamps[0, 0] = start_timestamp
    measurements = []
    cur_data = (start_timestamp, start_brain, start_timestamp, 0)
    times = []
    CS = 1
    pack_diff = 0
    on = False

    for i in range(1, LEN):
        samples, timestamps, impedance = amp.get_samples_vec(CS)
        print(samples[0][8:11])
        for s, t in zip(samples[:, 6], timestamps):
            # print(s)
            if s < 7600000:
                if not on:
                    print("On", t)
                    on = True
            elif on:
                print("off", t)
                on = False

        end_timestamp = time.time()
        mono_time = time.perf_counter()
        end_timestamp_mono = mono_time - start_mono + start_timestamp
        times.append(
            (end_timestamp - start_timestamp, mono_time - start_mono, timestamps[-1] + 1 / SR - start_brain))
        if end_timestamp > cur_data[0] + CS / SR:
            pack_diff = 0
            measurements.append(cur_data)
        else:
            pack_diff += 1
        cur_data = (end_timestamp, end_timestamp_mono, timestamps[-1] + 1 / SR, pack_diff)
    amp.stop_sampling()
    all_timestamps = np.array(measurements).T
    # duration = end_timestamp - start_timestamp
    from matplotlib import pyplot
    # pyplot.plot(all_timestamps[0])
    # pyplot.plot(all_timestamps[1])
    print('time', all_timestamps[0, :30] - all_timestamps[0, 0])
    print('mono', all_timestamps[1, :30] - all_timestamps[1, 0])
    print('brain', all_timestamps[2, :30] - all_timestamps[2, 0])

    pyplot.subplot(211)
    pyplot.plot(all_timestamps[0] - all_timestamps[2])
    pyplot.plot(all_timestamps[1] - all_timestamps[2])
    pyplot.plot((all_timestamps[2, 1:] - all_timestamps[2, :-1]))
    pyplot.plot(all_timestamps[3] / 100)
    # pyplot.plot(all_timestamps[0, 1:] - all_timestamps[0, :-1])
    pyplot.legend(['time_diff', 'monotonic_diff', "brain_diff"])
    pyplot.subplot(212)
    arr = np.array(times).T
    print('time', arr[0, :30] - arr[0, 0])
    print('mono', arr[1, :30] - arr[1, 0])
    print('brain', arr[2, :30] - arr[2, 0])
    pyplot.plot(arr[0, 1:] - arr[0, :-1])
    pyplot.plot(arr[1, 1:] - arr[1, :-1])
    pyplot.plot(arr[2, 1:] - arr[2, :-1])
    pyplot.legend(["time", "mono", "brain"])
    pyplot.show()

    # print("Sampling duration:", duration)
    # print("Sampling frequency", s / duration)
    # print("First sample timestamp:", start_timestamp, 'diff', start_timestamp - first_ts)
    # print("Last sample timestamp:", end_timestamp, 'diff', end_timestamp - last_ts)


def test_local_clock():
    from matplotlib import pyplot
    d = []
    for i in range(20000):
        # print(cpp_amplifiers.PyAmplifier.local_clock())
        d.append(PyAmplifierPerun8.local_clock())
    d = np.array(d) - d[0]
    pyplot.plot(d[1:] - d[:-1])
    pyplot.show()


def _diff(a):
    return a[1:] - a[:-1]


def test_brain_amplifier_timing():
    from matplotlib import pyplot
    amp = PyAmplifierPerun8({'device_index': 0}, log_callback)
    channels = ['Sample_Counter', 'Dongle Timestamp', 'Head Timestamp', 'PC Timestamp', '6']
    amp.set_active_channels(channels)
    amp.start_sampling()
    LEN = 100000 // 2
    CS = 4
    data = {c: [] for c in channels}
    data['ts'] = []
    prev = 0
    for i in range(LEN // CS):
        samples, timestamps, impedance = amp.get_samples_vec(CS)
        for s, n in zip(samples[0], channels):
            data[n].append(s)
        for s in samples[:, 2]:
            if prev and s > prev and (s - prev) / 4000 > 9:
                print("Samples dropped!", (s - prev) / 4000 / 2)
            prev = s

        data['ts'].append(timestamps[0])
    amp.stop_sampling()
    base = data['ts'][0]
    print("First TS", base)
    print("First PC Timestamp", data['PC Timestamp'][0])
    print("Diff", data['PC Timestamp'][0] - base)
    print("Last Diff", data['PC Timestamp'][-1] - data['ts'][-1])
    print("First Head Timestamp", data['Head Timestamp'][0])
    print("Last  Head Timestamp", data['Head Timestamp'][-1])
    data['PC Timestamp'] = np.array(data['PC Timestamp']) - base
    data['ts'] = np.array(data['ts']) - base
    for k in ['Dongle Timestamp', 'Head Timestamp']:
        data[k] = np.array(data[k]) - data[k][0]
    pyplot.subplot(2, 1, 1)
    pyplot.plot(_diff(data['PC Timestamp']) * 1000)
    pyplot.plot(_diff(data['ts']) * 1000)
    pyplot.plot((data['PC Timestamp'] - data['ts']) * 1000)
    pyplot.plot(_diff(data['Dongle Timestamp']) / 4000)
    pyplot.plot(_diff(data['Head Timestamp']) / 4000)
    pyplot.legend(['PC Timestamp', 'ts', 'diff', 'dongle_diff', "head_diff"])
    pickle.dump(data, open("timestamps.pickle", 'wb'))
    pyplot.subplot(2, 1, 2)
    pyplot.plot(data['PC Timestamp'] * 1000)
    pyplot.plot(data['ts'] * 1000)
    pyplot.plot(data['Dongle Timestamp'] / 4000)
    pyplot.legend(['PC Timestamp', 'ts', 'Dongle Timestamp'])
    pyplot.show()


def test_brain_timestamps():
    amp = PyAmplifierPerun8({'device_index': 0}, log_callback)
    channels = ['Sample_Counter', 'Dongle Timestamp', 'Head Timestamp', 'PC Timestamp', '6']
    amp.set_active_channels(channels)
    amp.start_sampling()
    i = 0
    last = 0
    while amp.is_sampling():
        samples, timestamps, impedance = amp.get_samples_vec(1)
        i += 1
        if i % 1000 == 0 or abs(timestamps[0] - last) > 0.1:
            print("head: %f, ts: %f" % (samples[0][2], timestamps[0]))
        if abs(timestamps[0] - last) > 0.1 and last != 0:
            print("######################!!!!!!!!!!!", samples)
        last = timestamps[0]

    amp.stop_sampling()


def test_brain_stopping():
    amp = PyAmplifierPerun8({'device_index': 0}, log_callback)
    amp.start_sampling()
    received = threading.Event()
    received.clear()
    def _read_sample():
        while amp.is_sampling():
            samples, timestamps, _ = amp.get_samples_vec(10)
            print(timestamps)
            received.set()

    receive_thread = threading.Thread(target=_read_sample)
    receive_thread.start()
    received.wait()
    amp.stop_sampling()
    receive_thread.join()
