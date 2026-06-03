#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.
from braintech.drivers.perun8._perun8 import PyAmplifierPerun8
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


def test_perun_amplifier():
    print(PyAmplifierPerun8.getAvailablePerunAmplifiers())
    amp = PyAmplifierPerun8({'device_index': 0}, log_callback)
    desc = amp.get_description()
    amp.set_active_channels([c['name'] for c in desc['channels']])
    amp.get_active_channels()
    amp.start_sampling()
    for i in range(10):
        amp.get_samples_vec(10)
    amp.stop_sampling()


if __name__ == '__main__':
    test_perun_amplifier()
