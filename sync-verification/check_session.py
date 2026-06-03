"""Load a Recorder session, realise synchronization, run the sync analysis.

This is the "check later" half: it takes a folder written by the prototype's
Recorder (sync_prototype.py), maps both streams onto the common clock using
the recorded per-stream ``time_correction``, decodes the video through the
SAME shared H264Decoder, and reuses the validated drift analysis from
``xdf_sync_check.py`` (fixed offset / drift slope / residual jitter).

Run (PC)::

    .venv-pc\\Scripts\\python sync-verification\\check_session.py recordings\\session_YYYYmmdd-HHMMSS
"""

import argparse
import csv
import json
import os
import sys

import numpy as np

# Reuse the ONE shared decode path and the VALIDATED drift analysis.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pc-tools"))
sys.path.insert(0, os.path.dirname(__file__))
from h264_inlet import H264Decoder            # noqa: E402
from xdf_sync_check import _drift             # noqa: E402


class _Args:
    def __init__(self, min_gap, max_pair_dt, k):
        self.min_gap = min_gap
        self.max_pair_dt = max_pair_dt
        self.k = k


def _mean_tc(clock_csv):
    tc = {"eeg": [], "video": []}
    if not os.path.exists(clock_csv):
        return {"eeg": 0.0, "video": 0.0}
    with open(clock_csv, newline="") as f:
        for row in csv.DictReader(f):
            if row["stream"] in tc:
                tc[row["stream"]].append(float(row["time_correction"]))
    return {k: (float(np.mean(v)) if v else 0.0) for k, v in tc.items()}


def _decode_video(session):
    dec = H264Decoder()
    bright, vts = [], []
    idx = os.path.join(session, "video_index.csv")
    with open(idx, newline="") as f, \
         open(os.path.join(session, "video.h264"), "rb") as fv:
        for row in csv.DictReader(f):
            data = fv.read(int(row["nbytes"]))
            kf = row["keyframe"] == "1"
            for frame, fts in dec.feed(data, kf, float(row["ts"])):
                bright.append(float(frame.mean()))
                vts.append(fts)
        for frame, fts in dec.flush():
            bright.append(float(frame.mean()))
            vts.append(fts)
    return np.asarray(bright), np.asarray(vts, dtype=np.float64)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check a recorded session.")
    ap.add_argument("session", help="Path to a session_* folder.")
    ap.add_argument("--min-gap", type=float, default=2.0)
    ap.add_argument("--max-pair-dt", type=float, default=0.5)
    ap.add_argument("--k", type=float, default=6.0)
    a = ap.parse_args(argv if argv is not None else sys.argv[1:])

    s = a.session
    meta = json.load(open(os.path.join(s, "meta.json")))
    nch = int(meta["eeg_nch"])
    edata = np.fromfile(os.path.join(s, "eeg_samples.f32"),
                        dtype=np.float32).reshape(-1, nch)
    ets = np.fromfile(os.path.join(s, "eeg_ts.f64"), dtype=np.float64)
    m = min(len(edata), len(ets))
    edata, ets = edata[:m], ets[:m]
    bright, vts = _decode_video(s)

    if m < 2 or len(vts) < 2:
        print("Not enough data (eeg=%d samples, video=%d frames)."
              % (m, len(vts)))
        sys.exit(1)

    tc = _mean_tc(os.path.join(s, "clock.csv"))
    # Realise synchronization: map BOTH streams onto the common PC clock.
    ets_c = ets + tc["eeg"]
    vts_c = vts + tc["video"]

    vfps = len(vts) / (vts[-1] - vts[0])
    print("Session: %s" % os.path.basename(os.path.normpath(s)))
    print("EEG   '%s': %d samples, %.1fs, ~%.2f Hz  (clock_corr %+.1f ms)"
          % (meta["eeg_name"], m, ets[-1] - ets[0],
             m / (ets[-1] - ets[0]), tc["eeg"] * 1e3))
    print("Video '%s': %d frames, %.1fs, ~%.1f fps  (clock_corr %+.1f ms)"
          % (meta["video_name"], len(vts), vts[-1] - vts[0], vfps,
             tc["video"] * 1e3))
    overlap = min(ets_c[-1], vts_c[-1]) - max(ets_c[0], vts_c[0])
    print("Overlap on the common clock: %.1f s" % overlap)

    ok = _drift(ets_c, edata, bright, vts_c, vfps,
                _Args(a.min_gap, a.max_pair_dt, a.k))
    if not ok:
        mid = len(vts_c) // 2
        j = int(np.clip(np.searchsorted(ets_c, vts_c[mid]), 0, len(ets_c) - 1))
        print("\nNo marker train found — basic alignment spot check:")
        print("  mid video frame t=%.4f <-> nearest EEG t=%.4f  gap %.1f ms"
              % (vts_c[mid], ets_c[j], (ets_c[j] - vts_c[mid]) * 1e3))
        print("  (Fire the sync marker periodically to get the "
              "offset/drift/jitter numbers — see VIDEO_EEG_APP_SPEC.md §4.)")


if __name__ == "__main__":
    main()
