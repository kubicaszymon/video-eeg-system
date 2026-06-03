# cython: language_level=3, embedsignature=True
# -*- coding: utf-8 -*-
# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import json
import time
import numpy as np
cimport numpy as np

from libcpp cimport bool
from libcpp.string cimport string
from libcpp.vector cimport vector

from libc.stdint cimport int64_t


cdef void log_callback(const char * msg, void * f) with gil:
    try:
        (< object > f)(msg.decode('utf-8'))
    except:
        import traceback
        print('log_callback exception')
        traceback.print_exc()
        print('log_callback stacktrace')
        traceback.print_stack()
        print('log_callback params')
        print(< object > f, msg.decode('utf-8'))


cdef class PyAmplifier:
    def __init__(self, *args):
        self._buf = np.zeros((0, 0), dtype=np.float64)
        self._ts_buf = np.zeros((0,), dtype=np.float64)
        self._imp_buf = np.zeros((0, 0), dtype=np.float64)

    def __dealloc__(self):
        del self._amp
        if self._log_callback_func:
            self._log_callback_func('CPP Amplifier destructor done')
        self._log_callback_func = None

    def set_log_callback(self, func):
        # this function is so triavial that 'with nogil' is not needed
        self._amp.set_log_callback(log_callback, < void *> func)
        self._log_callback_func = func

    def get_description(self):
        cdef string json_str
        with nogil:
            json_str = self._amp.get_description_json()
        return json.loads(json_str.decode('utf-8'))

    def start_sampling(self):
        print("CLOCK:", int(time.time() * 1e9))
        with nogil:
            self._amp.start_sampling()

    def stop_sampling(self):
        with nogil:
            self._amp.stop_sampling()

    def is_sampling(self):
        # this function is so triavial that 'with nogil' is not needed
        return self._amp.is_sampling()

    def get_active_channels(self):
        cdef string channels_str
        with nogil:
            channels_str = self._amp.get_active_channels_string()
        return channels_str.decode('utf-8').split(';')

    def set_active_channels(self, channels):
        cdef string channels_str = ';'.join(channels).encode('utf-8')
        with nogil:
            self._amp.set_active_channels_string(channels_str)

    def get_sampling_rate(self):
        # this function is so triavial that 'with nogil' is not needed
        return self._amp.get_sampling_rate()

    def set_sampling_rate(self, sampling_rate):
        cdef unsigned int c_sampling_rate = sampling_rate
        with nogil:
            self._amp.set_sampling_rate(c_sampling_rate)

    def next_samples(self, synchronize):
        cdef bool c_synchronize = synchronize
        cdef double ret
        with nogil:
            ret = self._amp.next_samples(c_synchronize)
        return ret

    def get_sample_timestamp(self):
        # this function is so triavial that 'with nogil' is not needed
        return self._amp.get_sample_timestamp()

    def get_samples_vec(self, samples_per_vector, copy=True):
        """
        :param samples_per_vector: int how many samples to pack
        :param copy: if ``True`` new buffer is always allocated, else buffer will be reused
        :return: tuple with samples (data array shape: (samples_per_vector, ch_num),
                 timestamp array shape: (samples_per_vector,),
                 impedance array shape: (samples_per_vector, imp_ch_num)
        """
        cdef int ch_num = self._amp.get_active_channels_number()
        cdef int imp_ch_num = self._amp.get_active_channels_with_impedance_number()
        cdef int c_samples_per_vector = samples_per_vector

        # check buffer size, allocate new numpy.ndarray if
        # current buffer is not valid
        if (not self._buf.flags['C_CONTIGUOUS']
                or self._buf.dtype != np.float64
                or self._buf.shape != (samples_per_vector, ch_num)):
            self._buf = np.ascontiguousarray(np.empty((samples_per_vector, ch_num), dtype=np.float64))

        if (not self._ts_buf.flags['C_CONTIGUOUS']
                or self._ts_buf.dtype != np.float64
                or self._ts_buf.shape != (samples_per_vector,)):
            self._ts_buf = np.ascontiguousarray(np.empty((samples_per_vector,), dtype=np.float64))

        if (not self._imp_buf.flags['C_CONTIGUOUS']
                or self._imp_buf.dtype != np.float64
                or self._imp_buf.shape != (samples_per_vector, imp_ch_num)):
            self._imp_buf = np.ascontiguousarray(
                np.empty((samples_per_vector, imp_ch_num), dtype=np.float64)
            )

        cdef double * buf = < double *> np.PyArray_DATA(self._buf)
        cdef double * ts_buf = < double *> np.PyArray_DATA(self._ts_buf)
        cdef double * imp_buf = < double *> np.PyArray_DATA(self._imp_buf)

        with nogil:
            self._amp.get_samples_vec_to_buf(buf,
                                             ts_buf,
                                             imp_buf,
                                             ch_num,
                                             c_samples_per_vector)
        if copy:
            return (self._buf.copy(), self._ts_buf.copy(), self._imp_buf.copy())
        else:
            return (self._buf, self._ts_buf, self._imp_buf)

    @staticmethod
    def local_clock():
        return Amplifier.local_clock()
