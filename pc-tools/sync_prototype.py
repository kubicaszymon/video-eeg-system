"""Sample prototype: live video + EEG in one window, with a sync panel.

Purpose
-------
A first combined prototype to (a) see the Perun32 EEG stream and the
Perun32_Video stream together in one app, and (b) get a *live, indicative*
read on how well they are time-aligned.

Honest scope
------------
The **rigorous** millisecond synchronization proof is OFFLINE: record with
LabRecorder and run ``pc_examples/xdf_sync_check.py`` (see
VIDEO_EEG_APP_SPEC.md). A live app cannot prove ms accuracy — it can only
*indicate* timing health: per-stream LSL ``time_correction``, effective
rate/fps, how old the newest sample of each stream is on the common clock,
and the gap between the two streams' newest-sample timestamps. Treat the
"timeline gap" as a sanity indicator, NOT the thesis number.

Robustness
----------
Both receivers **auto-reconnect**. This matters: an on-demand impedance
check drops the ``Perun32`` stream for ~60 s by design (eeg-PROJECT_STATE
§11) — that must look like a normal reconnect, not a dead app.

Reuses the shared H.264 decode path (``h264_inlet.H264LslReceiver``) — one
decode path for live + offline, per the project rule.

Run (PC)::

    .venv-pc\\Scripts\\pip install pylsl numpy pyqtgraph PyQt5 opencv-python av
    .venv-pc\\Scripts\\python pc_app\\sync_prototype.py
    .venv-pc\\Scripts\\python pc_app\\sync_prototype.py --eeg Perun32 --video Perun32_Video --channels 8

Close the window or Ctrl-C to stop.
"""

import argparse
import base64
import collections
import csv
import json
import os
import sys
import threading
import time

import numpy as np
import cv2
import pylsl
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

from h264_inlet import H264LslReceiver
from pi_control import ControlClient, ControlPoller


# If no data for this long, drop the inlet and re-resolve (covers the ~60 s
# impedance-check outage and any WiFi blip).
_EEG_STALE_S = 8.0
_VID_STALE_S = 8.0


def _parse_args(argv):
    p = argparse.ArgumentParser(description="Live video+EEG prototype with a "
                                            "sync panel (LSL).")
    p.add_argument("--eeg", default="Perun32", help="EEG LSL stream name.")
    p.add_argument("--video", default="Perun32_Video",
                   help="Video LSL stream name.")
    p.add_argument("--channels", type=int, default=8,
                   help="How many EEG signal channels to draw (default: 8).")
    p.add_argument("--seconds", type=float, default=5.0,
                   help="Seconds of EEG history shown (default: 5).")
    p.add_argument("--spacing", type=float, default=200.0,
                   help="Vertical gap between EEG traces, µV (default: 200).")
    p.add_argument("--eeg-control-host", default="camera-pi.local",
                   help="EEG Pi control daemon host (default: "
                        "camera-pi.local). Empty string disables the panel.")
    p.add_argument("--eeg-control-port", type=int, default=8080,
                   help="EEG Pi control daemon port (default: 8080).")
    p.add_argument("--video-control-host", default="video-pi.local",
                   help="Video Pi control daemon host (default: "
                        "video-pi.local). Empty string disables the panel.")
    p.add_argument("--video-control-port", type=int, default=8081,
                   help="Video Pi control daemon port (default: 8081).")
    p.add_argument("--control-token", default=None,
                   help="Shared control-API token, if the daemons require "
                        "one (header X-Control-Token; used for both Pis).")
    return p.parse_args(argv)


class EegReceiver(threading.Thread):
    """Resolve + keep a rolling buffer of EEG signal channels, with
    auto-reconnect and live timing metrics.

    Signal vs impedance channels are split from per-channel metadata exactly
    as eeg-LSL_STREAM_SPEC.md §3 prescribes (never hardcode count/order).
    """

    def __init__(self, name, seconds):
        super().__init__(daemon=True)
        self._name = name
        self._seconds = seconds
        self._lock = threading.Lock()
        self._stop = threading.Event()
        # shared state (read by the UI thread via snapshot())
        self.connected = False
        self.srate_nominal = 500.0
        self.labels = []
        self.buf = None            # (n_samples, n_signal) ring buffer
        self._w = 0
        self._tstamps = collections.deque(maxlen=4000)  # recent sample ts
        self.last_ts = None        # newest sample LSL ts (sender clock)
        self.time_corr = None      # LSL offset -> add to map onto our clock
        self.reconnects = 0

    # --- helpers -----------------------------------------------------------
    def _resolve_inlet(self):
        while not self._stop.is_set():
            for s in pylsl.resolve_streams(wait_time=1.0):
                if s.name() == self._name:
                    return pylsl.StreamInlet(s, max_buflen=int(self._seconds) + 2)
        return None

    def _setup_channels(self, inlet):
        info = inlet.info()
        self.srate_nominal = info.nominal_srate() or 500.0
        ch = info.desc().child("channels").child("channel")
        labels, types = [], []
        for _ in range(info.channel_count()):
            labels.append(ch.child_value("label") or ch.child_value("name"))
            types.append(ch.child_value("type"))
            ch = ch.next_sibling()
        sig = [i for i, t in enumerate(types) if t == "EEG"]
        if not sig:                       # older sender w/o type metadata
            sig = list(range(info.channel_count()))
        n = max(1, int(self.srate_nominal * self._seconds))
        with self._lock:
            self._signal_idx = sig
            self.labels = [labels[i] for i in sig]
            self.buf = np.zeros((n, len(sig)), dtype=np.float32)
            self._w = 0
            self._tstamps.clear()
            self.last_ts = None
        return inlet

    # --- thread body -------------------------------------------------------
    def run(self):
        while not self._stop.is_set():
            inlet = self._resolve_inlet()
            if inlet is None:
                return
            self._setup_channels(inlet)
            with self._lock:
                self.connected = True
            last_data = time.time()
            last_tc = 0.0
            try:
                while not self._stop.is_set():
                    chunk, ts = inlet.pull_chunk(timeout=0.5, max_samples=256)
                    now = time.time()
                    if chunk:
                        block = np.asarray(chunk, dtype=np.float32)[
                            :, self._signal_idx]
                        with self._lock:
                            self._push(block)
                            self._tstamps.extend(ts)
                            self.last_ts = ts[-1]
                        last_data = now
                    elif now - last_data > _EEG_STALE_S:
                        break                      # stale -> reconnect
                    if now - last_tc > 2.0:        # refresh clock offset
                        try:
                            tc = inlet.time_correction(timeout=0.2)
                            with self._lock:
                                self.time_corr = tc
                        except Exception:
                            pass
                        last_tc = now
            except Exception:
                pass                               # LostError etc. -> below
            with self._lock:
                self.connected = False
                self.reconnects += 1

    def _push(self, block):
        b = self.buf
        k = block.shape[0]
        if k >= b.shape[0]:
            b[:] = block[-b.shape[0]:]
            self._w = 0
            return
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
                data = None
            else:
                data = np.roll(self.buf, -self._w, axis=0).copy()
            n = len(self._tstamps)
            rate = None
            if n >= 2:
                span = self._tstamps[-1] - self._tstamps[0]
                if span > 0:
                    rate = (n - 1) / span
            return {
                "data": data,
                "labels": list(self.labels),
                "connected": self.connected,
                "rate": rate,
                "srate_nominal": self.srate_nominal,
                "last_ts": self.last_ts,
                "time_corr": self.time_corr,
                "reconnects": self.reconnects,
            }

    def stop(self):
        self._stop.set()


class VideoReceiver(threading.Thread):
    """Wrap the shared H264LslReceiver; keep the newest frame + timing,
    with auto-reconnect."""

    def __init__(self, name):
        super().__init__(daemon=True)
        self._rx = H264LslReceiver(name)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.connected = False
        self._frame = None
        self.last_ts = None
        self.time_corr = None
        self.count = 0
        self._fps_t = time.time()
        self._fps_c = 0
        self.fps = 0.0
        self.reconnects = 0

    def run(self):
        while not self._stop.is_set():
            # (re)resolve
            while not self._stop.is_set():
                if self._rx.resolve(timeout=2.0) is None:
                    break
            if self._stop.is_set():
                return
            self._rx.reset()
            with self._lock:
                self.connected = True
            last_data = time.time()
            last_tc = 0.0
            while not self._stop.is_set():
                frames = self._rx.poll(block_timeout=0.5)
                now = time.time()
                if frames:
                    img, ts = frames[-1]
                    with self._lock:
                        self._frame = img
                        self.last_ts = ts
                        self.count += len(frames)
                        self._fps_c += len(frames)
                    last_data = now
                elif now - last_data > _VID_STALE_S:
                    break                          # stale -> reconnect
                if now - last_tc > 2.0:
                    tc = self._rx.time_correction(0.2)
                    with self._lock:
                        self.time_corr = tc
                    last_tc = now
                if now - self._fps_t >= 1.0:
                    with self._lock:
                        self.fps = self._fps_c / (now - self._fps_t)
                        self._fps_c = 0
                        self._fps_t = now
            with self._lock:
                self.connected = False
                self.reconnects += 1

    def snapshot(self):
        with self._lock:
            return {
                "frame": self._frame,
                "connected": self.connected,
                "last_ts": self.last_ts,
                "time_corr": self.time_corr,
                "fps": self.fps,
                "count": self.count,
                "reconnects": self.reconnects,
            }

    def stop(self):
        self._stop.set()


class Recorder:
    """Loss-less synchronized recorder.

    Records BOTH streams from its OWN inlets (independent of the display —
    LSL allows many consumers, so a laggy UI cannot corrupt the recording)
    plus periodic per-stream ``time_correction``. Synchronization is
    realised at load time by mapping each stream onto the common clock with
    those offsets — the same principle as LabRecorder/XDF, self-contained
    for the prototype. Session layout::

        session_YYYYmmdd-HHMMSS/
          meta.json          stream names, eeg channels, srate, start
          eeg_samples.f32    raw float32, rows = samples x nch
          eeg_ts.f64         raw float64, one LSL timestamp per sample
          video.h264         concatenated Annex-B access units
          video_index.csv    ts,keyframe,nbytes  (one row per AU)
          clock.csv          local_clock,stream,time_correction  (~0.5 Hz)
    """

    def __init__(self, eeg_name, video_name, root):
        self.eeg_name = eeg_name
        self.video_name = video_name
        self.root = root
        self._stop = threading.Event()
        self._threads = []
        self._lock = threading.Lock()
        self.dir = None
        self.started = None
        self.error = None
        self._eeg_n = 0
        self._vid_n = 0
        self._bytes = 0

    @property
    def active(self):
        return bool(self._threads) and not self._stop.is_set()

    def start(self):
        self.dir = os.path.join(self.root,
                                time.strftime("session_%Y%m%d-%H%M%S"))
        os.makedirs(self.dir, exist_ok=True)
        self.started = time.time()
        self.error = None
        self._eeg_n = self._vid_n = self._bytes = 0
        self._stop.clear()
        self._threads = [
            threading.Thread(target=self._eeg_loop, daemon=True),
            threading.Thread(target=self._video_loop, daemon=True),
            threading.Thread(target=self._clock_loop, daemon=True),
        ]
        for t in self._threads:
            t.start()

    def stop(self):
        self._stop.set()
        for t in self._threads:
            t.join(timeout=4.0)
        self._threads = []

    def _resolve(self, name):
        while not self._stop.is_set():
            for s in pylsl.resolve_streams(wait_time=1.0):
                if s.name() == name:
                    return pylsl.StreamInlet(s, max_buflen=60, recover=True)
        return None

    def _eeg_loop(self):
        inlet = self._resolve(self.eeg_name)
        if inlet is None:
            return
        info = inlet.info()
        nch = info.channel_count()
        ch = info.desc().child("channels").child("channel")
        labels = []
        for _ in range(nch):
            labels.append(ch.child_value("label") or ch.child_value("name"))
            ch = ch.next_sibling()
        try:
            with open(os.path.join(self.dir, "meta.json"), "w") as f:
                json.dump({
                    "eeg_name": self.eeg_name,
                    "video_name": self.video_name,
                    "eeg_nch": nch,
                    "eeg_channels": labels,
                    "eeg_srate_nominal": info.nominal_srate() or 0.0,
                    "started_unix": self.started,
                    "started_localclock": pylsl.local_clock(),
                }, f, indent=1)
        except Exception as ex:
            self.error = "meta: %s" % ex
        fs = open(os.path.join(self.dir, "eeg_samples.f32"), "wb")
        ft = open(os.path.join(self.dir, "eeg_ts.f64"), "wb")
        try:
            while not self._stop.is_set():
                chunk, ts = inlet.pull_chunk(timeout=0.5, max_samples=512)
                if not chunk:
                    continue
                a = np.asarray(chunk, dtype=np.float32)
                fs.write(a.tobytes())
                ft.write(np.asarray(ts, dtype=np.float64).tobytes())
                with self._lock:
                    self._eeg_n += a.shape[0]
        finally:
            fs.close()
            ft.close()

    def _video_loop(self):
        inlet = self._resolve(self.video_name)
        if inlet is None:
            return
        fv = open(os.path.join(self.dir, "video.h264"), "wb")
        fi = open(os.path.join(self.dir, "video_index.csv"), "w", newline="")
        w = csv.writer(fi)
        w.writerow(["ts", "keyframe", "nbytes"])
        try:
            while not self._stop.is_set():
                smp, ts = inlet.pull_sample(timeout=0.5)
                if smp is None:
                    continue
                data = base64.b64decode(smp[0])
                fv.write(data)
                w.writerow(["%.9f" % ts, 1 if smp[1] == "1" else 0,
                            len(data)])
                with self._lock:
                    self._vid_n += 1
                    self._bytes += len(data)
        finally:
            fv.close()
            fi.close()

    def _clock_loop(self):
        ei = self._resolve(self.eeg_name)
        vi = self._resolve(self.video_name)
        fc = open(os.path.join(self.dir, "clock.csv"), "w", newline="")
        w = csv.writer(fc)
        w.writerow(["local_clock", "stream", "time_correction"])
        try:
            while not self._stop.is_set():
                for nm, inl in (("eeg", ei), ("video", vi)):
                    if inl is None:
                        continue
                    try:
                        tc = inl.time_correction(timeout=0.5)
                    except Exception:
                        continue
                    w.writerow(["%.9f" % pylsl.local_clock(), nm,
                                "%.9f" % tc])
                fc.flush()
                self._stop.wait(2.0)
        finally:
            fc.close()

    def status(self):
        with self._lock:
            if not self.active:
                return "REC: idle (not recording)"
            dt = int(time.time() - self.started) if self.started else 0
            return ("REC ● %ds  eeg=%d samp  video=%d AU  %.1f MB  -> %s"
                    % (dt, self._eeg_n, self._vid_n, self._bytes / 1e6,
                       os.path.basename(self.dir)))


def _fmt_ms(x):
    return "—" if x is None else "%+.1f ms" % (x * 1000.0)


class _WorkerSignals(QtCore.QObject):
    done = QtCore.Signal(object)            # emits (tag, code, payload)


class _Worker(QtCore.QRunnable):
    """Run one blocking control call off the Qt thread; result via signal."""

    def __init__(self, tag, fn):
        super().__init__()
        self._tag = tag
        self._fn = fn
        self.signals = _WorkerSignals()

    def run(self):
        try:
            code, payload = self._fn()
        except Exception as exc:                # never let it kill the pool
            code, payload = None, {"error": str(exc)}
        self.signals.done.emit((self._tag, code, payload))


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, args, eeg, video, controller=None, client=None,
                 vcontroller=None, vclient=None):
        super().__init__()
        self.args = args
        self.eeg = eeg
        self.video = video
        self.controller = controller          # EEG ControlPoller | None
        self.client = client                  # EEG ControlClient  | None
        self.vcontroller = vcontroller        # Video ControlPoller | None
        self.vclient = vclient                # Video ControlClient | None
        self._pool = QtCore.QThreadPool.globalInstance()
        self._opts_loaded = False
        self._vopts_loaded = False
        self.setWindowTitle("Video-EEG sample prototype (live + sync panel)")

        split = QtWidgets.QSplitter()
        self.plot = pg.PlotWidget()
        self.plot.setMenuEnabled(False)
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.hideButtons()
        self.plot.setLabel("bottom", "time", "s")
        # The EEG plot was the UI-thread bottleneck (8 curves × thousands of
        # points every tick starved the video). Downsample + clip-to-view so
        # pyqtgraph draws ~screen-width points, not the whole buffer.
        self.plot.setDownsampling(auto=True, mode="peak")
        self.plot.setClipToView(True)
        self.curves = []
        self._n = 0                # tick counter (EEG redraw is throttled)
        self._last_vcount = -1     # last shown video frame index
        self.video_label = QtWidgets.QLabel("waiting for video stream…")
        self.video_label.setAlignment(QtCore.Qt.AlignCenter)
        self.video_label.setMinimumWidth(480)
        split.addWidget(self.plot)
        split.addWidget(self.video_label)
        split.setSizes([680, 540])

        self.sync = QtWidgets.QPlainTextEdit()
        self.sync.setReadOnly(True)
        self.sync.setMaximumHeight(150)
        self.sync.setStyleSheet("font-family: Consolas, monospace;")

        self.recorder = Recorder(
            args.eeg, args.video,
            os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "recordings"))
        self.rec_btn = QtWidgets.QPushButton("●  Start recording")
        self.rec_btn.setStyleSheet("font-weight: bold; padding: 6px;")
        self.rec_btn.clicked.connect(self._toggle_record)

        central = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(central)
        lay.addWidget(split, 1)
        lay.addWidget(self.rec_btn)
        lay.addWidget(self.sync)
        self.setCentralWidget(central)

        if self.controller is not None:
            self._build_control_dock()
        if self.vcontroller is not None:
            self._build_video_control_dock()

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)                       # ~30 Hz UI refresh

    def _ensure_curves(self, n):
        if len(self.curves) == n:
            return
        self.plot.clear()
        self.curves = []
        for i in range(n):
            self.curves.append(self.plot.plot(
                pen=pg.intColor(i, hues=max(n, 6)),
                autoDownsample=True, downsampleMethod="peak",
                clipToView=True))
        self.plot.setYRange(-self.args.spacing, n * self.args.spacing)

    def _tick(self):
        self._n += 1
        v = self.video.snapshot()

        # ---- video: EVERY tick, cheap, only re-blit a *new* frame ----
        if v["frame"] is not None and v["count"] != self._last_vcount:
            self._last_vcount = v["count"]
            rgb = np.ascontiguousarray(cv2.cvtColor(v["frame"],
                                                    cv2.COLOR_BGR2RGB))
            h, w, _ = rgb.shape
            qimg = QtGui.QImage(rgb.data, w, h, 3 * w,
                                QtGui.QImage.Format_RGB888)
            self.video_label.setPixmap(QtGui.QPixmap.fromImage(qimg).scaled(
                self.video_label.width(), self.video_label.height(),
                QtCore.Qt.KeepAspectRatio, QtCore.Qt.FastTransformation))

        # ---- EEG + sync panel: throttled (~every 4th tick ≈ 8 Hz) so the
        #      heavy plot can never starve the video again ----
        if self._n % 4 != 0:
            return
        e = self.eeg.snapshot()

        if e["data"] is not None and e["data"].size:
            data = e["data"]
            n = min(self.args.channels, data.shape[1])
            self._ensure_curves(n)
            t = np.arange(data.shape[0]) / max(e["srate_nominal"], 1.0)
            for i in range(n):
                y = data[:, i] - np.mean(data[:, i])
                self.curves[i].setData(t, y + i * self.args.spacing)

        # ---- sync / status panel (indicative only) ----
        now = pylsl.local_clock()

        def common(last_ts, tc):
            if last_ts is None or tc is None:
                return None
            return last_ts + tc                    # newest sample on our clock

        e_c = common(e["last_ts"], e["time_corr"])
        v_c = common(v["last_ts"], v["time_corr"])
        e_age = None if e_c is None else now - e_c
        v_age = None if v_c is None else now - v_c
        gap = None if (e_c is None or v_c is None) else (v_c - e_c)

        e_state = "OK" if e["connected"] else "reconnecting (impedance check?)"
        v_state = "OK" if v["connected"] else "reconnecting…"
        e_rate = "—" if e["rate"] is None else "%.2f Hz" % e["rate"]

        lines = [
            "EEG  '%s': %-32s reconnects=%d" % (
                self.args.eeg, e_state, e["reconnects"]),
            "     rate≈%s (nominal %.0f)   time_correction=%s   "
            "newest-sample age=%s" % (
                e_rate, e["srate_nominal"], _fmt_ms(e["time_corr"]),
                _fmt_ms(e_age)),
            "VIDEO '%s': %-31s reconnects=%d" % (
                self.args.video, v_state, v["reconnects"]),
            "     fps≈%.1f   time_correction=%s   newest-frame age=%s   "
            "frames=%d" % (
                v["fps"], _fmt_ms(v["time_corr"]), _fmt_ms(v_age),
                v["count"]),
            "NEWEST-SAMPLE TIMELINE GAP (video − EEG, common clock): %s" %
            _fmt_ms(gap),
            self.recorder.status() + (
                "   ERR:%s" % self.recorder.error
                if self.recorder.error else ""),
        ]
        self.sync.setPlainText("\n".join(lines))

        if self.controller is not None:
            try:
                self._refresh_control_panel()
            except Exception:
                pass                           # UI must never die on this
        if self.vcontroller is not None:
            try:
                self._refresh_video_control_panel()
            except Exception:
                pass

    # ---- EEG Pi remote control (dock) ------------------------------------

    def _build_control_dock(self):
        dock = QtWidgets.QDockWidget("EEG Pi control", self)
        dock.setAllowedAreas(QtCore.Qt.RightDockWidgetArea |
                             QtCore.Qt.LeftDockWidgetArea)
        box = QtWidgets.QGroupBox("Perun32 EEG  (%s:%d)" % (
            self.args.eeg_control_host, self.args.eeg_control_port))
        form = QtWidgets.QFormLayout(box)

        self.c_mode = QtWidgets.QComboBox()
        self.c_mode.addItems(["eeg", "impedance", "stopped"])
        self.c_rate = QtWidgets.QComboBox()
        self.c_rate.addItems(["500", "1000", "2000", "4000", "8000", "16000"])
        self.c_chan = QtWidgets.QLineEdit()
        self.c_chan.setPlaceholderText("blank = all; e.g. ExG_1, ExG_2")
        self.c_apply = QtWidgets.QPushButton("Apply")
        self.c_apply.clicked.connect(self._apply_control)

        self.c_imp_dur = QtWidgets.QSpinBox()
        self.c_imp_dur.setRange(5, 600)
        self.c_imp_dur.setValue(45)
        self.c_imp_dur.setSuffix(" s")
        self.c_imp_btn = QtWidgets.QPushButton("Impedance check")
        self.c_imp_btn.clicked.connect(self._do_impedance)

        self.c_status = QtWidgets.QLabel("control: connecting…")
        self.c_status.setWordWrap(True)
        self.c_status.setStyleSheet("font-family: Consolas, monospace;")
        self.c_result = QtWidgets.QLabel("")
        self.c_result.setWordWrap(True)

        form.addRow("Mode", self.c_mode)
        form.addRow("Rate (Hz)", self.c_rate)
        form.addRow("Channels", self.c_chan)
        form.addRow(self.c_apply)
        imp = QtWidgets.QHBoxLayout()
        imp.addWidget(self.c_imp_dur)
        imp.addWidget(self.c_imp_btn)
        form.addRow("Impedance", imp)
        form.addRow(self.c_status)
        form.addRow(self.c_result)

        dock.setWidget(box)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)

    def _run_off_thread(self, tag, fn):
        w = _Worker(tag, fn)
        w.signals.done.connect(self._on_control_result)
        self._pool.start(w)

    def _apply_control(self):
        patch = {"mode": self.c_mode.currentText(),
                 "rate": int(self.c_rate.currentText())}
        txt = self.c_chan.text().strip()
        if txt:
            patch["channels"] = [c.strip() for c in txt.replace(";", ",")
                                 .split(",") if c.strip()]
        else:
            patch["channels"] = None
        self.c_apply.setEnabled(False)
        self.c_result.setText("applying…")
        client = self.client
        self._run_off_thread("control", lambda: client.control(patch))

    def _do_impedance(self):
        dur = self.c_imp_dur.value()
        self.c_imp_btn.setEnabled(False)
        self.c_result.setText("impedance starting…")
        client = self.client
        self._run_off_thread("impedance", lambda: client.impedance(dur))

    def _on_control_result(self, res):
        tag, code, payload = res
        if code is None:
            msg = "%s: unreachable (%s)" % (tag, payload.get("error", "?"))
        elif code in (200, 202):
            msg = "%s: OK" % tag
        else:
            msg = "%s: error %s — %s" % (tag, code,
                                          payload.get("error", payload))
        if tag == "video-control":
            self.v_result.setText(msg)
            self.v_apply.setEnabled(True)
        else:
            # "control" or "impedance"
            self.c_result.setText(msg)
            self.c_apply.setEnabled(True)
            self.c_imp_btn.setEnabled(True)

    def _refresh_control_panel(self):
        snap = self.controller.snapshot()
        # Populate combos from /options once (keeps client generic).
        opts = snap.get("options")
        if opts and not self._opts_loaded:
            rates = [str(r) for r in opts.get("rates", [])]
            if rates:
                cur = self.c_rate.currentText()
                self.c_rate.clear()
                self.c_rate.addItems(rates)
                if cur in rates:
                    self.c_rate.setCurrentText(cur)
            modes = opts.get("modes")
            if modes:
                self.c_mode.clear()
                self.c_mode.addItems(modes)
            self._opts_loaded = True
        if not snap["reachable"]:
            self.c_status.setText("control: Pi unreachable "
                                  "(%s)" % self.args.eeg_control_host)
            return
        if not snap["daemon_up"]:
            self.c_status.setText("control: Pi up, daemon DOWN "
                                  "(break-glass?)")
            return
        st = snap.get("status") or {}
        ds = st.get("state", {})
        busy = st.get("transition_in_progress")
        self.c_apply.setEnabled(not busy)
        chans = snap.get("channels")
        if chans:
            self.c_chan.setToolTip("available: " + ", ".join(chans))
        self.c_status.setText(
            "control: mode=%s rate=%s ch=%s  child=%s amp=%s%s%s" % (
                ds.get("mode"), ds.get("rate"),
                ("all" if ds.get("channels") in (None, [])
                 else len(ds.get("channels"))),
                "UP" if st.get("child_alive") else "down",
                st.get("amp_detected"),
                "  [APPLYING]" if busy else "",
                ("  ERR:%s" % st.get("last_error"))
                if st.get("last_error") else ""))

    # ---- Video Pi remote control (dock) ----------------------------------

    def _build_video_control_dock(self):
        dock = QtWidgets.QDockWidget("Video Pi control", self)
        dock.setAllowedAreas(QtCore.Qt.RightDockWidgetArea |
                             QtCore.Qt.LeftDockWidgetArea)
        box = QtWidgets.QGroupBox("Pi Camera  (%s:%d)" % (
            self.args.video_control_host, self.args.video_control_port))
        form = QtWidgets.QFormLayout(box)

        self.v_mode = QtWidgets.QComboBox()
        self.v_mode.addItems(["video", "stopped"])
        self.v_w = QtWidgets.QSpinBox()
        self.v_w.setRange(160, 1920)
        self.v_w.setValue(960)
        self.v_h = QtWidgets.QSpinBox()
        self.v_h.setRange(120, 1080)
        self.v_h.setValue(720)
        self.v_fps = QtWidgets.QSpinBox()
        self.v_fps.setRange(1, 60)
        self.v_fps.setValue(30)
        self.v_br = QtWidgets.QSpinBox()
        self.v_br.setRange(100, 20000)
        self.v_br.setValue(4000)
        self.v_br.setSuffix(" kbps")
        self.v_hflip = QtWidgets.QCheckBox("hflip")
        self.v_vflip = QtWidgets.QCheckBox("vflip")
        self.v_apply = QtWidgets.QPushButton("Apply")
        self.v_apply.clicked.connect(self._apply_video_control)

        self.v_status = QtWidgets.QLabel("control: connecting…")
        self.v_status.setWordWrap(True)
        self.v_status.setStyleSheet("font-family: Consolas, monospace;")
        self.v_result = QtWidgets.QLabel("")
        self.v_result.setWordWrap(True)

        wh = QtWidgets.QHBoxLayout()
        wh.addWidget(self.v_w)
        wh.addWidget(QtWidgets.QLabel("×"))
        wh.addWidget(self.v_h)
        fl = QtWidgets.QHBoxLayout()
        fl.addWidget(self.v_hflip)
        fl.addWidget(self.v_vflip)
        form.addRow("Mode", self.v_mode)
        form.addRow("Size", wh)
        form.addRow("FPS", self.v_fps)
        form.addRow("Bitrate", self.v_br)
        form.addRow("Flip", fl)
        form.addRow(self.v_apply)
        form.addRow(self.v_status)
        form.addRow(self.v_result)

        dock.setWidget(box)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)

    def _apply_video_control(self):
        patch = {"mode": self.v_mode.currentText(),
                 "width": self.v_w.value(), "height": self.v_h.value(),
                 "fps": self.v_fps.value(),
                 "bitrate": self.v_br.value() * 1000,
                 "hflip": self.v_hflip.isChecked(),
                 "vflip": self.v_vflip.isChecked()}
        self.v_apply.setEnabled(False)
        self.v_result.setText("applying…")
        vclient = self.vclient
        self._run_off_thread("video-control", lambda: vclient.control(patch))

    def _refresh_video_control_panel(self):
        snap = self.vcontroller.snapshot()
        opts = snap.get("options")
        if opts and not self._vopts_loaded:
            rng = opts.get("ranges", {})
            for key, sb in (("width", self.v_w), ("height", self.v_h),
                            ("fps", self.v_fps)):
                if key in rng:
                    sb.setRange(int(rng[key][0]), int(rng[key][1]))
            if "bitrate" in rng:
                self.v_br.setRange(int(rng["bitrate"][0] / 1000),
                                   int(rng["bitrate"][1] / 1000))
            modes = opts.get("modes")
            if modes:
                self.v_mode.clear()
                self.v_mode.addItems(modes)
            self._vopts_loaded = True
        if not snap["reachable"]:
            self.v_status.setText("control: Pi unreachable (%s)"
                                  % self.args.video_control_host)
            return
        if not snap["daemon_up"]:
            self.v_status.setText("control: Pi up, daemon DOWN "
                                  "(break-glass?)")
            return
        st = snap.get("status") or {}
        ds = st.get("state", {})
        busy = st.get("transition_in_progress")
        self.v_apply.setEnabled(not busy)
        self.v_status.setText(
            "control: mode=%s %sx%s@%s %skbps  child=%s%s%s" % (
                ds.get("mode"), ds.get("width"), ds.get("height"),
                ds.get("fps"),
                int(ds.get("bitrate", 0) / 1000) if ds.get("bitrate") else "?",
                "UP" if st.get("child_alive") else "down",
                "  [APPLYING]" if busy else "",
                ("  ERR:%s" % st.get("last_error"))
                if st.get("last_error") else ""))

    def _toggle_record(self):
        if self.recorder.active:
            self.recorder.stop()
            self.rec_btn.setText("●  Start recording")
        else:
            self.recorder.start()
            self.rec_btn.setText("■  Stop recording")

    def closeEvent(self, ev):
        if self.recorder.active:
            self.recorder.stop()
        self.eeg.stop()
        self.video.stop()
        if self.controller is not None:
            self.controller.stop()
        if self.vcontroller is not None:
            self.vcontroller.stop()
        ev.accept()


def main(argv=None):
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    eeg = EegReceiver(args.eeg, args.seconds)
    video = VideoReceiver(args.video)
    eeg.start()
    video.start()

    controller = client = None
    if args.eeg_control_host:
        client = ControlClient(args.eeg_control_host, args.eeg_control_port,
                               token=args.control_token)
        controller = ControlPoller(client)
        controller.start()

    vcontroller = vclient = None
    if args.video_control_host:
        vclient = ControlClient(args.video_control_host,
                                args.video_control_port,
                                token=args.control_token)
        vcontroller = ControlPoller(vclient)
        vcontroller.start()

    app = QtWidgets.QApplication(sys.argv[:1])
    win = MainWindow(args, eeg, video, controller, client,
                     vcontroller, vclient)
    win.resize(1340, 760)
    win.show()
    app.exec_()


if __name__ == "__main__":
    main()
