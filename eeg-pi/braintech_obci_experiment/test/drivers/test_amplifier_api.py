#!/usr/bin/env python3
# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import logging
import math
import os
import subprocess
import time
import unittest
import unittest.mock as mock

import numpy
import pytest

import braintech.obci.experiment.test.tools

try:
    from braintech.drivers.native_amplifier_lib.native_lib import _native_lib
except ImportError:
    _native_lib = mock.MagicMock()

try:
    from braintech.drivers.native_amplifier_lib import dummy_amplifier
except ImportError:
    dummy_amplifier = mock.MagicMock()

try:
    from braintech.drivers.tmsi import amplifiers as amplifiers_tmsi
except ImportError:
    amplifiers_tmsi = mock.MagicMock()

try:
    from braintech.drivers.perun8 import amplifiers as amplifiers_perun8
except ImportError:
    amplifiers_perun8 = mock.MagicMock()

try:
    from braintech.drivers.perun8 import _perun8
except ImportError:
    _perun8 = mock.MagicMock()

try:
    from braintech.drivers import perun8
except ImportError:
    perun8 = mock.MagicMock()

from braintech.obci.core.drivers.eeg import openbci_amplifier
from braintech.obci.core.drivers.eeg import random_amplifier
from braintech.obci.core.drivers.eeg.eeg_amplifier import (AmplifierException, AmplifierDescription, EEGAmplifier,
                                                           NoSamplesException,
                                                           SamplingRateNotAvailable)
from braintech.obci.core.drivers.eeg.read_manager_amplifier import ReadManagerAmplifier

from braintech.obci.signal_processing.signal.data_generic_write_proxy import Impedance

LOG = logging.getLogger(__name__)


class AmplifierApiTests:
    AmplifierClass = None
    CHANNEL_TYPE_PREFIXES_FOR_IMPEDANCE_FLAG = {
        Impedance.PRESENT: [],
        Impedance.NOT_APPLICABLE: [],
        Impedance.UNKNOWN: [],
    }

    @classmethod
    def setUpClass(cls):
        if not amplifier_is_available(cls.AmplifierClass):
            if isinstance(cls.AmplifierClass, mock.MagicMock):
                message = '"braintech-drivers-native-amplifier-lib" is not installed. Please install and try again'
            else:
                message = 'Driver for {} had not been found. '.format(cls.AmplifierClass.__name__)
            LOG.info(message)
            raise unittest.SkipTest("Device not found")

    def setUp(self):
        self.amplifier = self.AmplifierClass()

    def tearDown(self):
        self.amplifier.stop_sampling()
        del self.amplifier

    def test_amplifier_description_correctness(self):
        description = self.amplifier.current_description
        assert isinstance(description, AmplifierDescription)

    def _test_sampling_rate(self, sample_rate, sampling_duration):
        self.amplifier.sampling_rate = sample_rate
        self.amplifier.start_sampling()
        assert self.amplifier.is_sampling
        self.amplifier.get_samples()

        start = time.time()
        for _ in range(int(sample_rate * sampling_duration)):
            for s in self.amplifier.get_samples().samples:
                assert isinstance(s, (numpy.ndarray)), "incorrect sample type"
        self.assertAlmostEqual(time.time() - start,
                               sampling_duration, delta=0.02, msg="Sampling rate {} failed".format(sample_rate))
        self.amplifier.stop_sampling()

    def test_sampling(self):
        for sampling_rate in self.amplifier.description.sampling_rates:
            self._test_sampling_rate(sampling_rate, sampling_duration=0.5)

    def test_active_channels(self):
        self._active_channels = [0, 1] + list(self.amplifier.description.channel_names[:2])
        self.amplifier.active_channels = self._active_channels
        self.amplifier.start_sampling()
        samples = self.amplifier.get_samples()
        assert len(samples.samples[0]) == len(self._active_channels), "Active Channels should work"

    def test_samples_per_packet(self):
        samples_per_packet = 10
        self.amplifier.start_sampling()
        packet = self.amplifier.get_samples(samples_per_packet)
        assert len(packet.ts) == samples_per_packet, "Samples per packet should be respected"
        assert len(packet.samples) == samples_per_packet, "Samples per packet should be respected"

    def test_exceptions(self):
        with self.assertRaises(AmplifierException):
            self.amplifier.get_samples()
        self.amplifier.active_channels = []
        with self.assertRaises(AmplifierException):
            self.amplifier.start_sampling()
        with self.assertRaises(AmplifierException):
            self.amplifier.active_channels = ['wrong']
            self.amplifier.current_description.channel_gains

    def test_properties(self):
        ACT_CH = 2
        self._active_channels = self.amplifier.description.channel_names[:ACT_CH]
        self.amplifier.active_channels = self._active_channels
        description = self.amplifier.current_description
        assert len(description.channel_gains) == ACT_CH
        assert len(description.channel_offsets) == ACT_CH
        assert len(description.channels_info) == ACT_CH
        assert set(description.channels_info[0].keys()).issuperset({'name', 'gain', 'offset', 'idle', 'filters'})
        self.amplifier.active_channels = ['1', 2]
        description = self.amplifier.current_description
        assert len(description.channel_gains) == 2
        assert isinstance(EEGAmplifier.get_available_amplifiers(), list)

    def test_impedance_is_sent_in_packet(self):
        active_channels = self.amplifier.active_channels
        self.amplifier.start_sampling()
        sample_packet = self.amplifier.get_samples()
        for idx, channel in enumerate(active_channels):
            self.assertIsNotNone(
                sample_packet.impedance.for_channel(channel_number=idx),
                msg="Couldn't fetch impedance for channel."
            )

    def test_impedance_has_correct_values(self):
        active_channels = self.amplifier.get_active_channels()
        self.amplifier.start_sampling()
        sample_packet = self.amplifier.get_samples()
        for idx, channel in enumerate(active_channels):
            impedance = sample_packet.impedance.for_channel(channel_number=idx)
            if self.impedance_should_be_present(channel.type):
                self.check_present_impedance_values(idx, channel, impedance)
            elif self.impedance_should_be_unknown(channel.type):
                error_msg = (
                    'Impedance flag: {} {}; should be: {} {}. '
                    'Channel name: {}; type: {}'.format(
                        impedance, type(impedance),
                        Impedance.UNKNOWN, type(Impedance.UNKNOWN),
                        channel.name, channel.type
                    )
                )
                assert impedance == Impedance.UNKNOWN, error_msg
            elif self.impedance_should_not_be_applicable(channel.type):
                error_msg = (
                    'Impedance flag: {} {}; should be: {} {}. '
                    'Channel name: {}; type: {}'.format(
                        impedance, type(impedance),
                        Impedance.NOT_APPLICABLE, type(Impedance.NOT_APPLICABLE),
                        channel.name, channel.type
                    )
                )
                assert impedance == Impedance.NOT_APPLICABLE, error_msg
            else:
                error_msg = (
                    'Unrecognizable impedance flag of value: {} '
                    '(Possible values: present={} unknown={} not_applicable{})'
                    ''.format(
                        impedance, Impedance.PRESENT,
                        Impedance.UNKNOWN, Impedance.NOT_APPLICABLE
                    )
                )
                self.fail(error_msg)

    def check_present_impedance_values(self, idx, channel, impedance):
        raise NotImplementedError()

    def impedance_should_be_present(self, channel_type_name):
        """Impedance should be present for this channel."""
        return self.matchin_prefix_exists(
            text=channel_type_name,
            prefixes=self.CHANNEL_TYPE_PREFIXES_FOR_IMPEDANCE_FLAG[Impedance.PRESENT],
        )

    def impedance_should_be_unknown(self, channel_type_name):
        """Impedance may exists for this channel but is not present."""
        return self.matchin_prefix_exists(
            text=channel_type_name,
            prefixes=self.CHANNEL_TYPE_PREFIXES_FOR_IMPEDANCE_FLAG[Impedance.UNKNOWN],
        )

    def impedance_should_not_be_applicable(self, channel_type_name):
        """If it's a technic channel (ex: battery) then sending impedance does not have sense."""
        return self.matchin_prefix_exists(
            text=channel_type_name,
            prefixes=self.CHANNEL_TYPE_PREFIXES_FOR_IMPEDANCE_FLAG[Impedance.NOT_APPLICABLE],
        )

    def matchin_prefix_exists(self, text: str, prefixes: []):
        for prefix in prefixes:
            if text.startswith(prefix):
                return True
        else:
            return False


class RandomAmplifier(random_amplifier.RandomAmplifier):
    long_initialization = 1
    _description = AmplifierDescription(
        name=random_amplifier.RandomAmplifier.name,
        sampling_rates=[128, 512],
        channels=AmplifierDescription.UNKNOWN
    )

    def _get_samples(self, samples_per_packet):
        is_the_first_run = self._next_sample_time is None
        if is_the_first_run and self.long_initialization:
            time.sleep(self.long_initialization)
        return super()._get_samples(samples_per_packet)


class TestRandomAmplifier(AmplifierApiTests, unittest.TestCase):
    AmplifierClass = RandomAmplifier
    CHANNEL_TYPE_PREFIXES_FOR_IMPEDANCE_FLAG = {
        Impedance.PRESENT: ['EEG'],
        Impedance.NOT_APPLICABLE: ['ZAAG', 'TECH'],
        Impedance.UNKNOWN: [],
    }

    def check_present_impedance_values(self, idx, channel, impedance):
        assert idx % 2, 'RandomAmplifier should send impedance only for even channels, ' \
                        'counting from 0. ({channel_name}; idx={idx})'.format(channel_name=channel.name, idx=idx)

    def test_automatic_sampling_rates(self):
        SUPER_SAMPLING_RATE = 12345
        with pytest.raises(SamplingRateNotAvailable):
            self.amplifier.sampling_rate = SUPER_SAMPLING_RATE
        self.amplifier.description.sampling_rates = AmplifierDescription.ALL
        self.amplifier.sampling_rate = SUPER_SAMPLING_RATE
        assert self.amplifier.sampling_rate == SUPER_SAMPLING_RATE
        self.amplifier.start_sampling()
        self.amplifier.get_samples(1)
        start = time.time()
        self.amplifier.get_samples(int(SUPER_SAMPLING_RATE / 10))
        assert time.time() - start < 0.5, "RandomAmplifier should sample with super speed"
        self.amplifier.stop_sampling()


class TestTMSIAmplifier(AmplifierApiTests, unittest.TestCase):
    AmplifierClass = amplifiers_tmsi.TmsiCppAmplifier
    CHANNEL_TYPE_PREFIXES_FOR_IMPEDANCE_FLAG = {
        Impedance.PRESENT: [],
        Impedance.NOT_APPLICABLE: [
            'UNKNOWN', 'AUX', 'DIG', 'TIME', 'LEAK', 'PRESSURE',
            'ENVELOPE', 'MARKER', 'ZAAG', 'SAO2',
            'trig',  # TriggerChannel
            'onoff',  # OnOffChannel
            'bat',  # BatteryChannel
        ],
        Impedance.UNKNOWN: ['EXG', 'BIP'],
    }

    def test_active_channels(self):
        raise unittest.SkipTest(
            'Redmine issue: #40991, '
            'link: https://redmine.titanis.pl/issues/40991'
        )

    def test_properties(self):
        raise unittest.SkipTest(
            'Redmine issue: #40991, '
            'link: https://redmine.titanis.pl/issues/40991'
        )

    def test_exceptions(self):
        raise unittest.SkipTest(
            'Redmine issue: #40992, '
            'link: https://redmine.titanis.pl/issues/40992'
        )

    def test_sampling(self):
        raise unittest.SkipTest(
            'Redmine issue: #40993, '
            'link: https://redmine.titanis.pl/issues/40993'
        )

    def check_present_impedance_values(self, idx, channel, impedance):
        error_msg = (
            'TMSI amplifier do not send impedance for channel: '
            '{channel_type}(idx={idx})'.format(
                channel_type=channel.type, idx=idx
            )
        )
        self.fail(error_msg)


class TestReadManager(AmplifierApiTests, unittest.TestCase):
    AmplifierClass = ReadManagerAmplifier
    CHANNEL_TYPE_PREFIXES_FOR_IMPEDANCE_FLAG = {
        Impedance.PRESENT: [],
        Impedance.NOT_APPLICABLE: [],
        Impedance.UNKNOWN: [''],
    }

    def setUp(self):
        super().setUp()
        self.amplifier.info_source = os.path.join(os.path.dirname(__file__), 'data', 'wakeEEG.obci.xml')
        self.amplifier.data_source = self.amplifier.info_source.replace('.xml', '.raw')
        self.amplifier.tags_source = self.amplifier.info_source.replace('.xml', '.tag')
        self.amplifier.init()

    def test_indexes(self):
        self.amplifier.active_channels = list(reversed(self.amplifier.description.channel_names[1:3]))
        self.amplifier.start_sampling()
        samples = self.amplifier.get_samples()
        assert samples.channel_count == 2

    def test_tags(self):
        with braintech.obci.experiment.test.tools.disable_sampling_rate_check():
            self.amplifier.sampling_rate = 5000
        self.amplifier.start_sampling()

        all_tags = []
        while self.amplifier.is_sampling:
            try:
                samples = self.amplifier.get_samples()
            except NoSamplesException:
                break
            tags = self.amplifier.get_tags()
            if tags:
                for tag in tags:
                    assert math.isclose(tag['start_timestamp'], samples.ts[0], abs_tol=0.2)

            all_tags += tags
        assert len(all_tags) == 6


class TestOpenBciAmplifier(AmplifierApiTests, unittest.TestCase):
    AmplifierClass = openbci_amplifier.OpenBciAmplifier
    CHANNEL_TYPE_PREFIXES_FOR_IMPEDANCE_FLAG = {
        Impedance.PRESENT: [],
        Impedance.NOT_APPLICABLE: ['AUX'],
        Impedance.UNKNOWN: ['EEG'],
    }

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        subprocess.run(['obci', 'srv'])

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        subprocess.run(['obci', 'srv_kill'])


class TestDummyCppAmplifier(AmplifierApiTests, unittest.TestCase):
    AmplifierClass = dummy_amplifier.DummyCppBaseAmplifier
    CHANNEL_TYPE_PREFIXES_FOR_IMPEDANCE_FLAG = {
        Impedance.PRESENT: [],
        Impedance.NOT_APPLICABLE: [''],
        Impedance.UNKNOWN: [],
    }

    def test_active_channels(self):
        raise unittest.SkipTest(
            'Redmine issue: #40991, '
            'link: https://redmine.titanis.pl/issues/40991'
        )

    def test_properties(self):
        raise unittest.SkipTest(
            'Redmine issue: #40991, '
            'link: https://redmine.titanis.pl/issues/40991'
        )

    def test_exceptions(self):
        raise unittest.SkipTest(
            'Redmine issue: #40992, '
            'link: https://redmine.titanis.pl/issues/40992'
        )

    def test_amplifier_description_correctness(self):
        raise unittest.SkipTest(
            'Redmine issue: #41192, '
            'link: https://redmine.titanis.pl/issues/41192'
        )

    def test_samples_per_packet(self):
        raise unittest.SkipTest(
            'Redmine issue: #41193, '
            'link: https://redmine.titanis.pl/issues/41193'
        )

    def test_sampling(self):
        raise unittest.SkipTest(
            'Redmine issue: #43877, '
            'link: https://redmine.titanis.pl/issues/43877'
        )

    def test_impedance_has_correct_values(self):
        raise unittest.SkipTest(
            'Redmine issue: #43877, '
            'link: https://redmine.titanis.pl/issues/43877'
        )

    def test_impedance_is_sent_in_packet(self):
        raise unittest.SkipTest(
            'Redmine issue: #43877, '
            'link: https://redmine.titanis.pl/issues/43877'
        )


class TestPerunCppAmplifier(AmplifierApiTests, unittest.TestCase):
    AmplifierClass = amplifiers_perun8.PerunCppAmplifier
    CHANNEL_TYPE_PREFIXES_FOR_IMPEDANCE_FLAG = {
        Impedance.PRESENT: ['EXG EEG'],
        Impedance.NOT_APPLICABLE: [''],
        Impedance.UNKNOWN: [],
    }

    def setUp(self):
        super().setUp()
        # Brain Amplifier supports sampling rate of 500 only
        self.amplifier.sampling_rate = 500

    def check_present_impedance_values(self, idx, channel, impedance):
        error_msg = (
            'Impedance should be present for channel {idx}:{name}. '
            'Got flag "{flag}" of type={flag_type}'.format(
                idx=idx, name=channel.name,
                flag=impedance, flag_type=type(impedance)
            )
        )
        assert type(impedance) == numpy.ndarray, error_msg

    def test_active_channels(self):
        raise unittest.SkipTest(
            'Redmine issue: #40991, '
            'link: https://redmine.titanis.pl/issues/40991'
        )

    def test_properties(self):
        raise unittest.SkipTest(
            'Redmine issue: #40991, '
            'link: https://redmine.titanis.pl/issues/40991'
        )

    def test_exceptions(self):
        raise unittest.SkipTest(
            'Redmine issue: #40992, '
            'link: https://redmine.titanis.pl/issues/40992'
        )


def amplifier_is_available(amplifier_class) -> bool:
    physical_amplifiers = {
        amplifiers_perun8.PerunCppAmplifier,
        amplifiers_tmsi.TmsiCppAmplifier,
        openbci_amplifier.OpenBciAmplifier,
    }
    virtual_amplifiers = {
        RandomAmplifier,
        ReadManagerAmplifier,
        dummy_amplifier.DummyCppBaseAmplifier,
    }
    if amplifier_class in virtual_amplifiers:
        is_available = True
    elif (
        amplifier_class in physical_amplifiers
        and not isinstance(amplifier_class, mock.MagicMock)
    ):
        LOG.info('Running discovery for {}'.format(amplifier_class.name))
        is_available = bool(amplifier_class.get_available_amplifiers())
    else:
        is_available = False

    return is_available


@pytest.mark.skipif(
    isinstance(perun8, mock.MagicMock),
    reason="There is no perun8 package installed",
)
@mock.patch.object(amplifiers_perun8, 'PyAmplifierPerun8')
def test_brain_amplifier_locking(mock_PyAmplifierPerun8):
    amplifier_mock = mock.MagicMock(spec=_native_lib.PyAmplifier)
    brain_py_amplifier_description = _get_mock_brain_py_amplifiers_description()
    amplifier_mock.get_description.return_value = brain_py_amplifier_description
    amplifier_mock.get_active_channels.return_value = [
        channel['name']
        for channel in brain_py_amplifier_description['channels']
    ]
    mock_PyAmplifierPerun8.getAvailablePerunAmplifiers.return_value = [
        'Brain Amplifier {}'.format(idx)
        for idx in range(1, amplifiers_perun8.PerunCppAmplifier.MAX_BRAIN_AMPLIFIERS + 1)
    ]
    mock_PyAmplifierPerun8.return_value = amplifier_mock
    amplifier_ids = amplifiers_perun8.PerunCppAmplifier.get_available_amplifiers()
    amplifier_1_id, amplifier_2_id, *other_amplifier_ids = amplifier_ids

    amplifier_1 = amplifiers_perun8.PerunCppAmplifier(amplifier_1_id)
    assert set(amplifiers_perun8.PerunCppAmplifier.get_available_amplifiers()) == set(amplifier_ids)
    amplifier_1.start_sampling()
    assert set(amplifiers_perun8.PerunCppAmplifier.get_available_amplifiers()) == set()
    amplifier_1_copy = amplifiers_perun8.PerunCppAmplifier(amplifier_1_id)
    with pytest.raises(amplifiers_perun8.CantConnectToAmplifier):
        amplifier_1_copy.start_sampling()

    amplifier_2 = amplifiers_perun8.PerunCppAmplifier(amplifier_2_id)
    assert set(amplifiers_perun8.PerunCppAmplifier.get_available_amplifiers()) == set()
    amplifier_2.start_sampling()
    assert set(amplifiers_perun8.PerunCppAmplifier.get_available_amplifiers()) == set()
    amplifier_2_copy = amplifiers_perun8.PerunCppAmplifier(amplifier_2_id)
    with pytest.raises(amplifiers_perun8.CantConnectToAmplifier):
        amplifier_2_copy.start_sampling()

    amplifier_1.stop_sampling()
    assert set(amplifiers_perun8.PerunCppAmplifier.get_available_amplifiers()) == set()
    amplifier_1_copy = amplifiers_perun8.PerunCppAmplifier(amplifier_1_id)
    amplifier_1_copy.start_sampling()
    assert set(amplifiers_perun8.PerunCppAmplifier.get_available_amplifiers()) == set()

    amplifier_2.stop_sampling()
    assert set(amplifiers_perun8.PerunCppAmplifier.get_available_amplifiers()) == set()
    amplifier_2_copy = amplifiers_perun8.PerunCppAmplifier(amplifier_2_id)
    amplifier_2_copy.start_sampling()
    assert set(amplifiers_perun8.PerunCppAmplifier.get_available_amplifiers()) == set()

    amplifier_1_copy.stop_sampling()
    assert set(amplifiers_perun8.PerunCppAmplifier.get_available_amplifiers()) == set()
    amplifier_2_copy.stop_sampling()
    assert set(amplifiers_perun8.PerunCppAmplifier.get_available_amplifiers()) == set(amplifier_ids)


def _get_mock_brain_py_amplifiers_description() -> dict:
    return {
        'channels': [
            {
                'impedance': 2,
                'filters': [
                    {
                        'a': [1.0, -1.2e-16, 0.9489645667148798],
                        'b': [0.9744822833574399, -1.2e-16, 0.9744822833574399]
                    }
                ],
                'idle': -2147483648,
                'gain': 0.04465999826788902,
                'offset': 0.0,
                'name': 'P3'
            },
            {
                'impedance': 2,
                'filters': [
                    {
                        'a': [1.0, -1.2e-16, 0.9489645667148798],
                        'b': [0.9744822833574399, -1.2e-16, 0.9744822833574399]
                    }
                ],
                'idle': -2147483648,
                'gain': 0.04465999826788902,
                'offset': 0.0,
                'name': 'Cz'
            },
            {
                'impedance': 2,
                'filters': [
                    {
                        'a': [1.0, -1.2e-16, 0.9489645667148798],
                        'b': [0.9744822833574399, -1.2e-16, 0.9744822833574399]
                    }
                ],
                'idle': -2147483648,
                'gain': 0.04465999826788902,
                'offset': 0.0,
                'name': 'O2'
            },
            {
                'impedance': 2,
                'filters': [
                    {
                        'a': [1.0, -1.2e-16, 0.9489645667148798],
                        'b': [0.9744822833574399, -1.2e-16, 0.9744822833574399]
                    }
                ],
                'idle': -2147483648,
                'gain': 0.04465999826788902,
                'offset': 0.0,
                'name': 'P4'
            },
            {
                'impedance': 2,
                'filters': [
                    {
                        'a': [1.0, -1.2e-16, 0.9489645667148798],
                        'b': [0.9744822833574399, -1.2e-16, 0.9744822833574399]
                    }
                ],
                'idle': -2147483648,
                'gain': 0.04465999826788902,
                'offset': 0.0,
                'name': 'C3'
            },
            {
                'impedance': 2,
                'filters': [
                    {
                        'a': [1.0, -1.2e-16, 0.9489645667148798],
                        'b': [0.9744822833574399, -1.2e-16, 0.9744822833574399]
                    }
                ],
                'idle': -2147483648,
                'gain': 0.04465999826788902,
                'offset': 0.0,
                'name': 'O1'
            },
            {
                'impedance': 2,
                'filters': [
                    {
                        'a': [1.0, -1.2e-16, 0.9489645667148798],
                        'b': [0.9744822833574399, -1.2e-16, 0.9744822833574399]
                    }
                ],
                'idle': -2147483648,
                'gain': 0.04465999826788902,
                'offset': 0.0,
                'name': 'Pz'
            },
            {
                'impedance': 2,
                'filters': [
                    {
                        'a': [1.0, -1.2e-16, 0.9489645667148798],
                        'b': [0.9744822833574399, -1.2e-16, 0.9744822833574399]
                    }
                ],
                'idle': -2147483648,
                'gain': 0.04465999826788902,
                'offset': 0.0,
                'name': 'C4'
            },
            {
                'impedance': 1,
                'filters': [],
                'idle': -2147483648,
                'gain': 4.0,
                'offset': 0.0,
                'name': 'ACC_x'
            },
            {
                'impedance': 1,
                'filters': [],
                'idle': -2147483648,
                'gain': 4.0,
                'offset': 0.0,
                'name': 'ACC_y'
            },
            {
                'impedance': 1,
                'filters': [],
                'idle': -2147483648,
                'gain': 4.0,
                'offset': 0.0,
                'name': 'ACC_z'
            },
            {
                'impedance': 1,
                'filters': [],
                'idle': -128,
                'gain': 1.0,
                'offset': 0.0,
                'name': 'RSSI'
            },
            {
                'impedance': 1,
                'filters': [],
                'idle': 2147483648,
                'gain': 0.00025,
                'offset': 0.0,
                'name': 'RFTime'
            },
            {
                'impedance': 1,
                'filters': [],
                'idle': 2147483648,
                'gain': 1.0,
                'offset': 0.0,
                'name': 'Sample_Counter'
            }
        ],
        'physical_channels': 13,
        'name': 'Brain Amplifier',
        'sampling_rates': [500.0]
    }


if __name__ == "__main__":
    unittest.main()
