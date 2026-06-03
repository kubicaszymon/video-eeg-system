# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""This module provides a simple class that is able to receive messages and produce some statistical information."""
import time
from typing import Iterable


class MsgPerfStats:
    """Receives messages with method and periodically prints some statistical information."""

    def __init__(self, interval: float, name: str = '') -> None:
        """
        Function prints statistical information about received message.

        :param interval: how often statistics will be printed
        :param name: name of this counter
        """
        super().__init__()
        self._name = name   # type: str
        self._interval = interval  # type: float
        self._calc_size = False  # type: bool
        self.reset()

    def reset(self) -> None:
        """Reset statistics."""
        self._last_time = time.time()  # type: float
        self._start_time = self._last_time  # type: float
        self._count = 0  # type: int
        self._total_size = 0  # type: int

    def msg(self, msg: Iterable[bytes]) -> None:
        """
        Called to count new message into statistics.

        :param msg: serialized message to count in
        """
        self._last_time = time.time()
        self._count += 1
        if self._calc_size:
            self._total_size += sum(map(len, msg))
        measurement_time = self._last_time - self._start_time

        if measurement_time > self._interval:
            if self._calc_size:
                mean_size = int(self._total_size / self._count)
                megabytes_per_second = (self._total_size / measurement_time) / 1e6
            messages_per_second = self._count / measurement_time

            if self._name:
                print('stats for "{}"'.format(self._name))
            print('message count:     {:6d} [msgs]'.format(self._count))
            if self._calc_size:
                print('mean message size: {:6d} [B]'.format(mean_size))
            print('mean throughput:   {:4.2f} [msg/s]'.format(messages_per_second))
            if self._calc_size:
                print('mean throughput:   {:2.4f} [MB/s]'.format(megabytes_per_second))
            print('measurement time:  {:2.4f} [s]'.format(measurement_time))
            print('')

            self.reset()

    @property
    def interval(self) -> float:
        """How often message statistics will be printed to stdout.

        float:Specified in seconds.

        .. note::
            Interval is checked only when calling :meth:`msg` method, this
            class doesn't use its own timer.
        """
        return self._interval

    @interval.setter
    def interval(self, interval: float) -> None:
        self._interval = interval
        self.reset()
