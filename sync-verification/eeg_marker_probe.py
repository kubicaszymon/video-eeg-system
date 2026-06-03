"""Scan the recorded EEG for an injected sync-marker pulse train.

Answers a single question: is the AUX marker pulse actually present in the
recorded EEG data, and on which channel? Works straight off eeg_samples.f32
(memmapped) -- no video decode. The Pico fires a ~50 ms pulse every ~5 s, so a
connected AUX channel should show a regular ~0.2 Hz train of square excursions.

    python sync-verification/eeg_marker_probe.py <session> [--start-h 1.0] [--dur-s 180] [--period 5.0]
"""
import argparse
import json
import os

import numpy as np


def _events(level, ts, k, min_gap):
    med = np.median(level)
    mad = np.median(np.abs(level - med))
    spread = 1.4826 * mad if mad > 0 else (np.std(level) or 1.0)
    hot = level > med + k * spread
    rising = np.flatnonzero((~hot[:-1]) & hot[1:]) + 1
    out, last = [], -np.inf
    for i in rising:
        if ts[i] - last >= min_gap:
            out.append(ts[i]); last = ts[i]
    return np.asarray(out), (med + k * spread), spread


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session")
    ap.add_argument("--start-h", type=float, default=1.0)
    ap.add_argument("--dur-s", type=float, default=180.0)
    ap.add_argument("--period", type=float, default=5.0, help="expected marker period (s)")
    ap.add_argument("--k", type=float, default=6.0)
    args = ap.parse_args()
    s = args.session

    meta = json.load(open(os.path.join(s, "meta.json")))
    nch = int(meta["eeg_nch"])
    srate = float(meta.get("eeg_srate_nominal", 500.0))
    labels = meta.get("eeg_channels", [f"ch{i}" for i in range(nch)])

    ts = np.fromfile(os.path.join(s, "eeg_ts.f64"), dtype="<f8")
    N = ts.size
    raw = np.memmap(os.path.join(s, "eeg_samples.f32"), dtype="<f4", mode="r", shape=(N, nch))

    i0 = int(args.start_h * 3600 * srate)
    i1 = min(N, i0 + int(args.dur_s * srate))
    if i0 >= N:
        i0, i1 = 0, min(N, int(args.dur_s * srate))
    x = np.asarray(raw[i0:i1], dtype=np.float64)   # copy window into RAM
    tw = ts[i0:i1]
    win_s = tw[-1] - tw[0]
    expected = win_s / args.period
    print(f"Window: {args.start_h:.2f} h .. +{win_s:.0f}s  ({i1-i0:,} samples, {nch} ch)")
    print(f"Expected pulses if marker live: ~{expected:.0f} (every {args.period}s)\n")

    print(f"{'ch':>3} {'label':<14} {'p2p(uV?)':>10} {'MAD':>9} {'events':>7} {'med_gap_s':>9}  verdict")
    best = None
    for c in range(nch):
        col = x[:, c]
        dev = np.abs(col - np.median(col))
        ev, thr, spread = _events(dev, tw, args.k, min_gap=args.period * 0.5)
        p2p = float(col.max() - col.min())
        gaps = np.diff(ev) if ev.size >= 2 else np.array([])
        med_gap = float(np.median(gaps)) if gaps.size else 0.0
        # "periodic at ~period" if we got a plausible count and consistent spacing
        periodic = (ev.size >= max(3, 0.5 * expected)
                    and gaps.size
                    and abs(med_gap - args.period) < 0.25 * args.period
                    and np.std(gaps) < 0.2 * args.period)
        verdict = "<-- PULSE TRAIN" if periodic else ""
        if periodic and (best is None or ev.size > best[1]):
            best = (c, ev.size, med_gap)
        # only print informative rows to keep it readable: active or flagged
        if periodic or ev.size or p2p > 1e-3:
            print(f"{c:>3} {str(labels[c])[:14]:<14} {p2p:>10.2f} {spread:>9.3f} "
                  f"{ev.size:>7} {med_gap:>9.2f}  {verdict}")

    print()
    if best is not None:
        print(f"RESULT: marker pulse train FOUND on channel {best[0]} "
              f"('{labels[best[0]]}') — {best[1]} events, median spacing {best[2]:.2f}s.")
        print("        => EEG marker IS recoverable; the earlier EEG=0 was a "
              "detector-threshold issue (max-across-channels drowned it out).")
    else:
        print("RESULT: no ~5s-periodic pulse train on ANY channel in this window.")
        print("        => the pulse is NOT in the recorded EEG (hardware/AUX path), "
              "not a software detection problem.")
        print("        Try another window (--start-h) in case the marker was "
              "intermittent before concluding.")


if __name__ == "__main__":
    main()
