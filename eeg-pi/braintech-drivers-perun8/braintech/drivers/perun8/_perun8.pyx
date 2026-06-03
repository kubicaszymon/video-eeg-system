# cython: language_level=3, embedsignature=True
# -*- coding: utf-8 -*-
# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import json
import numpy as np
cimport numpy as np

from libcpp cimport bool
from libcpp.string cimport string
from libcpp.vector cimport vector

from braintech.drivers.native_amplifier_lib.native_lib._native_lib cimport PyAmplifier
from braintech.drivers.native_amplifier_lib.native_lib._native_lib cimport Amplifier
from braintech.drivers.native_amplifier_lib.native_lib._native_lib cimport AmplifierOptions
from braintech.drivers.native_amplifier_lib.native_lib._native_lib cimport log_callback


cdef extern from "PerunAmplifier.h":
    cdef cppclass PerunAmplifierOptions(AmplifierOptions):
        int device_index
        bool measure_impedance

    cdef cppclass PerunAmplifier(Amplifier):
        BrainAmplifier() except +
        @staticmethod
        vector[string] getAvailable();

cdef class PyAmplifierPerun8(PyAmplifier):
    @staticmethod
    def getAvailablePerunAmplifiers():
        available = PerunAmplifier.getAvailable()
        return [s.decode('utf-8') for s in available]

    def __cinit__(self, params=None, log_callback_func=None):
        cdef AmplifierOptions * opt
        cdef PerunAmplifierOptions * perun_opt

        opt = NULL
        if params is None:
            params = {}
        self._amp = new PerunAmplifier()
        amp_selected_ok = True

        if log_callback_func is not None:
            self._amp.set_log_callback(log_callback, < void *> log_callback_func)
            self._log_callback_func = log_callback_func
        else:
            self._log_callback_func = None


        try:
            opt = perun_opt = new PerunAmplifierOptions()

            if 'device_index' in params:
                perun_opt.device_index = int(params['device_index'])
            if 'impedance' in params:
                perun_opt.measure_impedance = int(params['impedance'])

            if 'sampling_rate' in params:
                opt.sampling_rate = int(params['sampling_rate'])
            if 'active_channels' in params:
                opt.active_channels = params['active_channels'].encode('utf-8')

            with nogil:
                self._amp.init(opt[0])
        finally:
            if opt != NULL:
                del opt
