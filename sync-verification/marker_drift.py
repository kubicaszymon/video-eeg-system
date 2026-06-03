"""Offline EEG<->video sync drift from the hardware marker, on a recorded session.

Uses the EEG digital trigger channel (default label 'Events') for EEG marker
times and the camera LED (frame brightness) for video marker times, pairs them,
and fits  offset(t) = fixed_offset + drift*t  with residual jitter.

To stay fast on multi-day recordings it does NOT decode the whole video: it
seeks into the raw Annex-B stream using byte offsets derived from
video_index.csv and decodes only a few short windows (default: start / middle /
end), which is enough leverage for the drift slope + jitter.

    python sync-verification/marker_drift.py <session> [--trigger Events]
        [--windows 0.1,24.5,48.8] [--dur 300] [--period 5.0] [--k 6.0]
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pc-tools"))
from h264_inlet import H264Decoder  # noqa: E402


def _rising_times(level, ts, k, min_gap):
    level = np.asarray(level, float); ts = np.asarray(ts, float)
    if level.size < 2:
        return np.empty(0)
    med = np.median(level)
    mad = np.median(np.abs(level - med))
    spread = 1.4826 * mad if mad > 0 else (np.std(level) or 1.0)
    hot = level > med + k * spread
    rising = np.flatnonzero((~hot[:-1]) & hot[1:]) + 1
    out, last = [], -np.inf
    for i in rising:
        if ts[i] - last >= min_gap:
            out.append(ts[i]); last = ts[i]
    return np.asarray(out)


def _led_marker_times(grids, bts, eeg_w, k, period):
    """Matched filter using the known EEG marker times: find the image block
    that is brightest in the ~0.2 s windows around each EEG marker vs. far from
    any marker. That block is the LED. Returns (video_marker_times, diag)."""
    n, gh, gw = grids.shape
    flat = grids.reshape(n, gh * gw).astype(np.float64)
    if eeg_w.size == 0:
        return np.empty(0), None
    d = np.min(np.abs(bts[:, None] - eeg_w[None, :]), axis=1)  # frame->nearest marker
    on = d <= 0.20
    off = d >= 0.60
    if on.sum() < 3 or off.sum() < 10:
        return np.empty(0), None
    mu_on = flat[on].mean(axis=0)
    mu_off = flat[off].mean(axis=0)
    sd = flat.std(axis=0) + 1e-6
    score = (mu_on - mu_off) / sd
    b = int(np.argmax(score))
    diag = (b // gw, b % gw, float(score[b]), float(mu_on[b] - mu_off[b]))
    mk = _rising_times(flat[:, b], bts, k, period * 0.5)
    return mk, diag


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session")
    ap.add_argument("--trigger", default="Events")
    ap.add_argument("--windows", default="0.1,24.5,48.8", help="window start times in HOURS")
    ap.add_argument("--dur", type=float, default=300.0)
    ap.add_argument("--period", type=float, default=5.0)
    ap.add_argument("--k", type=float, default=6.0)
    args = ap.parse_args()
    s = args.session

    meta = json.load(open(os.path.join(s, "meta.json")))
    nch = int(meta["eeg_nch"]); labels = meta["eeg_channels"]
    srate = float(meta.get("eeg_srate_nominal", 500.0))
    tci = labels.index(args.trigger)

    # ---- EEG trigger markers (whole file) ----
    ets = np.fromfile(os.path.join(s, "eeg_ts.f64"), dtype="<f8"); N = ets.size
    eraw = np.memmap(os.path.join(s, "eeg_samples.f32"), dtype="<f4", mode="r", shape=(N, nch))
    trig = np.abs(np.asarray(eraw[:, tci], float) - np.median(eraw[:, tci]))
    eeg_mk = _rising_times(trig, ets, args.k, args.period * 0.5)
    print(f"EEG trigger '{args.trigger}' (ch {tci}): {eeg_mk.size} markers over "
          f"{(ets[-1]-ets[0])/3600:.1f} h\n")

    # ---- video index + byte offsets ----
    vts, vkey, vnb = [], [], []
    with open(os.path.join(s, "video_index.csv")) as f:
        next(f)
        for ln in f:
            a = ln.split(",")
            if len(a) >= 3:
                vts.append(float(a[0])); vkey.append(a[1] == "1"); vnb.append(int(a[2]))
    vts = np.asarray(vts); vkey = np.asarray(vkey, bool); vnb = np.asarray(vnb, np.int64)
    voff = np.concatenate([[0], np.cumsum(vnb)])  # byte offset of each AU
    h264 = os.path.join(s, "video.h264")
    t0 = ets[0]

    pairs_t, pairs_off = [], []
    for wh in [float(x) for x in args.windows.split(",")]:
        T = t0 + wh * 3600.0
        i_lo = int(np.searchsorted(vts, T))
        i_hi = int(np.searchsorted(vts, T + args.dur))
        if i_hi <= i_lo:
            print(f"  window @ {wh:.2f}h: no video here, skipped"); continue
        ks = np.flatnonzero(vkey[:i_lo + 1])
        start = ks[-1] if ks.size else 0          # decode from preceding keyframe
        with open(h264, "rb") as fh:
            fh.seek(int(voff[start]))
            blob = fh.read(int(voff[i_hi]) - int(voff[start]))
        dec = H264Decoder(); grids, bts = [], []
        F = 8   # max-pool factor: keeps a small bright LED dot alive
        p = 0
        for i in range(start, i_hi):
            n = int(vnb[i]); au = blob[p:p + n]; p += n
            for frame, fts in dec.feed(au, bool(vkey[i]), float(vts[i])):
                g = frame.max(axis=2)                       # brightest channel
                h, w = g.shape
                gh, gw = h // F, w // F
                g = g[:gh * F, :gw * F].reshape(gh, F, gw, F).max(axis=(1, 3))
                grids.append(g); bts.append(fts)
        for frame, fts in dec.flush():
            g = frame.max(axis=2)
            h, w = g.shape; gh, gw = h // F, w // F
            g = g[:gh * F, :gw * F].reshape(gh, F, gw, F).max(axis=(1, 3))
            grids.append(g); bts.append(fts if fts else 0.0)
        grids = np.asarray(grids, dtype=np.float32); bts = np.asarray(bts)
        m = (bts >= T) & (bts <= T + args.dur)
        eeg_w = eeg_mk[(eeg_mk >= T) & (eeg_mk <= T + args.dur)]
        vid_mk, diag = _led_marker_times(grids[m], bts[m], eeg_w, args.k, args.period)
        if diag is not None:
            print(f"      LED block (row {diag[0]},col {diag[1]}) on-off="
                  f"{diag[3]:+.1f} score={diag[2]:.2f}", end="")
        # pair nearest within half a period
        npair = 0
        for tv in vid_mk:
            if eeg_w.size == 0:
                break
            j = int(np.argmin(np.abs(eeg_w - tv)))
            if abs(eeg_w[j] - tv) <= args.period * 0.5:
                pairs_t.append(eeg_w[j] - t0); pairs_off.append((tv - eeg_w[j]) * 1000.0)
                npair += 1
        print(f"  window @ {wh:5.2f}h: video LED={vid_mk.size:3d}  EEG={eeg_w.size:3d}  paired={npair}")

    pairs_t = np.asarray(pairs_t); pairs_off = np.asarray(pairs_off)
    print()
    if pairs_t.size < 3:
        print("Not enough pairs to fit — LED may not be detectable by frame-mean "
              "brightness (try an ROI), or windows missed the marker.")
        return
    # robust-ish linear fit offset(ms) vs time(s)
    slope, intercept = np.polyfit(pairs_t, pairs_off, 1)   # ms per second
    resid = pairs_off - (slope * pairs_t + intercept)
    print("=== SYNC RESULT (hardware marker, %d pairs across the run) ===" % pairs_t.size)
    print(f"  fixed offset (video - EEG): {pairs_off.mean():+.2f} ms  "
          f"(median {np.median(pairs_off):+.2f})")
    print(f"  drift                      : {slope*3600:+.3f} ms/hour  "
          f"({slope*3600*( (ets[-1]-ets[0])/3600 ):+.1f} ms over the full {(ets[-1]-ets[0])/3600:.1f} h)")
    print(f"  residual jitter (1 sigma)  : {resid.std():.2f} ms")
    print(f"  offset range               : {pairs_off.min():+.2f} .. {pairs_off.max():+.2f} ms")


if __name__ == "__main__":
    main()
