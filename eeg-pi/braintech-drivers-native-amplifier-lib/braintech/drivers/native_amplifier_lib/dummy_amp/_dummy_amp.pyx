# cython: language_level=3, embedsignature=True
# -*- coding: utf-8 -*-
# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

from braintech.drivers.native_amplifier_lib.native_lib._native_lib cimport PyAmplifier
from braintech.drivers.native_amplifier_lib.native_lib._native_lib cimport Amplifier
from braintech.drivers.native_amplifier_lib.native_lib._native_lib cimport AmplifierOptions
from braintech.drivers.native_amplifier_lib.native_lib._native_lib cimport log_callback


cdef extern from "DummyAmplifier.h":
    cdef cppclass DummyAmplifier(Amplifier):
        DummyAmplifier() except +


cdef class PyAmplifierDummy(PyAmplifier):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __cinit__(self, params=None, log_callback_func=None):
        cdef AmplifierOptions * opt

        opt = NULL

        if params is None:
            params = {}

        self._amp = new DummyAmplifier()

        if log_callback_func is not None:
            self._amp.set_log_callback(log_callback, < void *> log_callback_func)
            self._log_callback_func = log_callback_func
        else:
            self._log_callback_func = None

        try:
            opt = new AmplifierOptions()
            if 'sampling_rate' in params:
                opt.sampling_rate = int(params['sampling_rate'])
            if 'active_channels' in params:
                opt.active_channels = params['active_channels'].encode('utf-8')

            self._amp.init(opt[0])
        finally:
            if opt != NULL:
                del opt


