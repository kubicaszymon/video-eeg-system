"""Hardware-marker EEG<->video sync accuracy from a recorded session.

This is the measurement that turns "the streams are aligned" into an actual
millisecond number. It is purpose-built for the Pico sync marker (LED in the
camera view + a TTL pulse into the Perun32 RIN1 sync input, both fired at the
SAME instant every few seconds -- see ``sync_marker/main.py``).

Why this exists separately from ``check_session.py`` / ``xdf_sync_check.py``:
their generic detectors use *whole-frame mean brightness* and *max deviation
across all EEG channels*. For this rig both fail -- the LED is a tiny dot, and
the clean marker is the dedicated **Events** channel (digital 0 -> pulse).

How it works:

1. Decode the video once into a small max-pooled grayscale stack (cached to
   ``_stack_cache.npz``; the ~4 min decode then happens only once).
2. Detect EEG markers as rising edges of the **Events** channel (clean
   digital 0 -> pulse), map them onto the common PC clock.
3. **Locate the LED** as the pixel-block whose brightness best *correlates*
   with the known EEG marker times. Variance/percentile metrics fail here: a
   50 ms flash is only ~1% of frames, so a slowly-drifting background region
   out-varies it. Correlating against 135 regularly-spaced markers is robust;
   it only fixes *where* the LED is -- the offset is still measured from
   independent edge times, so there is no circular bias.
4. Detect the LED's own rising edges, pair them with the EEG markers (reusing
   the validated nearest-neighbour pairing + robust fit from
   ``xdf_sync_check``), and report **fixed offset / drift slope / jitter**.

Run (PC)::

    .venv-pc\\Scripts\\python pc_examples\\marker_sync_check.py recordings\\session_YYYYmmdd-HHMMSS
"""

import argparse
import csv
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pc-tools"))
sys.path.insert(0, os.path.dirname(__file__))
from h264_inlet import H264Decoder                                  # noqa: E402
from xdf_sync_check import (_seed_offset, _pair_events,             # noqa: E402
                            _robust_linfit)

DOWNSCALE = 8          # max-pool into WxH/8 blocks (keeps the LED dot alive)
ROI_HALF = 1           # read brightness from a +/-1 block window around the LED
CORR_WIN = 1.00        # +/- s window around each EEG marker for LED-finding
                       # (must exceed |fixed_offset + cumulative drift|; 1 s
                       # handles up to ~100 min at 9 ms/min drift)


def _mean_tc(clock_csv):
    """Mean recorded time_correction per stream -> common-clock mapping."""
    tc = {"eeg": [], "video": []}
    if os.path.exists(clock_csv):
        with open(clock_csv, newline="") as f:
            for row in csv.DictReader(f):
                if row["stream"] in tc:
                    tc[row["stream"]].append(float(row["time_correction"]))
    return {k: (float(np.mean(v)) if v else 0.0) for k, v in tc.items()}


def _decode_stack(session, rebuild=False):
    """Max-pooled grayscale video stack (N, h, w) uint8 + timestamps.

    Max-pool (not decimate) so a tiny bright LED always survives. Cached so
    the slow PyAV decode happens only once per session.
    """
    cache = os.path.join(session, "_stack_cache.npz")
    if os.path.exists(cache) and not rebuild:
        z = np.load(cache)
        return z["stack"], z["vts"]

    def _pool(frame):
        g = frame.max(axis=2)                           # brightest channel
        h, w = g.shape
        gh, gw = h // DOWNSCALE, w // DOWNSCALE
        g = g[:gh * DOWNSCALE, :gw * DOWNSCALE]
        return g.reshape(gh, DOWNSCALE, gw, DOWNSCALE).max(axis=(1, 3))

    dec = H264Decoder()
    small, vts = [], []
    t0 = time.time()
    idx = os.path.join(session, "video_index.csv")
    with open(idx, newline="") as f, \
         open(os.path.join(session, "video.h264"), "rb") as fv:
        for row in csv.DictReader(f):
            data = fv.read(int(row["nbytes"]))
            kf = row["keyframe"] == "1"
            for frame, fts in dec.feed(data, kf, float(row["ts"])):
                small.append(_pool(frame).astype(np.uint8))
                vts.append(fts)
        for frame, fts in dec.flush():
            small.append(_pool(frame).astype(np.uint8))
            vts.append(fts)

    stack = np.asarray(small, dtype=np.uint8)
    vts = np.asarray(vts, dtype=np.float64)
    np.savez(cache, stack=stack, vts=vts)
    print("  decoded %d frames in %.1fs (cached)" % (len(vts), time.time() - t0))
    return stack, vts


def _detrend(sig, fps, window_s=4.0):
    """Remove slow baseline (exposure drift, constant brightness) via
    rolling-mean subtraction. Leaves only fast transients like LED blinks.
    Window of ~4 s >> blink duration (50 ms) so the blink itself is preserved.
    """
    w = max(3, int(round(fps * window_s)) | 1)          # odd length
    kernel = np.ones(w, dtype=np.float64) / w
    slow = np.convolve(sig, kernel, mode="same")
    return sig - slow


def _locate_led(stack, vts_c, marker_times_c, chunk=256):
    """Block whose *detrended* brightness best correlates with EEG markers.

    Detrending (subtract ~4 s rolling mean) removes always-saturated
    background and slow camera auto-exposure drift; only fast transients (LED
    blinks) survive. Correlating against the EEG marker train then reliably
    finds even a faint LED.

    Processes blocks in column-chunks so memory stays bounded regardless of
    recording length (a 2 h recording at 30 fps would otherwise need ~15 GB).

    Returns (detrended_signal[N], (row, col), corr).
    """
    n, h, w = stack.shape
    fps = n / float(vts_c[-1] - vts_c[0])
    win = max(3, int(round(fps * 4.0)) | 1)
    kernel = np.ones(win, dtype=np.float32) / win

    # Build zero-mean boxcar template from EEG marker times.
    tmpl = np.zeros(n, dtype=np.float32)
    for t in marker_times_c:
        tmpl[(vts_c >= t - CORR_WIN) & (vts_c <= t + CORR_WIN)] = 1.0
    tmpl -= tmpl.mean()
    tnorm = float(np.sqrt((tmpl * tmpl).sum())) or 1.0

    P = h * w
    flat = stack.reshape(n, P)                              # uint8 view
    num = np.zeros(P, dtype=np.float64)
    sumsq = np.zeros(P, dtype=np.float64)

    for c0 in range(0, P, chunk):
        c1 = min(c0 + chunk, P)
        x = flat[:, c0:c1].astype(np.float32)               # (N, C)
        slow = np.apply_along_axis(
            lambda col: np.convolve(col, kernel, mode="same"), 0, x)
        det = x - slow
        num[c0:c1] = tmpl @ det
        sumsq[c0:c1] = (det.astype(np.float64) ** 2).sum(axis=0)

    sig_norm = np.sqrt(np.maximum(sumsq, 1e-9))
    corr = num / (sig_norm * tnorm)

    b = int(np.argmax(corr))
    ry, rx = divmod(b, w)
    y0, y1 = max(ry - ROI_HALF, 0), ry + ROI_HALF + 1
    x0, x1 = max(rx - ROI_HALF, 0), rx + ROI_HALF + 1
    roi_raw = stack[:, y0:y1, x0:x1].max(axis=(1, 2)).astype(np.float64)
    roi_det = _detrend(roi_raw, fps)
    return roi_det, (ry * DOWNSCALE, rx * DOWNSCALE), float(corr[b])


def _rising_edges(level, ts, min_gap_s, thr):
    """Times of low->high crossings of ``thr`` in ``level``, debounced."""
    level = np.asarray(level, dtype=np.float64)
    hot = level > thr
    rising = np.flatnonzero((~hot[:-1]) & hot[1:]) + 1
    out, last = [], -np.inf
    for i in rising:
        if ts[i] - last >= min_gap_s:
            out.append(ts[i])
            last = ts[i]
    return np.asarray(out, dtype=np.float64)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Hardware-marker EEG/video sync.")
    ap.add_argument("session", help="Path to a session_* folder.")
    ap.add_argument("--min-gap", type=float, default=2.0,
                    help="Debounce: min seconds between markers (default 2).")
    ap.add_argument("--max-pair-dt", type=float, default=1.5,
                    help="Max |video-EEG| after coarse align to pair (s). "
                         "Bumped to 1.5 to survive >1h cumulative drift.")
    ap.add_argument("--rebuild", action="store_true",
                    help="Ignore the decode cache and re-decode the video.")
    a = ap.parse_args(argv if argv is not None else sys.argv[1:])

    s = a.session
    meta = json.load(open(os.path.join(s, "meta.json")))
    nch = int(meta["eeg_nch"])
    if "Events" not in meta["eeg_channels"]:
        print("No 'Events' channel in meta.json -- cannot use marker mode.")
        sys.exit(1)
    ev_idx = meta["eeg_channels"].index("Events")

    edata = np.fromfile(os.path.join(s, "eeg_samples.f32"),
                        dtype=np.float32).reshape(-1, nch)
    ets = np.fromfile(os.path.join(s, "eeg_ts.f64"), dtype=np.float64)
    m = min(len(edata), len(ets))
    ev = edata[:m, ev_idx].astype(np.float64)
    ets = ets[:m]

    print("Session: %s" % os.path.basename(os.path.normpath(s)))
    stack, vts = _decode_stack(s, rebuild=a.rebuild)

    # --- EEG markers: clean digital Events channel -----------------------
    ev_hi = ev.max()
    if ev_hi <= 0:
        print("Events channel never leaves 0 -- the marker is not reaching "
              "RIN1. Check wiring (common GND, Mini-DIN pin 3) and re-record.")
        sys.exit(1)
    ete_raw = _rising_edges(ev, ets, a.min_gap, ev_hi * 0.5)

    # --- map both trains onto the common PC clock ------------------------
    tc = _mean_tc(os.path.join(s, "clock.csv"))
    ete = ete_raw + tc["eeg"]
    vts_c = vts + tc["video"]
    vfps = len(vts) / (vts[-1] - vts[0])
    frame_ms = 1000.0 / vfps

    # --- locate the LED, then detect its flashes -------------------------
    sig, led, corr = _locate_led(stack, vts_c, ete)
    # Threshold on detrended signal: median + 4*MAD (robust, handles dim LED).
    med = float(np.median(sig))
    mad = float(np.median(np.abs(sig - med)))
    spread = 1.4826 * mad if mad > 0 else (float(sig.std()) or 1.0)
    vthr = med + 4.0 * spread
    vte = _rising_edges(sig, vts_c, a.min_gap, vthr)

    print("  EEG  Events pulses : %d  (level 0 -> %.0f)" % (ete_raw.size, ev_hi))
    print("  LED block          : (row=%d,col=%d), corr %.2f, "
          "detrended range %.1f..%.1f"
          % (led[0], led[1], corr, float(sig.min()), float(sig.max())))
    print("  video LED flashes  : %d  (thr %.1f)" % (vte.size, vthr))
    if corr < 0.03:
        print("  WARNING: very weak LED correlation (%.2f) -- the LED may not "
              "be in frame. Check the pairing count below." % corr)
    if ete_raw.size < 3 or vte.size < 3:
        print("Not enough markers detected (need >=3). Was the Pico firing "
              "and the LED clearly in frame?")
        sys.exit(1)

    # --- pair + fit (validated helpers) ----------------------------------
    seed = _seed_offset(vte, ete)
    pairs = _pair_events(vte, ete, seed, a.max_pair_dt)
    if len(pairs) < 3:
        print("Only %d marker pairs matched within %.0f ms (seed %+.1f ms)."
              % (len(pairs), a.max_pair_dt * 1e3, seed * 1e3))
        sys.exit(1)

    tv = np.array([p[0] for p in pairs])
    te = np.array([p[1] for p in pairs])
    off_ms = (tv - te) * 1000.0                 # +ve => video later than EEG
    rel_min = (tv - tv[0]) / 60.0
    slope, intercept, keep = _robust_linfit(rel_min, off_ms)
    fit_ms = slope * rel_min + intercept
    resid = off_ms - fit_ms
    n_kept = int(keep.sum())
    jitter = float(np.std(resid[keep])) if n_kept else float(np.std(resid))
    span = float(rel_min[-1] - rel_min[0])

    # Standard errors on the linear-fit parameters (OLS on the kept points).
    # SE(slope)     = sigma / sqrt(sum((x - xbar)^2))
    # SE(intercept) = sigma * sqrt(1/n + xbar^2 / sum((x - xbar)^2))
    if n_kept >= 3 and span > 0:
        xk = rel_min[keep]
        xbar = float(xk.mean())
        sxx = float(((xk - xbar) ** 2).sum())
        sigma = jitter
        slope_se = sigma / np.sqrt(max(sxx, 1e-12))
        intercept_se = sigma * np.sqrt(1.0 / n_kept + xbar * xbar / max(sxx, 1e-12))
        slope_ci95 = 1.96 * slope_se
        intercept_ci95 = 1.96 * intercept_se
    else:
        slope_se = intercept_se = slope_ci95 = intercept_ci95 = float("nan")

    print("\nEEG <-> video sync (offset = video - EEG, on the common clock):")
    print("  paired markers   : %d (rejected %d outliers), span %.1f min, "
          "~%.1f fps" % (n_kept, int((~keep).sum()), span, vfps))
    print("  fixed offset     : %+.1f +/- %.1f ms (95%% CI)   "
          "[constant -> post-hoc correctable]" % (intercept, intercept_ci95))
    print("  drift slope      : %+.3f +/- %.3f ms/min (95%% CI)  "
          "(= %+.1f ms over %.1f min)" % (slope, slope_ci95, slope * span, span))
    print("  residual jitter  : %.1f ms (1 sigma about the fit)" % jitter)
    print("  raw offset range : %+.1f .. %+.1f ms" % (off_ms.min(), off_ms.max()))
    print("  one video frame  : %.1f ms" % frame_ms)
    ok_fix = abs(intercept) <= 2 * frame_ms
    ok_jit = jitter <= frame_ms
    print("  %s: fixed offset %s ~1 frame; jitter %s 1 frame."
          % ("PASS" if (ok_fix and ok_jit) else "CHECK",
             "<=" if ok_fix else ">", "<=" if ok_jit else ">"))
    print("  -> drift slope is the uncorrected-amplifier-drift figure; report "
          "it (decides how urgent the C/C++ driver rewrite is).")

    # --- write thesis-ready data files ----------------------------------
    pairs_csv = os.path.join(s, "sync_pairs.csv")
    with open(pairs_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["idx", "t_common_s", "video_ts_s", "eeg_ts_s",
                    "offset_ms", "fit_ms", "residual_ms", "kept"])
        for i in range(len(pairs)):
            w.writerow([i, float(tv[i] - tv[0]), float(tv[i]), float(te[i]),
                        float(off_ms[i]), float(fit_ms[i]),
                        float(resid[i]), int(bool(keep[i]))])

    summary = {
        "session": os.path.basename(os.path.normpath(s)),
        "n_paired": int(len(pairs)),
        "n_kept": n_kept,
        "n_outliers": int((~keep).sum()),
        "span_min": float(span),
        "fps": float(vfps),
        "frame_ms": float(frame_ms),
        "fixed_offset_ms": float(intercept),
        "fixed_offset_ci95_ms": float(intercept_ci95),
        "drift_slope_ms_per_min": float(slope),
        "drift_slope_ci95_ms_per_min": float(slope_ci95),
        "drift_total_ms": float(slope * span),
        "residual_jitter_ms": float(jitter),
        "offset_min_ms": float(off_ms.min()),
        "offset_max_ms": float(off_ms.max()),
        "led_block_row": int(led[0]),
        "led_block_col": int(led[1]),
        "led_correlation": float(corr),
        "events_channel_index": int(ev_idx),
        "events_pulse_count": int(ete_raw.size),
        "video_flash_count": int(vte.size),
    }
    with open(os.path.join(s, "sync_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print("\nWrote sync_pairs.csv and sync_summary.json (thesis-ready data).")


if __name__ == "__main__":
    main()
