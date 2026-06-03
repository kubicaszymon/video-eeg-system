# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""
Use to debug real-life streaming modules like: amplifier, streamer, filter.

See signal_streamer_no_filter.py for sample use.
Author:
      Mateusz Kruszynski <mateusz.kruszynski@gmail.com>
"""
import time
from logging import getLogger

LOG_INTERVAL = 10


class Debug:
    """
    Class which will print, how many samples per second were received/sent.

    Useful to find slowest links in signal analysis pipeline.
    """

    def __init__(self, p_sampling, logger):
        """
        Init debugger.

        :param p_sampling: sampling rate
        :param logger: logging.logger class to use for printing
        :param per: samples per packet
        """
        self.num_of_samples = 0
        self.sampling = p_sampling
        self.logger = logger

    def next_sample(self, last_timestamp=None):
        self.next_samples(last_timestamp, 1)

    def next_samples(self, last_timestamp=None, count=1):
        """Called after every new sample packet received. After self.sampling sample print stats info."""
        if self.num_of_samples == 0:
            self.start_time = time.time()
            self.last_pack_first_sample_ts = time.time()

        samples_per_log = self.sampling * LOG_INTERVAL
        pre_rest = self.num_of_samples % (samples_per_log)
        self.num_of_samples += count
        rest = self.num_of_samples % (samples_per_log)
        if pre_rest > rest:
            last_time = time.time() - self.last_pack_first_sample_ts
            all_time = time.time() - self.start_time
            samples_per_log = samples_per_log
            if last_timestamp is not None:
                sending_delay = " Sending delay: %f s." % (time.time() - last_timestamp)
            else:
                sending_delay = ""
            self.logger.info(("Time of last {:.0f} samples / all avg: {:.3f} s / {:.3f} s; "
                              "Average Fs: {:.2f} Hz"
                              " / {:.2f} Hz.{}").format(samples_per_log,
                                                        last_time,
                                                        samples_per_log * all_time / self.num_of_samples,
                                                        samples_per_log / last_time,
                                                        self.num_of_samples / all_time,
                                                        sending_delay)
                             )

            self.last_pack_first_sample_ts = time.time()


class SamplingRateEstimator:
    def __init__(self, name, report_every=5.0):
        self.logger = getLogger('sampling_rate_estimator.' + name)
        self.report_every = report_every
        self._first_ts = None
        self._sum = 0

    def new_samples(self, count, timestamp=None):
        if timestamp is None:
            timestamp = time.time()
        if self._first_ts is None:
            self._first_ts = timestamp
            self._sum = 0
        else:
            self._sum += count
            if timestamp - self._first_ts > self.report_every:
                self.logger.info("Estimated sampling rate: %f" % (self._sum / (timestamp - self._first_ts)))
                self._first_ts = timestamp
                self._sum = 0
