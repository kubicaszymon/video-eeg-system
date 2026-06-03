"""Stream the Raspberry Pi camera to LSL as hardware-encoded H.264.

Why this exists / why H.264
---------------------------
The video-EEG system needs the video on the **same LSL clock** as the EEG so
LabRecorder records both into one XDF that is frame-accurately aligned, and
so the PC can show them live together.

The first version sent a full JPEG per frame (MJPEG). On a Pi 3B+ that is
~27 Mbps at 960×720 — more than its WiFi can sustain, so frames were dropped
(~5 fps). This version uses the Pi 3B+ **hardware H.264 encoder** (picamera2
``H264Encoder``, runs on the GPU): ~10× less bandwidth (~2–4 Mbps) and the
**CPU stays near-idle**, which is what makes 24/7 streaming actually viable.

Transport: one **H.264 access unit per LSL sample** on a 2-channel
``cf_string`` stream — channel 0 = access-unit bytes base64-encoded,
channel 1 = ``"1"`` for keyframes else ``"0"``. base64 because LSL string
channels are UTF-8 (raw bytes corrupt). **Baseline profile** (no B-frames)
so the consumer's frame↔timestamp mapping stays exact. SPS/PPS are repeated
before every keyframe so a consumer can (re)join at any keyframe.

Each sample's LSL timestamp is the camera **sensor capture time** converted
onto the LSL clock (not when Python handled it) — that is what makes the
EEG↔video alignment accurate.

Pi-only (picamera2). Imports nothing from the EEG code.

Usage (on the Pi, in the video venv)::

    ~/pi_camera/.venv-video/bin/python stream_picam.py
    ~/pi_camera/.venv-video/bin/python stream_picam.py -n Perun32_Video -W 960 -H 720 -f 30 -b 4000000
    ~/pi_camera/.venv-video/bin/python stream_picam.py --hflip --vflip   # camera mounted upside down

Ctrl-C to stop.
"""

import argparse
import base64
import collections
import sys
import threading
import time

import pylsl

try:
    from libcamera import Transform
    from picamera2 import Picamera2
    from picamera2.encoders import H264Encoder
    from picamera2.outputs import Output
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    sys.stderr.write(
        "\nCould not import the camera stack (%s).\n"
        "Run on the Raspberry Pi, with:\n"
        "  sudo apt install -y python3-picamera2\n"
        "and a venv made with: python3 -m venv .venv-video --system-site-packages\n\n"
        % exc
    )
    raise


_BOOTTIME = getattr(time, "CLOCK_BOOTTIME", time.CLOCK_MONOTONIC)


def _parse_args(argv):
    p = argparse.ArgumentParser(
        description="Stream the Pi camera to LSL as hardware H.264.")
    p.add_argument("-n", "--name", default="Perun32_Video",
                   help="LSL stream name (default: Perun32_Video).")
    p.add_argument("-W", "--width", type=int, default=960, help="Width (default: 960).")
    p.add_argument("-H", "--height", type=int, default=720, help="Height (default: 720).")
    p.add_argument("-f", "--fps", type=float, default=30.0, help="FPS (default: 30).")
    p.add_argument("-b", "--bitrate", type=int, default=4_000_000,
                   help="H.264 bitrate in bits/s (default: 4000000 = 4 Mbps).")
    p.add_argument("-g", "--gop", type=int, default=0,
                   help="Keyframe interval in frames (default: 0 = once per "
                        "second = fps; smaller = more robust + bigger).")
    p.add_argument("--hflip", action="store_true", help="Flip horizontally.")
    p.add_argument("--vflip", action="store_true", help="Flip vertically.")
    p.add_argument("--queue", type=int, default=120,
                   help="Max access units buffered for the sender before the "
                        "oldest is dropped (default: 120).")
    return p.parse_args(argv)


def _build_outlet(args, gop):
    info = pylsl.StreamInfo(
        name=args.name, type="Video", channel_count=2,
        nominal_srate=pylsl.IRREGULAR_RATE,
        channel_format=pylsl.cf_string,
        source_id="picam-h264-%s-%dx%d" % (args.name, args.width, args.height),
    )
    desc = info.desc()
    desc.append_child_value("manufacturer", "RaspberryPi")
    desc.append_child_value("sensor", "ov5647")
    chans = desc.append_child("channels")
    c0 = chans.append_child("channel")
    c0.append_child_value("label", "h264")
    c0.append_child_value("type", "video")
    c1 = chans.append_child("channel")
    c1.append_child_value("label", "keyframe")
    c1.append_child_value("type", "marker")
    enc = desc.append_child("encoding")
    enc.append_child_value("codec", "h264")
    enc.append_child_value("profile", "baseline")
    enc.append_child_value("format", "annexb")
    enc.append_child_value("transport", "base64")
    enc.append_child_value("width", str(args.width))
    enc.append_child_value("height", str(args.height))
    enc.append_child_value("fps", str(args.fps))
    enc.append_child_value("bitrate", str(args.bitrate))
    enc.append_child_value("gop", str(gop))
    return pylsl.StreamOutlet(info, chunk_size=1, max_buffered=30)


class _Queue:
    """Bounded drop-oldest hand-off (capture/encoder thread -> sender).

    A WiFi stall must never block the encoder. Dropping H.264 access units
    causes artifacts only until the next keyframe, where the consumer
    resyncs — acceptable degradation, and it should essentially never
    happen at ~4 Mbps over a working link.
    """

    def __init__(self, maxlen):
        self._dq = collections.deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self.dropped = 0

    def put(self, item):
        with self._lock:
            if len(self._dq) == self._dq.maxlen:
                self.dropped += 1
            self._dq.append(item)
        self._wake.set()

    def get(self, timeout):
        if self._wake.wait(timeout):
            with self._lock:
                if self._dq:
                    item = self._dq.popleft()
                    if not self._dq:
                        self._wake.clear()
                    return item
                self._wake.clear()
        return None


class _LslOutput(Output):
    """picamera2 calls outputframe() once per encoded access unit."""

    def __init__(self, queue):
        super().__init__()
        self._q = queue
        self.frames = 0
        self.keyframes = 0
        self.bytes = 0

    def outputframe(self, frame, keyframe=True, timestamp=None,
                    *args, **kwargs):
        # Read both clocks now, then convert the frame's sensor timestamp
        # (picamera2 gives SensorTimestamp in microseconds, boottime) onto
        # the LSL clock. Fall back to "now" if the value looks unexpected.
        now_lsl = pylsl.local_clock()
        now_boot = time.clock_gettime(_BOOTTIME)
        ts = now_lsl
        if timestamp is not None:
            age = now_boot - (timestamp / 1e6)
            if 0.0 <= age < 2.0:
                ts = now_lsl - age
        data = bytes(frame)
        self.frames += 1
        self.bytes += len(data)
        if keyframe:
            self.keyframes += 1
        self._q.put((data, bool(keyframe), ts))


def _sender(outlet, q, stop):
    while not stop.is_set():
        item = q.get(timeout=0.5)
        if item is None:
            continue
        data, keyframe, ts = item
        outlet.push_sample(
            [base64.b64encode(data).decode("ascii"), "1" if keyframe else "0"],
            ts)


def main(argv=None):
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    gop = args.gop if args.gop > 0 else max(1, int(round(args.fps)))

    picam2 = Picamera2()
    frame_us = int(round(1_000_000 / args.fps))
    cfg = picam2.create_video_configuration(
        main={"size": (args.width, args.height)},
        transform=Transform(hflip=args.hflip, vflip=args.vflip),
        controls={"FrameDurationLimits": (frame_us, frame_us)},
    )
    picam2.configure(cfg)

    encoder = H264Encoder(
        bitrate=args.bitrate, repeat=True, iperiod=gop,
        framerate=args.fps, profile="baseline",
    )

    outlet = _build_outlet(args, gop)
    q = _Queue(maxlen=args.queue)
    stop = threading.Event()
    out = _LslOutput(q)
    sender = threading.Thread(target=_sender, args=(outlet, q, stop),
                              name="lsl-sender", daemon=True)

    sender.start()
    picam2.start_recording(encoder, out)
    print("Streaming '%s'  %dx%d @ %g fps  H.264 %d bps  gop=%d  (Ctrl-C)"
          % (args.name, args.width, args.height, args.fps, args.bitrate, gop),
          flush=True)

    t0 = time.monotonic()
    last_f = 0
    last_b = 0
    try:
        while True:
            time.sleep(5.0)
            dt = time.monotonic() - t0
            t0 = time.monotonic()
            df = out.frames - last_f
            db = out.bytes - last_b
            last_f = out.frames
            last_b = out.bytes
            print("  %d frames (%.1f fps), %d keyframes, %.2f Mbps, "
                  "%d dropped"
                  % (out.frames, df / dt if dt else 0, out.keyframes,
                     (db * 8 / dt / 1e6) if dt else 0, q.dropped),
                  flush=True)
    except KeyboardInterrupt:
        print("\nStopping stream", flush=True)
    finally:
        stop.set()
        sender.join(timeout=2.0)
        try:
            picam2.stop_recording()
        except Exception:
            pass
        picam2.close()


if __name__ == "__main__":
    main()
