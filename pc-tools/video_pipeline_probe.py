"""Locate the video-lag bottleneck: network delivery vs H.264 decode.

Both PC apps show the camera at ~3-4 fps even though the decoded-frame
counter says ~30 fps -> frames are produced ~30/s but reach the consumer
in **bursts**. This probe says *why*, without guessing, by isolating the
two suspects so neither contaminates the other:

  Phase A - ARRIVAL CADENCE (near-zero-cost consumer, NO decode).
    Flush the inlet, then pull samples one at a time doing nothing but
    timestamping. Measures how the network actually delivers frames:
      * local arrival interval  (should be ~33 ms if paced at 30 fps)
      * sender-timestamp interval (how evenly the Pi *produced* them)
    If arrival is clumped (many ~0 ms then long gaps) while the sender
    interval is steady ~33 ms -> the **network** is bursting them
    (the documented 2.4 GHz airtime saturation).

  Phase B - DECODE COST (isolated, NO network in the loop).
    Re-decode the access units captured in Phase A, in order, timing each
    feed(). If median/p95 per-AU decode > ~33 ms -> the PC **decode**
    can't sustain 30 fps and backlog snowballs into bursts.

Run (PC, while the video stream is up)::

    .venv-pc\\Scripts\\python pc_examples\\video_pipeline_probe.py
    .venv-pc\\Scripts\\python pc_examples\\video_pipeline_probe.py --arrival-seconds 20
"""

import argparse
import base64
import os
import sys
import time

import numpy as np
import pylsl

# Reuse the ONE shared decode path (per the project rule); h264_inlet.py is a
# sibling module in this same pc-tools/ folder.
sys.path.insert(0, os.path.dirname(__file__))
from h264_inlet import H264Decoder  # noqa: E402

_FRAME_MS_30 = 1000.0 / 30.0


def _stats(name, x_ms):
    x = np.asarray(x_ms, dtype=np.float64)
    if x.size == 0:
        print("  %-26s (no data)" % name)
        return
    print("  %-26s n=%d  mean=%.1f  med=%.1f  p95=%.1f  p99=%.1f  "
          "max=%.1f ms" % (name, x.size, x.mean(), np.median(x),
                           np.percentile(x, 95), np.percentile(x, 99),
                           x.max()))


def _resolve(name, timeout):
    for s in pylsl.resolve_streams(wait_time=timeout):
        if s.name() == name:
            return s
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Diagnose video pipeline lag.")
    ap.add_argument("--name", default="Perun32_Video")
    ap.add_argument("--arrival-seconds", type=float, default=15.0,
                    help="Phase A duration (default 15 s).")
    ap.add_argument("--max-capture", type=int, default=1500,
                    help="Max access units to keep for Phase B decode.")
    ap.add_argument("--gap-ms", type=float, default=100.0,
                    help="Arrival interval above this counts as a 'gap'.")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    print("Resolving '%s' ..." % args.name, flush=True)
    si = _resolve(args.name, 5.0)
    if si is None:
        print("Stream '%s' not found. Is the video Pi streaming and on the "
              "same subnet?" % args.name)
        sys.exit(2)
    # small buffer: we want to observe real-time delivery, not a huge backlog
    inlet = pylsl.StreamInlet(si, max_buflen=360, max_chunklen=1)

    # Drain whatever is already buffered so Phase A sees fresh, live arrivals.
    flushed = 0
    while True:
        s, _ = inlet.pull_chunk(timeout=0.0, max_samples=512)
        if not s:
            break
        flushed += len(s)
    print("Flushed %d buffered samples. Phase A: measuring arrival cadence "
          "for %.0f s (no decode)..." % (flushed, args.arrival_seconds),
          flush=True)

    arr_iv, snd_iv = [], []          # ms between consecutive frames
    cap = []                         # (b64, keyframe, sender_ts) in order
    near_zero = 0                    # arrivals < 2 ms apart (already queued)
    prev_local = prev_send = None
    t_end = time.perf_counter() + args.arrival_seconds
    while time.perf_counter() < t_end:
        smp, ts = inlet.pull_sample(timeout=1.0)
        if smp is None:
            continue
        now = time.perf_counter()
        if prev_local is not None:
            iv = (now - prev_local) * 1000.0
            arr_iv.append(iv)
            if iv < 2.0:
                near_zero += 1
            snd_iv.append((ts - prev_send) * 1000.0)
        prev_local, prev_send = now, ts
        if len(cap) < args.max_capture:
            cap.append((smp[0], smp[1] == "1", ts))

    n = len(arr_iv) + 1
    dur = (args.arrival_seconds)
    recv_fps = n / dur if dur else 0.0
    print("\n=== Phase A: network delivery ===")
    print("  frames received: %d  (~%.1f fps over %.0f s)"
          % (n, recv_fps, dur))
    _stats("local arrival interval", arr_iv)
    _stats("sender-ts interval", snd_iv)
    if arr_iv:
        gaps = int(np.sum(np.asarray(arr_iv) > args.gap_ms))
        print("  arrivals < 2 ms apart: %d / %d  (%.0f%%)  <- buffered/bursty"
              % (near_zero, len(arr_iv), 100.0 * near_zero / len(arr_iv)))
        print("  gaps > %.0f ms: %d  (each gap = a visible stall)"
              % (args.gap_ms, gaps))

    print("\n=== Phase B: isolated decode cost (no network) ===")
    if len(cap) < 10:
        print("  too few AUs captured to time decode.")
        _verdict(arr_iv, snd_iv, None, args)
        return
    # start at the first keyframe so the decoder can establish.
    start = next((i for i, c in enumerate(cap) if c[1]), None)
    dec = H264Decoder()
    feed_ms, frames_out = [], 0
    if start is None:
        print("  no keyframe in the captured window (can't decode-time).")
    else:
        for b64, kf, ts in cap[start:]:
            data = base64.b64decode(b64)
            t0 = time.perf_counter()
            out = dec.feed(data, kf, ts)
            feed_ms.append((time.perf_counter() - t0) * 1000.0)
            frames_out += len(out)
        _stats("decode time / access unit", feed_ms)
        tot = sum(feed_ms) / 1000.0
        if tot > 0:
            print("  decoded %d frames in %.2f s  -> decode-limited ceiling "
                  "~%.0f fps" % (frames_out, tot, frames_out / tot))
        over = int(np.sum(np.asarray(feed_ms) > _FRAME_MS_30))
        print("  AUs slower than one 30 fps frame (%.1f ms): %d / %d"
              % (_FRAME_MS_30, over, len(feed_ms)))

    _verdict(arr_iv, snd_iv, feed_ms, args)


def _verdict(arr_iv, snd_iv, feed_ms, args):
    print("\n=== VERDICT ===")
    a = np.asarray(arr_iv, dtype=np.float64) if arr_iv else None
    s = np.asarray(snd_iv, dtype=np.float64) if snd_iv else None
    f = np.asarray(feed_ms, dtype=np.float64) if feed_ms else None

    decode_bound = f is not None and f.size and np.median(f) > _FRAME_MS_30
    sender_even = s is not None and s.size and np.median(s) < 45 \
        and np.percentile(s, 95) < 80
    arrival_clumped = a is not None and a.size and (
        np.percentile(a, 95) > 3 * max(np.median(a), 1.0)
        or np.sum(a > args.gap_ms) > 0.02 * a.size)

    if decode_bound:
        print("  -> DECODE-BOUND. The PC cannot decode 960x720 H.264 at "
              "30 fps (median per-AU > one frame). Backlog snowballs into "
              "bursts. Fix is PC-side: faster/HW decode, fewer pixels, or a "
              "lower live frame target — NOT the router.")
    elif arrival_clumped and sender_even:
        print("  -> NETWORK-BOUND. The Pi produced frames evenly (steady "
              "sender interval) but they ARRIVE clumped. This is the "
              "documented 2.4 GHz airtime saturation. The dedicated router "
              "you ordered targets exactly this; a live latency-cap helps "
              "meanwhile.")
    elif arrival_clumped and not sender_even:
        print("  -> SENDER/CAPTURE UNEVEN. Frames were produced unevenly on "
              "the Pi (sender-ts interval itself is bursty). Look at the "
              "video Pi (encoder/CPU/camera pacing), not the PC or router.")
    else:
        print("  -> Pipeline delivery + decode both look healthy here. The "
              "lag is then in the CONSUMER (poll() draining whole backlog "
              "then bulk-decoding, and/or display). Fix is in h264_inlet/"
              "the app loop, not the network.")
    print("  (Numbers above are the evidence — read them, don't just trust "
          "this line.)")


if __name__ == "__main__":
    main()
