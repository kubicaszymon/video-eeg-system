#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.
from braintech.drivers.native_amplifier_lib.dummy_amp._dummy_amp import PyAmplifierDummy

import numpy as np


def log_callback(msg):
    print('LOG: {}'.format(msg))


def test_dummy_amplifier():
    amp = PyAmplifierDummy(
        {'no_such_option': 'xoxox'},
        log_callback)

    description = amp.get_description()

    channel_names = [ch['name'] for ch in description['channels']]
    assert 'Saw' in channel_names
    assert 'Sample_Counter' in channel_names

    assert not amp.is_sampling()
    amp.start_sampling()
    assert amp.is_sampling()
    amp.stop_sampling()
    assert not amp.is_sampling()

    amp.start_sampling()

    ch = amp.get_active_channels()
    print('Active channels (total {}):'.format(len(ch)))
    for i, c in enumerate(ch):
        print('{:2}. {}'.format(i + 1, c))

    print('Sampling rate:', amp.get_sampling_rate())

    for i in range(20):
        s_vec = amp.get_samples_vec(10)
        assert type(s_vec[0]) == np.ndarray
        assert type(s_vec[1]) == np.ndarray
        assert s_vec[0].shape == (10, 27)
        # print(s_vec)


if __name__ == '__main__':
    test_dummy_amplifier()
