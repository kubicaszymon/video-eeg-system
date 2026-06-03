"""Live video-EEG viewer (PC side).

Shows, in one window:

  * left  - scrolling EEG traces from the Perun32 LSL stream (Pi Zero 2W),
  * right - the live camera image from the Perun32_Video LSL stream
            (Pi 3B+).

Both come off the network via LSL. This is the *live monitoring* tool
(requirement #1). It does **not** do the precise post-hoc alignment — that
is LabRecorder + ``pc_examples/xdf_sync_check.py`` (requirement #2). You can
(and should) run LabRecorder at the same time as this app: an LSL stream
supports many independent consumers.

Run (on the PC)::

    python -m venv .venv-pc
    .venv-pc\\Scripts\\pip install pylsl numpy pyqtgraph PyQt5 opencv-python
    .venv-pc\\Scripts\\python pc_app\\live_view.py
    .venv-pc\\Scripts\\python pc_app\\live_view.py --eeg Perun32 --video Perun32_Video --channels 8 --seconds 5

Close the window or Ctrl-C to stop.
"""

import argparse
import sys
import threading
import time

import numpy as np
import cv2
import pylsl
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

from h264_inlet import H264LslReceiver


def _parse_args(argv):
    p = argparse.ArgumentParser(description="Live video-EEG viewer (LSL).")
    p.add_argument("--eeg", default="Perun32", help="EEG LSL stream name.")
    p.add_argument("--video", default="Perun32_Video", help="Video LSL stream name.")
    p.add_argument("--channels", type=int, default=8,
                   help="How many EEG signal channels to draw (default: 8).")
    p.add_argument("--seconds", type=float, default=5.0,
                   help="Seconds of EEG history shown (default: 5).")
    p.add_argument("--spacing", type=float, default=200.0,
                   help="Vertical gap between EEG traces, in microvolts "
                        "(default: 200).")
    return p.parse_args(argv)


class EegReceiver(threading.Thread):
    """Resolve the EEG stream and keep a rolling buffer of signal channels.

    Signal vs impedance channels are split from per-channel metadata, exactly
    as LSL_STREAM_SPEC.md prescribes (don't hardcode the count/order).
    """

    def __init__(self, name):
        super().__init__(daemon=True)
        self._name = name
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.ready = threading.Event()
        self.srate = 500.0
        self.signal_idx = []
        self.labels = []
        self.buf = None  # (n_samples, n_signal) ring buffer
        self._w = 0

    def _resolve(self):
        while not self._stop.is_set():
            for s in pylsl.resolve_streams(wait_time=1.0):
                if s.name() == self._name:
                    return pylsl.StreamInlet(s, max_buflen=int(self.seconds_hint) + 1)
        return None

    def configure(self, seconds):
        self.seconds_hint = seconds

    def run(self):
        inlet = self._resolve()
        if inlet is None:
            return
        info = inlet.info()
        self.srate = info.nominal_srate() or 500.0
        ch = info.desc().child("channels").child("channel")
        labels, types = [], []
        for _ in range(info.channel_count()):
            labels.append(ch.child_value("label") or ch.child_value("name"))
            types.append(ch.child_value("type"))
            ch = ch.next_sibling()
        # If 'type' metadata is absent (older sender) treat everything as signal.
        sig = [i for i, t in enumerate(types) if t == "EEG"]
        if not sig:
            sig = list(range(info.channel_count()))
        n = int(self.srate * self.seconds_hint)
        with self._lock:
            self.signal_idx = sig
            self.labels = [labels[i] for i in sig]
            self.buf = np.zeros((n, len(sig)), dtype=np.float32)
            self._w = 0
        self.ready.set()

        while not self._stop.is_set():
            chunk, _ = inlet.pull_chunk(timeout=0.5, max_samples=256)
            if not chunk:
                continue
            block = np.asarray(chunk, dtype=np.float32)[:, self.signal_idx]
            with self._lock:
                k = block.shape[0]
                b = self.buf
                if k >= b.shape[0]:
                    b[:] = block[-b.shape[0]:]
                    self._w = 0
                else:
                    end = self._w + k
                    if end <= b.shape[0]:
                        b[self._w:end] = block
                    else:
                        first = b.shape[0] - self._w
                        b[self._w:] = block[:first]
                        b[:k - first] = block[first:]
                    self._w = end % b.shape[0]

    def snapshot(self):
        with self._lock:
            if self.buf is None:
                return None, None
            # unroll the ring so the newest sample is last
            ordered = np.roll(self.buf, -self._w, axis=0).copy()
            return ordered, list(self.labels)

    def stop(self):
        self._stop.set()


class VideoReceiver(threading.Thread):
    """Background H.264-over-LSL receiver; keeps the newest decoded frame.

    Decoding/resync lives in the shared H264LslReceiver so the live app and
    the offline sync check use one decode path.
    """

    def __init__(self, name):
        super().__init__(daemon=True)
        self._rx = H264LslReceiver(name)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._frame = None
        self._ts = None
        self._count = 0

    def run(self):
        while not self._stop.is_set():           # retry until resolved
            if self._rx.resolve(timeout=2.0) is None:
                break
        while not self._stop.is_set():
            frames = self._rx.poll(block_timeout=0.5)
            if not frames:
                continue
            img, ts = frames[-1]                  # newest decoded frame
            with self._lock:
                self._frame = img
                self._ts = ts
                self._count += len(frames)

    def snapshot(self):
        with self._lock:
            return self._frame, self._ts, self._count

    def stop(self):
        self._stop.set()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, args, eeg, video):
        super().__init__()
        self.args = args
        self.eeg = eeg
        self.video = video
        self.setWindowTitle("Live Video-EEG")

        split = QtWidgets.QSplitter()
        self.plot = pg.PlotWidget()
        self.plot.setMenuEnabled(False)
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.hideButtons()
        self.plot.setLabel("bottom", "time", "s")
        self.curves = []
        self.video_label = QtWidgets.QLabel("waiting for video stream...")
        self.video_label.setAlignment(QtCore.Qt.AlignCenter)
        self.video_label.setMinimumWidth(480)
        split.addWidget(self.plot)
        split.addWidget(self.video_label)
        split.setSizes([700, 520])
        self.setCentralWidget(split)
        self.status = self.statusBar()

        self._t0 = time.time()
        self._last_count = 0
        self._last_fps_t = time.time()
        self._fps = 0.0

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)  # ~30 Hz UI refresh

    def _ensure_curves(self, n):
        if len(self.curves) == n:
            return
        self.plot.clear()
        self.curves = []
        pens = [pg.intColor(i, hues=max(n, 6)) for i in range(n)]
        for i in range(n):
            self.curves.append(self.plot.plot(pen=pens[i]))
        self.plot.setYRange(-self.args.spacing, n * self.args.spacing)

    def _tick(self):
        # ---- EEG ----
        data, labels = self.eeg.snapshot()
        if data is not None and data.size:
            n = min(self.args.channels, data.shape[1])
            self._ensure_curves(n)
            t = np.arange(data.shape[0]) / max(self.eeg.srate, 1.0)
            for i in range(n):
                y = data[:, i] - np.mean(data[:, i])
                self.curves[i].setData(t, y + i * self.args.spacing)

        # ---- Video ----
        frame, vts, count = self.video.snapshot()
        if frame is not None:
            rgb = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            h, w, _ = rgb.shape
            qimg = QtGui.QImage(rgb.data, w, h, 3 * w, QtGui.QImage.Format_RGB888)
            pix = QtGui.QPixmap.fromImage(qimg).scaled(
                self.video_label.width(), self.video_label.height(),
                QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            self.video_label.setPixmap(pix)

            now = time.time()
            if now - self._last_fps_t >= 1.0:
                self._fps = (count - self._last_count) / (now - self._last_fps_t)
                self._last_count = count
                self._last_fps_t = now

        # ---- status ----
        eeg_state = "EEG: ok" if self.eeg.ready.is_set() else "EEG: waiting..."
        vid_state = ("video: %.1f fps" % self._fps) if frame is not None else "video: waiting..."
        self.status.showMessage("%s   |   %s" % (eeg_state, vid_state))

    def closeEvent(self, ev):
        self.eeg.stop()
        self.video.stop()
        ev.accept()


def main(argv=None):
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    eeg = EegReceiver(args.eeg)
    eeg.configure(args.seconds)
    video = VideoReceiver(args.video)
    eeg.start()
    video.start()

    app = QtWidgets.QApplication(sys.argv[:1])
    win = MainWindow(args, eeg, video)
    win.resize(1240, 560)
    win.show()
    app.exec_()


if __name__ == "__main__":
    main()
