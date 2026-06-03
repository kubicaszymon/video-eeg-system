import sys
import time
from subprocess import Popen, check_output, call
from uuid import uuid4

import numpy

from braintech.obci.core.drivers.eeg.lsl_amplifier import LSLAmplifierAdapter
import braintech.obci.experiment.driver_utils.obci_to_lsl_streamer as streamer_module
from braintech.obci.core.drivers.eeg.random_amplifier import RandomAmplifier

streamer_module_file = streamer_module.__file__
python = sys.executable

RANDOM_AMP_MAX_VALUE = 20
RANDOM_AMP_MIN_VALUE = 0
LSL_LAUNCH_TIMEOUT = 100
SAMPLES_TO_CAPTURE = 128


def test_lsl_streaming_sees_default_random_amp():
    output = check_output([python, streamer_module_file, '-l']).decode()
    assert "RandomAmplifier" in output, "LSL streamer can't find amplifier"


def test_lsl_streaming_runs_default_random_amp():
    stream_name = str(uuid4())

    process = Popen([python, streamer_module_file, '-a', 'RandomAmplifier', '-n', stream_name])
    t_end = time.monotonic() + LSL_LAUNCH_TIMEOUT
    available_streams = []
    while time.monotonic() < t_end:
        available_streams = LSLAmplifierAdapter.get_available_amplifiers('virtual')
        if stream_name in available_streams:
            break
    assert len(available_streams)
    recv_amp = LSLAmplifierAdapter(stream_name)
    recv_amp.start_sampling()
    samples = recv_amp.get_samples(SAMPLES_TO_CAPTURE)

    channel_names = RandomAmplifier.get_description('RandomAmplifier').channel_names

    assert recv_amp.active_channels == channel_names
    assert samples.samples.shape == (SAMPLES_TO_CAPTURE, len(channel_names))
    # excluding technical channels
    assert numpy.all(samples.samples[:, 0:-2] <= RANDOM_AMP_MAX_VALUE)
    assert numpy.all(samples.samples[:, 0:-2] >= RANDOM_AMP_MIN_VALUE)

    recv_amp.stop_sampling()
    process.kill()
    process.wait()


def test_lsl_streaming_runs_non_default_channels_and_sampling_rate():
    stream_name = str(uuid4())
    channel_names = "Random0 Random1 Random2 Random3".split()

    process = Popen([python, streamer_module_file, '-a', 'RandomAmplifier', '-n', stream_name,
                     '-c'] + channel_names + ['-s', "1000"])
    t_end = time.monotonic() + LSL_LAUNCH_TIMEOUT
    available_streams = []
    while time.monotonic() < t_end:
        available_streams = LSLAmplifierAdapter.get_available_amplifiers('virtual')
        if stream_name in available_streams:
            break
    assert len(available_streams)
    recv_amp = LSLAmplifierAdapter(stream_name)
    recv_amp.start_sampling()
    samples = recv_amp.get_samples(SAMPLES_TO_CAPTURE)

    assert recv_amp.sampling_rate == 1000
    assert list(recv_amp.active_channels) == channel_names
    assert samples.samples.shape == (SAMPLES_TO_CAPTURE, len(channel_names))
    # excluding technical channels
    assert numpy.all(samples.samples[:, 0:-2] <= RANDOM_AMP_MAX_VALUE)
    assert numpy.all(samples.samples[:, 0:-2] >= RANDOM_AMP_MIN_VALUE)

    recv_amp.stop_sampling()
    process.kill()
    process.wait()


def test_lsl_streaming_runs_non_default_channels_and_sampling_rate_impedance():
    stream_name = str(uuid4())
    channel_names = "Random0 Random1 Random2 Random3".split()

    process = Popen([python, streamer_module_file, '-a', 'RandomAmplifier', '-n', stream_name,
                     '-c'] + channel_names + ['-s', "1000", '-i'])
    t_end = time.monotonic() + LSL_LAUNCH_TIMEOUT
    available_streams = []
    while time.monotonic() < t_end:
        available_streams = LSLAmplifierAdapter.get_available_amplifiers('virtual')
        if stream_name in available_streams:
            break
    assert len(available_streams)
    recv_amp = LSLAmplifierAdapter(stream_name)
    recv_amp.start_sampling()
    samples = recv_amp.get_samples(SAMPLES_TO_CAPTURE)

    assert recv_amp.sampling_rate == 1000
    assert len(recv_amp.active_channels) == len(channel_names) + 2
    assert "impedance" in recv_amp.active_channels[-1]
    assert list(recv_amp.active_channels[:len(channel_names)]) == list(channel_names)
    assert samples.samples.shape == (SAMPLES_TO_CAPTURE, len(channel_names) + 2)
    # excluding technical channels
    assert numpy.all(samples.samples[:, 0:-2] <= RANDOM_AMP_MAX_VALUE)
    assert numpy.all(samples.samples[:, 0:-2] >= RANDOM_AMP_MIN_VALUE)

    recv_amp.stop_sampling()
    process.kill()
    process.wait()


def test_lsl_streaming_errors():
    code = call([python, streamer_module_file, '-a', 'test1', '-l'])
    assert code > 0

    code = call([python, streamer_module_file, '-a', 'RandomAmplifier', '-c', "A1"])
    assert code == 151

    code = call([python, streamer_module_file, '-a', 'thisamplifierdoesntexist'])
    assert code == 151

    stream_name = str(uuid4())
    process = Popen([python, streamer_module_file, '-a', 'RandomAmplifier', '-n', stream_name])
    available_streams = []
    t_end = time.monotonic() + LSL_LAUNCH_TIMEOUT
    while time.monotonic() < t_end:
        available_streams = LSLAmplifierAdapter.get_available_amplifiers('virtual')
        if stream_name in available_streams:
            break
    assert len(available_streams)
    process_cant_have_name = Popen([python, streamer_module_file, '-a', 'RandomAmplifier', '-n', stream_name])
    code = process_cant_have_name.wait()
    assert code == 151
    process.kill()
    process.wait()
