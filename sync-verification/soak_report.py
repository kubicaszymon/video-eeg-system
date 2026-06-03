"""Fast long-run integrity report (no video decode).

Reads only the timestamp/index/clock files of a recorded session and reports:
  - EEG: frame count, wall duration, effective rate, dropout gaps
  - Video: frame count, fps, dropout gaps, keyframe cadence, bitrate
  - Clock: per-stream LSL time_correction over the whole run (offset + drift)

Designed for multi-hour/day recordings where decoding every frame is
impractical. Run::

    python sync-verification/soak_report.py <session folder> [--gap-eeg 0.05] [--gap-video 0.5]
"""
import argparse
import csv
import json
import os
import sys

import numpy as np


def _fmt_hms(seconds):
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m{s:02d}s"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session")
    ap.add_argument("--gap-eeg", type=float, default=0.05,
                    help="EEG gap threshold in s (default 0.05 = 25x nominal dt)")
    ap.add_argument("--gap-video", type=float, default=0.5,
                    help="video gap threshold in s (default 0.5)")
    args = ap.parse_args()
    s = args.session

    meta = json.load(open(os.path.join(s, "meta.json")))
    nch = int(meta.get("eeg_nch", 0))
    srate = float(meta.get("eeg_srate_nominal", 0.0))
    print(f"Session: {os.path.basename(s.rstrip(os.sep))}")
    print(f"  EEG stream '{meta.get('eeg_name')}': {nch} ch, nominal {srate:g} Hz")
    print(f"  Video stream '{meta.get('video_name')}'")
    print(f"  subject={meta.get('subject')!r} operator={meta.get('operator')!r}")
    print()

    # ---------------- EEG timestamps ----------------
    ets = np.fromfile(os.path.join(s, "eeg_ts.f64"), dtype="<f8")
    if ets.size:
        dur = ets[-1] - ets[0]
        eff = (ets.size - 1) / dur if dur > 0 else 0.0
        dt = np.diff(ets)
        gaps = np.where(dt > args.gap_eeg)[0]
        gap_total = float(dt[gaps].sum()) if gaps.size else 0.0
        expected = srate * dur if srate else 0.0
        print("EEG:")
        print(f"  frames        : {ets.size:,}")
        print(f"  wall duration : {_fmt_hms(dur)}  ({dur:,.1f} s)")
        print(f"  effective rate: {eff:.4f} Hz  (nominal {srate:g})")
        if expected:
            print(f"  expected@nom  : {expected:,.0f}  -> captured {100*ets.size/expected:.3f}%")
        print(f"  dropout gaps  : {gaps.size}  (>{args.gap_eeg*1000:.0f} ms), "
              f"total lost ~{_fmt_hms(gap_total)}")
        if gaps.size:
            order = gaps[np.argsort(dt[gaps])[::-1][:5]]
            print("  largest gaps  :")
            for i in order:
                t_rel = ets[i] - ets[0]
                print(f"     +{_fmt_hms(t_rel)} : {dt[i]:.2f} s")
        print()

    # ---------------- Video index ----------------
    vts, key, nbytes = [], [], []
    with open(os.path.join(s, "video_index.csv"), newline="") as f:
        r = csv.reader(f)
        next(r, None)  # header
        for row in r:
            if len(row) < 3:
                continue
            vts.append(float(row[0]))
            key.append(row[1] == "1")
            nbytes.append(int(row[2]))
    vts = np.asarray(vts, dtype=np.float64)
    nbytes = np.asarray(nbytes, dtype=np.int64)
    key = np.asarray(key, dtype=bool)
    if vts.size:
        dur = vts[-1] - vts[0]
        fps = (vts.size - 1) / dur if dur > 0 else 0.0
        dt = np.diff(vts)
        gaps = np.where(dt > args.gap_video)[0]
        gap_total = float(dt[gaps].sum()) if gaps.size else 0.0
        nk = int(key.sum())
        mbits = nbytes.sum() * 8 / 1e6
        print("Video:")
        print(f"  frames        : {vts.size:,}  (keyframes {nk:,}, "
              f"~1 every {vts.size/nk:.0f})" if nk else f"  frames        : {vts.size:,}")
        print(f"  wall duration : {_fmt_hms(dur)}  ({dur:,.1f} s)")
        print(f"  effective fps : {fps:.4f}")
        print(f"  payload       : {nbytes.sum()/1e9:.2f} GB  -> avg {mbits/dur:,.0f} kbps"
              if dur > 0 else f"  payload       : {nbytes.sum()/1e9:.2f} GB")
        print(f"  dropout gaps  : {gaps.size}  (>{args.gap_video*1000:.0f} ms), "
              f"total ~{_fmt_hms(gap_total)}")
        if gaps.size:
            order = gaps[np.argsort(dt[gaps])[::-1][:5]]
            print("  largest gaps  :")
            for i in order:
                t_rel = vts[i] - vts[0]
                print(f"     +{_fmt_hms(t_rel)} : {dt[i]:.2f} s")
        print()

    # ---------------- Clock offsets (inter-stream sync stability) ----------------
    rows = {"eeg": [], "video": []}
    with open(os.path.join(s, "clock.csv"), newline="") as f:
        r = csv.reader(f)
        next(r, None)
        for row in r:
            if len(row) < 3:
                continue
            lc, stream, tc = row[0], row[1], row[2]
            if stream in rows:
                try:
                    rows[stream].append((float(lc), float(tc)))
                except ValueError:
                    pass
    print("Clock (LSL time_correction over the run):")
    fits = {}
    for stream in ("eeg", "video"):
        a = np.asarray(rows[stream], dtype=np.float64)
        if a.shape[0] < 2:
            print(f"  {stream:5s}: <2 samples")
            continue
        t = a[:, 0] - a[0, 0]
        tc = a[:, 1] * 1000.0  # ms
        slope, intercept = np.polyfit(t, tc, 1)  # ms per second
        fits[stream] = (slope, tc[0], tc[-1])
        print(f"  {stream:5s}: {a.shape[0]:,} samples | "
              f"tc start {tc[0]:+.3f} ms -> end {tc[-1]:+.3f} ms | "
              f"drift {slope*3600:+.3f} ms/h, range {tc.max()-tc.min():.3f} ms")
    if "eeg" in fits and "video" in fits:
        rel = (fits["video"][0] - fits["eeg"][0]) * 3600.0
        print(f"  inter-stream relative clock drift: {rel:+.3f} ms/h")
    print()
    print("(Marker-based offset/jitter requires the EEG AUX pulse; not in this run.)")


if __name__ == "__main__":
    main()
