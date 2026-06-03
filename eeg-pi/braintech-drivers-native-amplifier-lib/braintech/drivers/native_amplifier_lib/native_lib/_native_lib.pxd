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


ctypedef void (*LogCallback)(const char * , void *)

cdef void log_callback(const char * msg, void * f) with gil


cdef extern from "Amplifier.h":
    cdef cppclass AmplifierOptions "AmplifierOptions":
        int sampling_rate
        string active_channels

    cdef cppclass Amplifier "Amplifier":
        Amplifier() except +

        void init(AmplifierOptions options) nogil except +

        void set_log_callback(LogCallback callback_func, void * callback_param) except +

        void start_sampling() nogil except +
        void stop_sampling() nogil except +

        bool is_sampling() nogil

        void set_active_channels_string(string channels) nogil except +

        void set_sampling_rate(unsigned int sampling_rate) nogil except +
        int get_sampling_rate() nogil

        string get_description_json() nogil except +
        string get_active_channels_string() nogil except +

        int get_active_channels_number() nogil
        int get_active_channels_with_impedance_number() nogil

        double next_samples(bool synchronize) nogil except +

        double get_sample_timestamp() nogil

        int get_samples_vec_to_buf(double * buf, double * tsbuf, double * impbuf, int buf_max_elements, int number_of_samples) nogil except +

        @staticmethod
        double local_clock()


cdef class PyAmplifier:
    cdef Amplifier * _amp
    cdef str _amp_type
    cdef object _buf
    cdef object _ts_buf
    cdef object _imp_buf
    cdef object _log_callback_func
