#!/usr/bin/env python3
# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.
import os
import hashlib
import shutil
import tempfile
import numpy as np
from braintech.obci.signal_processing.signal.revfilter import reverse_impedance_filter
from braintech.obci.signal_processing import read_manager


def get_file_tmp_copy(ext):
    file_path = os.path.join(os.path.dirname(__file__), 'data', 'random.' + ext)
    return shutil.copy(file_path, tempfile.gettempdir())


def test_empty_filter():
    """Input.raw should not change when no filter is specified."""
    def get_file_hash(path):
        return hashlib.md5(open(path, 'rb').read()).hexdigest()

    xml_copy, raw_copy = [get_file_tmp_copy(ext) for ext in ['xml', 'raw']]
    hash_pre = get_file_hash(raw_copy)
    reverse_impedance_filter(xml_copy, raw_copy, [[]])
    assert hash_pre == get_file_hash(raw_copy)


def test_sample_filter():
    """Non empty filtering should work. Here we test a 50Hz cutoff filter cascade."""
    xml_copy, raw_copy = [get_file_tmp_copy(ext) for ext in ['xml', 'raw']]

    def get_fft_at50hz():
        at50hz = 50
        mgr = read_manager.ReadManager(xml_copy, raw_copy, None)
        fft = np.fft.fft(mgr.get_all_samples()[0])
        sampling_frequency = int(float(mgr.get_param('sampling_frequency')))
        assert sampling_frequency == 128  # filters b/a params assume 128Hz
        return fft[int(len(fft) / 2 * at50hz / (sampling_frequency / 2))]

    pre = get_fft_at50hz()
    reverse_impedance_filter(xml_copy, raw_copy, [
        [{'b': [0.95327945, -0.95327945], 'a': [1., -0.9065589]},
         {'b': [0.79968847, 1.23633509, 0.79968847], 'a': [1., 1.23633509, 0.59937693]}]])
    assert abs(pre) > 2 * abs(get_fft_at50hz())
