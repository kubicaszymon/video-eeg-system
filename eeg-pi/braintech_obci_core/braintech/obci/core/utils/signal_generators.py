# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Provides various generators generating multichannel signal as SamplePacket objects."""

import time
import random
import asyncio
from typing import Iterator

import numpy as np

from braintech.obci.core.drivers.eeg.eeg_amplifier import SamplePacket

MAX_VAL = 10  # type: int
"""int: maximal value of saw signal"""


def saw_generator(max_val: int = MAX_VAL) -> Iterator[int]:
    """
    Saw signal generator.

    Returned values will be from 0 to max value (inclusive) and then back to 0.

    :param max_val: maximal value, after which generator drops to 0 and restarts
    """
    counter = 0
    while True:
        yield counter
        counter += 1
        if counter > max_val:
            counter = 0


class SawVerifier:
    """Raises exception if saw signal is not valid."""

    def __init__(self, max_val: int = MAX_VAL) -> None:
        """
        Create a new saw signal verifier with specified maximum value.

        :param max_val: maximum value, after which generator drops to 0 and restarts
        """
        super().__init__()
        self._saw_gen = saw_generator(max_val)

    def verify_next(self, value) -> None:
        """
        Get the next value from this generator and assert that it will be equal to the given value.

        :param value: value to compare
        """
        assert next(self._saw_gen) == value


class AsyncSignalGenerator:
    """
    An implementation of async generator for test signal.

    The following channels are generated:
    #. samples counter
    #. :func:`time.time` value
    #. :func:`time.monotonic` value
    #. always 0.0
    #. always 1.0
    #. always -1.0
    #. alternating sequence of 0 and 1
    #. 100 Hz sinus
    #. :func:`random.random` generated floats
    #. saw signal
    """

    def __init__(self) -> None:
        """Create a new async signal generator."""
        super().__init__()
        self._last_time = None

        self._sampling_rate = 16.0
        self._samples_per_iteration = 4

        self._samples_delay = 1.0 / (self._sampling_rate / self._samples_per_iteration)

        self._stop = False

        self._samples_counter = 0
        self._last_flip = 0
        self._saw_gen = saw_generator()

    def __aiter__(self) -> 'AsyncSignalGenerator':
        """Return itself as an iterator for "async for" construct."""
        return self

    async def __anext__(self) -> SamplePacket:
        """
        Return next sample packet from this generator.

        :return: :class:`SamplePacket` instance
        """
        if self._last_time is None:
            self._last_time = time.monotonic()
        sleep_duration = self._samples_delay - (time.monotonic() - self._last_time)
        # When we are late with the next sample sleep_duration is < 0. Despite being late call
        # asyncio.sleep(0) as it allows other, pending coroutines to be scheduled.
        if sleep_duration < 0:
            sleep_duration = 0
        await asyncio.sleep(sleep_duration)  # required
        if self._stop:
            raise StopAsyncIteration
        self._last_time = time.monotonic()
        ts = np.zeros(self._samples_per_iteration)
        samples = None
        for i in range(self._samples_per_iteration):
            timestamp, values = self._get_next_sample()
            if samples is None:
                samples = np.zeros((self._samples_per_iteration, len(values)))
            ts[i] = timestamp
            samples[i] = values
        return SamplePacket(ts=ts, samples=samples)

    def _get_next_sample(self) -> tuple:
        sample = time.time(), np.array([
            self._samples_counter,
            time.time(),
            time.monotonic(),
            0.0,
            1.0,
            -1.0,
            self._last_flip,
            np.sin(2.0 * np.pi * 100.0 * self._samples_counter / self._sampling_rate),  # 100 Hz sin
            random.random(),
            next(self._saw_gen)
        ], dtype=float)
        self._samples_counter += 1
        self._last_flip = 0 if self._last_flip == 1 else 1
        return sample
