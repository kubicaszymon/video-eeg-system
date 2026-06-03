import asyncio
import os
import uuid
from collections import deque
from logging import getLogger

import numpy as np

from braintech.drivers.blinker.blinker import get_blinker
from braintech.obci.core.broker.messages import TagMsg
from braintech.obci.signal_processing.buffers import AutoBlinkBuffer, Blink
from braintech.obci.signal_processing.signal.containers import SamplePacket
try:
    from braintech.drivers.perun8.perun_timestamp_correcter import DebugModeVisualisationException
except ImportError:
    class DebugModeVisualisationException(Exception):
        pass


class AmplifierLatencyVariabilityChecker:
    def __init__(self, sampling_rate=500, title='', comm_peer=None):
        """Assumes diode is connected to 1st active electrode."""
        self._comm_peer = comm_peer
        self._logger = getLogger(self.__class__.__name__)
        self._title = title
        self.sampling_rate = sampling_rate
        self.buffer = AutoBlinkBuffer(from_blink=int(self.sampling_rate * (-1)),
                                      samples_count=int(2 * self.sampling_rate),
                                      sampling=self.sampling_rate,
                                      num_of_channels=2,  # one channel fails
                                      ret_func=self._buffer_ret_func,
                                      copy_on_ret=True,
                                      )
        try:
            from bci_panel.bci_panels import BCIPanelProcess
        except ImportError:
            raise DebugModeVisualisationException("Debug mode requires obci-ugm for visualisation, please install.")
        self._bci_panel = BCIPanelProcess()

        self._blink_latencies = []

        self._blink_latencies_raw = []
        self._blink_latencies_raw_baseline_buffer = deque(maxlen=int(self.sampling_rate * 3))

        self._blink_timestamps = []
        self._blinks = []

        self._latencies_file = open(os.path.expanduser('~/test_amplifier_latency_{}.csv'.format(title)), 'w')
        self._latencies_raw_file = open(os.path.expanduser('~/test_amplifier_latency_raw_{}.csv'.format(title)), 'w')
        self._blinks_file = open(os.path.expanduser('~/test_amplifier_latency_blinks_{}.csv'.format(title)), 'w')

    def _buffer_ret_func(self, blink, samples):
        photodiode = samples[0]
        # matching raw latency - due to buffers moving the tag by 1 sample
        timeline = np.linspace(-1 + 1 / self.sampling_rate, 1, len(photodiode)) + 1 / self.sampling_rate

        baseline = photodiode[0:int(0.4 * self.sampling_rate)]
        baseline_mean = np.mean(baseline)
        baseline_std = np.std(baseline)
        threshold = (baseline_mean + baseline_std * 20)
        threshold_mask = photodiode >= threshold

        try:
            latency = timeline[threshold_mask][0]  # first sample crossing threshold
        except IndexError:
            self._logger.warning("CAN'T FIND BLINK LATENCY")

            self._bci_panel.update_plot(feature='last_blink_buffered',
                                        x_data=[timeline, timeline],
                                        y_data=[photodiode, np.zeros_like(timeline) + baseline_mean],
                                        title=self._title
                                        )
        else:

            latency_vis = (timeline >= latency) * np.max(photodiode - baseline_mean) + baseline_mean

            self._bci_panel.update_plot(feature='last_blink_buffered',
                                        x_data=[timeline, timeline],
                                        y_data=[photodiode, latency_vis],
                                        title=self._title
                                        )

            self._blink_latencies.append(latency)
            self._blink_timestamps.append(blink.timestamp)
            self._blinks.append(samples)

            self._latencies_file.write('{}, {}\n'.format(latency, blink.timestamp))
            self._latencies_file.flush()

            for ts, value in zip(timeline, photodiode):
                self._blinks_file.write('{}, {}\n'.format(ts, value))
            self._blinks_file.flush()

            info = {'Last blink latency': str(latency),
                    'First blink_latency': str(self._blink_latencies[0])}
            self._bci_panel.update_text(field_id='0', feature='0', data=info, title=self._title)

            self._draw_latencies()

    def _draw_latencies(self):
        raw = np.array(self._blink_latencies_raw)
        raw_timeline = raw[:, 1]
        raw_latencies = raw[:, 0]

        buffered_latencies = np.array(self._blink_latencies)
        buffered_timeline = np.array(self._blink_timestamps)

        self._bci_panel.update_plot(feature='latencies',
                                    x_data=[buffered_timeline, raw_timeline],
                                    y_data=[buffered_latencies, raw_latencies],
                                    title=self._title,
                                    labels=['latencies buffered', 'latencies raw'],
                                    )

    def get_packet(self, packet: SamplePacket):
        packet_for_buffer = SamplePacket(packet.samples[:, 0:2], packet.ts)

        for value, ts in zip(packet.samples[:, 0], packet.ts):
            self._blink_latencies_raw_baseline_buffer.append([value, ts])

        self.buffer.handle_sample_packet(packet_for_buffer)

    async def measure_delays(self, slave_checkers=[]):
        self._setup_blinker()
        while True:
            ts = await self._stimulate(slave_checkers)
            self._visualise_raw_latency(ts)

    def _setup_blinker(self):
        self._blinker = get_blinker("/dev/fat_blinker")
        for i in range(self._blinker.CHANNELS_NUMBER):
            self._blinker.enable(i)
            self._blinker.set_still(i, 0)
        self._blinker.flush()
        self._blinker.start()

    async def _stimulate(self, slave_checkers):
        for i in range(self._blinker.CHANNELS_NUMBER):
            self._blinker.set_still(i, 0)
        self._blinker.flush()
        await asyncio.sleep(1)

        for i in range(self._blinker.CHANNELS_NUMBER):
            self._blinker.set_still(i, 1)
        ts = self._blinker.flush()
        self._blink_latencies_raw_blink_ts = ts
        self._blink_latencies_raw_new_cycle = True

        blink = Blink(ts, 0)
        if self._comm_peer:
            self._comm_peer.send_message(TagMsg(id=str(uuid.uuid4()),
                                                start_timestamp=ts,
                                                name='blink',
                                                channels='-1',
                                                desc={},
                                                end_timestamp=ts + 1))

        self.buffer.handle_blink(blink)
        for checker in slave_checkers:
            checker.buffer.handle_blink(blink)
        await asyncio.sleep(1)

        for i in range(self._blinker.CHANNELS_NUMBER):
            self._blinker.set_still(i, 0)
        self._blinker.flush()
        await asyncio.sleep(1)
        return ts

    def _visualise_raw_latency(self, ts):
        data = np.copy(self._blink_latencies_raw_baseline_buffer)
        photodiode = np.array(data)[:, 0]
        timeline = np.array(data)[:, 1]
        baseline = photodiode[0:int(0.4 * self.sampling_rate)]
        baseline_mean = np.mean(baseline)
        baseline_std = np.std(baseline)
        threshold = (baseline_mean + baseline_std * 20)

        mask = photodiode >= threshold

        try:
            time_of_first_photon = timeline[mask][0]
        except IndexError:
            self._logger.warning("CAN'T FIND BLINK LATENCY")
            self._bci_panel.update_plot(feature='last_blink_raw',
                                        x_data=[timeline, timeline],
                                        y_data=[photodiode, np.zeros_like(timeline) + baseline_mean],
                                        title=self._title
                                        )
        else:
            latency = time_of_first_photon - ts
            self._blink_latencies_raw.append([latency, ts])
            self._latencies_raw_file.write('{}, {}\n'.format(latency, ts))
            self._latencies_raw_file.flush()

            latency_vis = (photodiode >= threshold) * np.max(photodiode - baseline_mean) + baseline_mean

            self._bci_panel.update_plot(feature='last_blink_raw',
                                        x_data=[timeline, timeline],
                                        y_data=[photodiode, latency_vis],
                                        title=self._title
                                        )

            info = {'Last blink raw latency': str(latency),
                    'First blink raw latency': str(self._blink_latencies_raw[0][0])}
            self._bci_panel.update_text(field_id='0', feature='raw_latencies', data=info, title=self._title)
