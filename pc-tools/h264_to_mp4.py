"""Wrap a session's raw H.264 elementary stream into a playable .mp4.

The Recorder writes ``video.h264`` as a bare Annex-B elementary stream (one
hardware H.264 access unit after another, no container). VLC/most players
can't open that directly -- they need a container with timing. This remuxes
(stream copy, no re-encode -- fast, lossless) into an .mp4 you can
double-click, purely for eyeballing the footage (e.g. "is the LED visible?").

Playback timing is a constant 30 fps placeholder, NOT the real LSL sensor
timestamps -- this file is for visual inspection only; all timing analysis
uses ``video_index.csv``.

Run (PC)::

    .venv-pc\\Scripts\\python pc_examples\\h264_to_mp4.py recordings\\session_YYYYmmdd-HHMMSS
    .venv-pc\\Scripts\\python pc_examples\\h264_to_mp4.py path\\to\\video.h264 [out.mp4] [--fps 30]
"""

import argparse
import fractions
import os
import sys

import av


def remux(src, dst, fps):
    inp = av.open(src, format="h264")
    in_stream = inp.streams.video[0]
    out = av.open(dst, "w")
    out_stream = out.add_stream_from_template(in_stream)
    tb = fractions.Fraction(1, int(fps))
    out_stream.time_base = tb

    n = 0
    for packet in inp.demux(in_stream):
        if packet.size == 0:
            continue                       # flush packet at EOF
        packet.stream = out_stream
        packet.pts = n
        packet.dts = n                     # baseline profile: dts == pts
        packet.time_base = tb
        out.mux(packet)
        n += 1

    out.close()
    inp.close()
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(description="Remux raw H.264 to .mp4.")
    ap.add_argument("path", help="A session_* folder, or a video.h264 file.")
    ap.add_argument("out", nargs="?", default=None, help="Output .mp4 path.")
    ap.add_argument("--fps", type=float, default=30.0,
                    help="Playback frame rate placeholder (default 30).")
    a = ap.parse_args(argv if argv is not None else sys.argv[1:])

    src = a.path
    if os.path.isdir(src):
        src = os.path.join(src, "video.h264")
    if not os.path.exists(src):
        print("Not found: %s" % src)
        sys.exit(1)
    dst = a.out or os.path.splitext(src)[0] + ".mp4"

    n = remux(src, dst, a.fps)
    print("Wrote %s (%d frames @ %.0f fps placeholder)." % (dst, n, a.fps))
    print("Open it in VLC to check the footage (timing is for viewing only).")


if __name__ == "__main__":
    main()
