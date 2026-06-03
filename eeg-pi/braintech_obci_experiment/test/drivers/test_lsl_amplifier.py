# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

from unittest import mock

import pylsl
import pytest

from braintech.obci.core.drivers.eeg.lsl_amplifier import LSLAmplifierAdapter
from braintech.obci.core.drivers.eeg import lsl_amplifier
from braintech.obci.signal_processing.signal.data_generic_write_proxy import SamplePacket

from data import lsl_mock_data


@pytest.mark.incremental
@mock.patch('pylsl.resolve_streams')
class TestGettingStreams:
    def test_no_streams(self, resolve_streams):
        resolve_streams.return_value = []
        assert lsl_amplifier._get_streams() == []

    def test_matching_streams(self, resolve_streams):
        stream1 = pylsl.StreamInfo(type='signal')
        resolve_streams.return_value = [stream1]
        output = lsl_amplifier._get_streams()
        assert len(output) == 1
        assert {s.type() for s in output} == {'signal'}
        stream2 = pylsl.StreamInfo(type='eeg')
        resolve_streams.return_value = [stream1, stream2]
        output = lsl_amplifier._get_streams()
        assert len(output) == 2
        assert {s.type() for s in output} == {'signal', 'eeg'}
        stream3 = pylsl.StreamInfo(type='signal')
        stream4 = pylsl.StreamInfo(type='eeg')
        resolve_streams.return_value = [stream1, stream2, stream3, stream4]
        output = lsl_amplifier._get_streams()
        assert len(output) == 4
        assert {s.type() for s in output} == {'signal', 'eeg'}

    def test_not_matching_streams(self, resolve_streams):
        stream1 = pylsl.StreamInfo(type='signal')
        stream2 = pylsl.StreamInfo(type='lol')
        stream3 = pylsl.StreamInfo(type='whatever')
        resolve_streams.return_value = [stream1, stream2, stream3]
        output = lsl_amplifier._get_streams()
        assert len(output) == 1
        assert {s.type() for s in output} == {'signal'}


@pytest.mark.incremental
@mock.patch('braintech.obci.core.drivers.eeg.lsl_amplifier._get_streams')
class TestGettingStreamsByName:
    def test_matching_none(self, _get_streams):
        _get_streams.return_value = []
        with pytest.raises(lsl_amplifier.RequestedLSLStreamMissing):
            lsl_amplifier._get_stream_by_name('MissingNo.')

        stream1 = pylsl.StreamInfo(name='Niespodzianka')
        _get_streams.return_value = [stream1]
        with pytest.raises(lsl_amplifier.RequestedLSLStreamMissing):
            lsl_amplifier._get_stream_by_name('MissingNo.')

        stream2 = pylsl.StreamInfo(name='Lubię placki')
        stream3 = pylsl.StreamInfo(name='Jagodowe')
        _get_streams.return_value = [stream1, stream2, stream3]
        with pytest.raises(lsl_amplifier.RequestedLSLStreamMissing):
            lsl_amplifier._get_stream_by_name('MissingNo.')

    def test_matching_singleton(self, _get_streams):
        stream = pylsl.StreamInfo(name='lolo')
        _get_streams.return_value = [stream]
        result = lsl_amplifier._get_stream_by_name('lolo')
        assert result.name() == 'lolo'

    def test_matching_one_of_many(self, _get_streams):
        stream1 = pylsl.StreamInfo(name='Japońskie krzaki')
        stream2 = pylsl.StreamInfo(name='Evelup')
        stream3 = pylsl.StreamInfo(name='Chińskie krzewy')
        _get_streams.return_value = [stream1, stream2, stream3]
        result = lsl_amplifier._get_stream_by_name('Evelup')
        assert result.name() == 'Evelup'

    def test_matching_many_of_many(self, _get_streams):
        stream1 = pylsl.StreamInfo(name='Krzaki')
        stream2 = pylsl.StreamInfo(name='Krzaki')
        stream3 = pylsl.StreamInfo(name='Krzaki')
        _get_streams.return_value = [stream1, stream2, stream3]
        with pytest.raises(lsl_amplifier.MultipleStreamsMatched):
            lsl_amplifier._get_stream_by_name('Krzaki')


@pytest.mark.incremental
class TestGettingAvailableAmplifiers:
    def test_wrong_device_type(self):
        output = LSLAmplifierAdapter.get_available_amplifiers()
        assert output == []
        output = LSLAmplifierAdapter.get_available_amplifiers('bt')
        assert output == []
        output = LSLAmplifierAdapter.get_available_amplifiers('usb')
        assert output == []
        output = LSLAmplifierAdapter.get_available_amplifiers('wiiboard')
        assert output == []

    @mock.patch('braintech.obci.core.drivers.eeg.lsl_amplifier._get_streams')
    def test_no_streams(self, _get_streams):
        _get_streams.return_value = []
        output = LSLAmplifierAdapter.get_available_amplifiers('virtual')
        assert output == []

    @mock.patch('braintech.obci.core.drivers.eeg.lsl_amplifier._get_streams')
    def test_with_one_stream(self, _get_streams):
        stream = mock.Mock()
        stream.name.return_value = 'MaryAnn Dovgialo'
        _get_streams.return_value = [stream]
        output = LSLAmplifierAdapter.get_available_amplifiers('virtual')
        assert set(output) == {'MaryAnn Dovgialo'}

    @mock.patch('braintech.obci.core.drivers.eeg.lsl_amplifier._get_streams')
    def test_with_multiple_streams(self, _get_streams):
        stream1 = mock.Mock()
        stream1.name.return_value = 'deep stream with only deep thoughts'
        stream2 = mock.Mock()
        stream2.name.return_value = 'unhealthy thought loops'
        stream3 = mock.Mock()
        stream3.name.return_value = 'hot chocolate stream'
        _get_streams.return_value = [stream1, stream2, stream3]
        output = LSLAmplifierAdapter.get_available_amplifiers('virtual')
        assert set(output) == {
            'deep stream with only deep thoughts',
            'unhealthy thought loops',
            'hot chocolate stream',
        }


@pytest.mark.incremental
@mock.patch('braintech.obci.core.drivers.eeg.lsl_amplifier._get_channel_names')
@mock.patch('braintech.obci.core.drivers.eeg.lsl_amplifier._get_streams')
@mock.patch('braintech.obci.core.drivers.eeg.lsl_amplifier.TimeConverter', mock.Mock())
class TestReadingLSL:
    @mock.patch('braintech.obci.core.drivers.eeg.lsl_amplifier._calculate_creation_time')
    def test_creating_with_stream_by_creation_time(self, _calculate_creation_time,
                                                   _get_streams, _get_channel_names):
        stream = pylsl.StreamInfo(channel_count=3, nominal_srate=512)
        _get_streams.return_value = [stream]
        _get_channel_names.return_value = ['LSL 1', 'LSL 2', 'LSL 3']
        _calculate_creation_time.return_value = 0
        adapter = LSLAmplifierAdapter()
        assert list(adapter._description.channel_names) == ['LSL 1', 'LSL 2', 'LSL 3']
        assert adapter._inlet is not None

    def test_creating_with_no_streams(self, _get_streams, _get_channel_names):
        _get_streams.return_value = []
        _get_channel_names.return_value = []
        with pytest.raises(lsl_amplifier.NoLSLStreamAvailable):
            LSLAmplifierAdapter()

    @mock.patch('braintech.obci.core.drivers.eeg.lsl_amplifier._calculate_creation_time')
    @mock.patch('braintech.obci.core.drivers.eeg.lsl_amplifier.LSLAmplifierAdapter._get_chunk')
    def test_reading_sample_chunk(self, _get_chunk, _calculate_creation_time,
                                  _get_streams, _get_channel_names):
        stream = pylsl.StreamInfo(channel_count=4, nominal_srate=512)
        _get_streams.return_value = [stream]
        _get_channel_names.return_value = ['LSL1', 'LSL2', 'LSL3', 'LSL4']
        _calculate_creation_time.return_value = 0
        adapter = LSLAmplifierAdapter()
        _get_chunk.return_value = lsl_mock_data.chunk
        output = adapter._get_samples(samples_per_packet=16)
        assert type(output) == SamplePacket
        assert len(output.samples) == 16
        assert len(output.samples[0]) == 4
        assert output.samples[0][0] == 1.6593127250671387
        assert len(output.ts) == 16


@mock.patch('time.time')
@mock.patch('pylsl.local_clock')
@pytest.mark.incremental
class TestTimeConverter:
    def test_remote_lsl_to_local_lsl(self, _, __):
        inlet = mock.Mock()
        inlet.time_correction.return_value = 5
        converter = lsl_amplifier.TimeConverter(inlet)
        assert converter._remote_lsl_to_local_lsl(lsl_time_there=0) == 5
        assert converter._remote_lsl_to_local_lsl(lsl_time_there=1) == 6
        inlet.time_correction.return_value = 20
        assert converter._remote_lsl_to_local_lsl(lsl_time_there=1) == 21

    def test_lsl2unix_with_time_equal_to_start_time(self, pylsl_local_clock,
                                                    time_time):
        inlet = mock.Mock()
        inlet.time_correction.return_value = 5
        converter = lsl_amplifier.TimeConverter(inlet)
        converter._start_local_lsl_time = 200
        pylsl_local_clock.return_value = 200
        converter._start_unix_time = 2000
        time_time.return_value = 2000
        assert converter._local_lsl_to_local_unix(lsl_time_here=200) == 2000

    def test_lsl2unix_with_time_after_start_time_without_drift(
            self, pylsl_local_clock, time_time):
        converter = lsl_amplifier.TimeConverter(mock.Mock())
        converter._start_local_lsl_time = 200
        pylsl_local_clock.return_value = 210
        converter._start_unix_time = 2000
        time_time.return_value = 2010
        assert converter._local_lsl_to_local_unix(lsl_time_here=210) == 2010
        assert converter._local_lsl_to_local_unix(lsl_time_here=205) == 2005

    def test_lsl2unix_with_time_after_start_time_with_drift(
            self, pylsl_local_clock, time_time):
        converter = lsl_amplifier.TimeConverter(mock.Mock())
        converter._start_local_lsl_time = 200
        pylsl_local_clock.return_value = 210
        converter._start_unix_time = 2000
        time_time.return_value = 2020
        assert converter._local_lsl_to_local_unix(lsl_time_here=210) == 2020
        assert converter._local_lsl_to_local_unix(lsl_time_here=205) == 2010

    def test_lsl2unix_with_time_before_start_time_without_drift(
            self, pylsl_local_clock, time_time):
        converter = lsl_amplifier.TimeConverter(mock.Mock())
        converter._start_local_lsl_time = 200
        pylsl_local_clock.return_value = 210
        converter._start_unix_time = 2000
        time_time.return_value = 2010
        assert converter._local_lsl_to_local_unix(lsl_time_here=190) == 1990
        assert converter._local_lsl_to_local_unix(lsl_time_here=195) == 1995

    def test_lsl2unix_with_time_before_start_time_with_drift(
            self, pylsl_local_clock, time_time):
        converter = lsl_amplifier.TimeConverter(mock.Mock())
        converter._start_local_lsl_time = 200
        pylsl_local_clock.return_value = 210
        converter._start_unix_time = 2000
        time_time.return_value = 2020
        assert converter._local_lsl_to_local_unix(lsl_time_here=190) == 1980
        assert converter._local_lsl_to_local_unix(lsl_time_here=195) == 1990

    def test_remote_lsl_to_local_unix(self, pylsl_local_clock, time_time):
        inlet = mock.Mock()
        inlet.time_correction.return_value = 105
        converter = lsl_amplifier.TimeConverter(inlet)
        converter._start_local_lsl_time = 200
        pylsl_local_clock.return_value = 210
        converter._start_unix_time = 2000
        time_time.return_value = 2020
        assert converter.remote_lsl_to_local_unix(lsl_time_there=90) == 1990
        assert converter.remote_lsl_to_local_unix(lsl_time_there=95) == 2000
        assert converter.remote_lsl_to_local_unix(lsl_time_there=100) == 2010
        assert converter.remote_lsl_to_local_unix(lsl_time_there=105) == 2020
