"""Prove the video-lag cause: frame-threaded decode emits frames in CLUMPS.

Captures real access units from the live stream, then replays them in order
through two decoders and logs how many frames each *feed* returns:

  * multithread (thread_type="AUTO")  -- the old setting
  * single-thread (thread_type="NONE") -- the fix

A live consumer that shows only the newest frame per poll displays roughly
`feeds_that_returned>=1 / total_feeds * fps` fps. If multithread returns
frames in clumps (long runs of 0 then a burst), that ratio collapses to a
few fps even though total decoded == ~fps. Single-thread returns 1 frame
per feed -> the ratio is ~1 -> full fps.

Run (PC, video Pi streaming)::

    .venv-pc\\Scripts\\python pc_examples\\decode_latency_probe.py
"""

import argparse
import base64
import sys
import time

import av
import numpy as np
import pylsl

_FPS = 30.0


def _resolve(name, timeout):
    for s in pylsl.resolve_streams(wait_time=timeout):
        if s.name() == name:
            return s
    return None


def _run_mode(label, thread_type, thread_count, aus):
    cc = av.CodecContext.create("h264", "r")
    cc.thread_type = thread_type
    try:
        cc.thread_count = thread_count
    except Exception:
        pass
    per_feed = []          # frames returned by each feed() after 1st keyframe
    started = False
    total = 0
    for data, kf in aus:
        if not started:
            if not kf:
                continue
            started = True
        try:
            out = list(cc.decode(av.Packet(data)))
        except Exception:
            out = []
        per_feed.append(len(out))
        total += len(out)
    pf = np.asarray(per_feed, dtype=np.int32)
    if pf.size == 0:
        print("  %-22s no decodable data" % label)
        return
    feeds = pf.size
    with_out = int(np.sum(pf >= 1))
    # longest run of consecutive zero-output feeds = the visible stall
    zr = mx = 0
    for v in pf:
        zr = zr + 1 if v == 0 else 0
        mx = max(mx, zr)
    shown_fps = with_out / feeds * _FPS
    print("  %-22s feeds=%d  total_frames=%d  feeds_with_output=%d (%.0f%%)"
          % (label, feeds, total, with_out, 100.0 * with_out / feeds))
    print("  %-22s max zero-output run=%d feeds (~%.0f ms stall)  "
          "=> est. displayed ~%.1f fps"
          % ("", mx, mx / _FPS * 1000.0, shown_fps))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Prove decode clumping / the "
                                             "single-thread fix.")
    ap.add_argument("--name", default="Perun32_Video")
    ap.add_argument("--aus", type=int, default=450,
                    help="Access units to capture (~15 s @ 30 fps).")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    si = _resolve(args.name, 5.0)
    if si is None:
        print("Stream '%s' not found (is the video Pi streaming?)"
              % args.name)
        sys.exit(2)
    inlet = pylsl.StreamInlet(si, max_buflen=360, max_chunklen=1)
    while inlet.pull_chunk(timeout=0.0, max_samples=512)[0]:
        pass                                    # flush stale buffer

    print("Capturing %d access units live..." % args.aus, flush=True)
    aus = []
    while len(aus) < args.aus:
        smp, ts = inlet.pull_sample(timeout=2.0)
        if smp is None:
            break
        aus.append((base64.b64decode(smp[0]), smp[1] == "1"))
    print("Captured %d. Replaying through both decoders:\n" % len(aus),
          flush=True)

    print("=== OLD: multithreaded decode (thread_type=AUTO) ===")
    _run_mode("multithread", "AUTO", 0, aus)
    print("\n=== FIX: single-threaded decode (thread_type=NONE) ===")
    _run_mode("single-thread", "NONE", 1, aus)
    print("\nIf 'multithread' shows a low feeds_with_output %% / long "
          "zero-output run and 'single-thread' shows ~100%% / run≈1, the "
          "clumping was the cause and the fix removes it.")


if __name__ == "__main__":
    main()
