"""Verify and *characterize* EEG <-> video synchronization in an XDF file.

Requirement #2: prove EEG and video are frame-accurately aligned in a
recording, and — over a long recording — measure how that alignment behaves
in time (the uncorrected EEG amplifier drift only shows up over hours).

Two modes (``--mode``, default ``auto``):

* ``single`` — the original one-shot check: the single brightest jump in
  the video (a torch flashed at the camera) vs the single biggest EEG
  deflection (an electrode tapped at the same instant). Good for a first
  sanity pass. Correctly synced -> within ~1 frame (~33 ms @ 30 fps).
* ``drift``  — repeated-event characterization: a sync marker is fired
  periodically through the recording (LED in view + a pulse on a spare
  EEG/AUX input, ideally one hardware edge — see VIDEO_EEG_APP_SPEC.md §4).
  Every marker pair is detected, the per-event ``video - EEG`` offset is
  computed, and offset-vs-time is linearly fit:
    - **fixed offset (ms)** = fit value at the start (post-hoc correctable),
    - **drift slope (ms/min)** = the uncorrected-EEG-drift result,
    - **residual jitter (ms)** = scatter about the fit.
  ``auto`` picks ``drift`` when >=3 marker pairs are found, else ``single``.

Also cross-checks the pyxdf clock-corrected timeline against the
*un*synchronized load so LSL-clock-sync error can be told apart from
amplifier drift.

Run (PC)::

    .venv-pc\\Scripts\\pip install pyxdf numpy av
    .venv-pc\\Scripts\\python pc_examples\\xdf_sync_check.py path\\to\\rec.xdf
    .venv-pc\\Scripts\\python pc_examples\\xdf_sync_check.py rec.xdf --mode drift
"""

import argparse
import base64
import os
import sys

import numpy as np
import pyxdf

# H264Decoder lives in ../pc-tools (one decode path for live + offline).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pc-tools"))
from h264_inlet import H264Decoder  # noqa: E402


def _pick(streams, want_type, want_name):
    for s in streams:
        if want_name and s["info"]["name"][0] == want_name:
            return s
    for s in streams:
        if s["info"]["type"][0].lower() == want_type:
            return s
    return None


def _decode_video(vid):
    """Return (brightness[N], timestamps[N]) for every decoded frame."""
    dec = H264Decoder()
    series = vid["time_series"]
    stamps = np.asarray(vid["time_stamps"], dtype=np.float64)
    bright, vts = [], []
    for smp, ts in zip(series, stamps):
        data = base64.b64decode(smp[0])
        keyframe = str(smp[1]) == "1"
        for frame, fts in dec.feed(data, keyframe, ts):
            bright.append(float(frame.mean()))
            vts.append(fts)
    for frame, fts in dec.flush():
        bright.append(float(frame.mean()))
        vts.append(fts)
    return np.asarray(bright), np.asarray(vts, dtype=np.float64)


def _detect_event_times(level, ts, min_gap_s, k=6.0):
    """Rising edges of a sustained excursion above a robust baseline.

    ``level`` is a non-negative "how far from rest" signal (video: frame
    brightness; EEG: max abs deviation across channels). A marker (flash /
    injected pulse) makes it jump high and stay high for a few samples, then
    return -> exactly one rising edge per marker. Robust (median + MAD)
    thresholding so it is not thrown off by a few large artifacts; a
    ``min_gap_s`` debounce stops one physical event registering twice.
    """
    level = np.asarray(level, dtype=np.float64)
    ts = np.asarray(ts, dtype=np.float64)
    if level.size < 2:
        return np.empty(0)
    med = np.median(level)
    mad = np.median(np.abs(level - med))
    spread = 1.4826 * mad if mad > 0 else (np.std(level) or 1.0)
    thr = med + k * spread
    hot = level > thr
    rising = np.flatnonzero((~hot[:-1]) & hot[1:]) + 1
    out = []
    last = -np.inf
    for i in rising:
        t = ts[i]
        if t - last >= min_gap_s:
            out.append(t)
            last = t
    return np.asarray(out, dtype=np.float64)


def _pair_events(vte, ete, seed_offset, max_pair_dt):
    """Nearest-neighbour pair video events to EEG events.

    ``seed_offset`` (~ video_ts - eeg_ts) coarsely aligns the two trains so
    a missed detection in one stream does not shift every later pairing
    (index pairing would). Each EEG event is used at most once.
    """
    pairs = []
    used = np.zeros(ete.size, dtype=bool)
    for tv in vte:
        cand = tv - seed_offset            # expected matching EEG time
        if ete.size == 0:
            break
        j = int(np.argmin(np.abs(ete - cand)))
        if not used[j] and abs(ete[j] - cand) <= max_pair_dt:
            used[j] = True
            pairs.append((tv, ete[j]))
    return pairs


def _seed_offset(vte, ete):
    """Coarse global offset from the most isolated/strongest pair: use the
    median of every video-event's nearest raw EEG-event difference."""
    if vte.size == 0 or ete.size == 0:
        return 0.0
    diffs = [vt - ete[int(np.argmin(np.abs(ete - vt)))] for vt in vte]
    return float(np.median(diffs))


def _robust_linfit(x, y, n_sigma=3.0, iters=2):
    """polyfit deg-1 with simple residual-outlier rejection. Returns
    (slope, intercept, kept_mask)."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    keep = np.ones(x.size, dtype=bool)
    slope = intercept = 0.0
    for _ in range(iters + 1):
        if keep.sum() < 2:
            break
        slope, intercept = np.polyfit(x[keep], y[keep], 1)
        resid = y - (slope * x + intercept)
        s = np.std(resid[keep])
        if s == 0:
            break
        new_keep = np.abs(resid) <= n_sigma * s
        if new_keep.sum() == keep.sum():
            keep = new_keep
            break
        keep = new_keep
    return slope, intercept, keep


def _single_event(eeg, vid, ets, edata, bright, vts, vfps):
    print("\nShared-event test (torch flash + electrode tap, same instant):")
    vi = int(np.argmax(np.diff(bright))) + 1     # brightness jumps up
    t_flash = vts[vi]
    de = np.max(np.abs(np.diff(edata, axis=0)), axis=1)
    ei = int(np.argmax(de)) + 1
    t_tap = ets[ei]
    dt_ms = (t_flash - t_tap) * 1000.0
    frame_ms = 1000.0 / vfps
    print("  video flash  @ t = %.4f s (frame %d)" % (t_flash, vi))
    print("  EEG artifact @ t = %.4f s (sample %d)" % (t_tap, ei))
    print("  offset video-EEG = %+.1f ms" % dt_ms)
    if abs(dt_ms) <= 2 * frame_ms:
        print("  PASS: within ~%.0f ms (about one frame). Synced." % frame_ms)
    else:
        print("  CHECK: > ~2 frames. Make sure the flash and the tap were "
              "truly simultaneous and the largest events in the file.")

    mid = len(vts) // 2
    j = min(max(int(np.searchsorted(ets, vts[mid])), 0), len(ets) - 1)
    print("\nSpot check: mid video frame t=%.4f <-> nearest EEG sample "
          "t=%.4f, gap %.2f ms"
          % (vts[mid], ets[j], (ets[j] - vts[mid]) * 1000.0))


def _drift(ets, edata, bright, vts, vfps, args):
    frame_ms = 1000.0 / vfps
    eeg_level = np.max(np.abs(edata - np.median(edata, axis=0)), axis=1)
    vte = _detect_event_times(bright, vts, args.min_gap, args.k)
    ete = _detect_event_times(eeg_level, ets, args.min_gap, args.k)
    print("\nDrift characterization:")
    print("  detected markers: video=%d, EEG=%d (min gap %.1fs, k=%.1f)"
          % (vte.size, ete.size, args.min_gap, args.k))
    if vte.size < 3 or ete.size < 3:
        print("  Not enough markers for a drift fit (need >=3 paired). Fire "
              "the sync marker periodically, or use --mode single.")
        return False

    seed = _seed_offset(vte, ete)
    pairs = _pair_events(vte, ete, seed, args.max_pair_dt)
    if len(pairs) < 3:
        print("  Only %d marker pairs matched within %.0f ms — check the "
              "marker is clear in BOTH streams." % (len(pairs),
                                                    args.max_pair_dt * 1000))
        return False

    tv = np.array([p[0] for p in pairs], dtype=np.float64)
    te = np.array([p[1] for p in pairs], dtype=np.float64)
    off_ms = (tv - te) * 1000.0
    t0 = tv[0]
    rel_min = (tv - t0) / 60.0                    # minutes into the recording

    slope, intercept, keep = _robust_linfit(rel_min, off_ms)
    resid = off_ms - (slope * rel_min + intercept)
    jitter = float(np.std(resid[keep])) if keep.sum() else float(np.std(resid))
    span_min = float(rel_min[-1] - rel_min[0])
    total_drift = slope * span_min

    print("  paired markers used: %d (rejected %d as outliers), span %.1f min"
          % (int(keep.sum()), int((~keep).sum()), span_min))
    print("  fixed offset (start) = %+.1f ms   [post-hoc correctable]"
          % intercept)
    print("  drift slope          = %+.3f ms/min  (= %+.1f ms over %.1f min)"
          % (slope, total_drift, span_min))
    print("  residual jitter      = %.1f ms (1 sigma about the fit)" % jitter)
    print("  raw offset range     = %+.1f .. %+.1f ms"
          % (off_ms.min(), off_ms.max()))

    ok_fixed = abs(intercept) <= 2 * frame_ms
    ok_jit = jitter <= frame_ms
    verdict = "PASS" if (ok_fixed and ok_jit) else "CHECK"
    print("  %s: fixed offset %s ~1 frame (%.0f ms); jitter %s 1 frame."
          % (verdict,
             "<=" if ok_fixed else ">", frame_ms,
             "<=" if ok_jit else ">"))
    print("  -> The drift slope is the uncorrected-EEG-amplifier-drift "
          "result. Report it; its size decides how urgently the C/C++ "
          "driver rewrite is needed (see VIDEO_EEG_APP_SPEC.md).")
    return True


def _summaries(streams, tag):
    eeg = _pick(streams, "eeg", None)
    vid = _pick(streams, "video", None)
    if eeg is None or vid is None:
        return None
    ets = np.asarray(eeg["time_stamps"], dtype=np.float64)
    vts = np.asarray(vid["time_stamps"], dtype=np.float64)
    if ets.size >= 2 and vts.size >= 2:
        print("  [%s] EEG span %.1fs (~%.2f Hz), Video span %.1fs"
              % (tag, ets[-1] - ets[0], ets.size / (ets[-1] - ets[0]),
                 vts[-1] - vts[0]))
    return eeg, vid


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check/characterize EEG-video "
                                             "sync in an XDF.")
    ap.add_argument("xdf", help="Path to the LabRecorder .xdf file.")
    ap.add_argument("--eeg-name", default="Perun32")
    ap.add_argument("--video-name", default="Perun32_Video")
    ap.add_argument("--mode", choices=("auto", "single", "drift"),
                    default="auto", help="Which test (default: auto).")
    ap.add_argument("--min-gap", type=float, default=2.0,
                    help="Min seconds between distinct markers (debounce).")
    ap.add_argument("--max-pair-dt", type=float, default=0.5,
                    help="Max |video-EEG| (after coarse align) to pair "
                         "two events, seconds (default 0.5).")
    ap.add_argument("--k", type=float, default=6.0,
                    help="Marker threshold = median + k*MAD (default 6).")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    # Fully corrected timeline (this is THE synchronization).
    streams, _ = pyxdf.load_xdf(args.xdf)
    eeg = _pick(streams, "eeg", args.eeg_name)
    vid = _pick(streams, "video", args.video_name)
    if eeg is None or vid is None:
        print("Need both an EEG and a Video stream. Found:",
              [(s["info"]["name"][0], s["info"]["type"][0]) for s in streams])
        sys.exit(1)

    ets = np.asarray(eeg["time_stamps"], dtype=np.float64)
    edata = np.asarray(eeg["time_series"], dtype=np.float64)
    bright, vts = _decode_video(vid)

    if len(vts) < 2 or len(ets) < 2:
        print("Not enough data decoded (video frames=%d, eeg samples=%d)."
              % (len(vts), len(ets)))
        sys.exit(1)

    vfps = len(vts) / (vts[-1] - vts[0])
    print("EEG   '%s': %d samples, %.1fs, ~%.1f Hz" % (
        eeg["info"]["name"][0], len(ets), ets[-1] - ets[0],
        len(ets) / (ets[-1] - ets[0])))
    print("Video '%s': %d frames decoded, %.1fs, ~%.1f fps" % (
        vid["info"]["name"][0], len(vts), vts[-1] - vts[0], vfps))
    overlap = min(ets[-1], vts[-1]) - max(ets[0], vts[0])
    print("Overlapping time on the shared LSL timeline: %.1f s" % overlap)

    mode = args.mode
    if mode == "auto":
        eeg_level = np.max(np.abs(edata - np.median(edata, axis=0)), axis=1)
        n_v = _detect_event_times(bright, vts, args.min_gap, args.k).size
        n_e = _detect_event_times(eeg_level, ets, args.min_gap, args.k).size
        mode = "drift" if (n_v >= 3 and n_e >= 3) else "single"
        print("auto -> %s mode (video markers=%d, EEG markers=%d)"
              % (mode, n_v, n_e))

    if mode == "single":
        _single_event(eeg, vid, ets, edata, bright, vts, vfps)
    else:
        _drift(ets, edata, bright, vts, vfps, args)

    # Cross-check: how much of the alignment comes from LSL clock sync vs
    # the amplifier itself. Load again WITHOUT clock synchronization and
    # report the EEG-vs-video start-offset difference.
    try:
        raw, _ = pyxdf.load_xdf(args.xdf, synchronize_clocks=False,
                                dejitter_timestamps=False)
        c = _summaries(streams, "clock-synced")
        r = _summaries(raw, "raw (no sync)")
        if c and r:
            de0 = (c[0]["time_stamps"][0] - c[1]["time_stamps"][0])
            de1 = (r[0]["time_stamps"][0] - r[1]["time_stamps"][0])
            print("  LSL clock-sync contribution to EEG-video start offset: "
                  "%+.1f ms" % ((de0 - de1) * 1000.0))
    except Exception as e:  # cross-check is informational only
        print("  (clock-sync cross-check skipped: %s)" % e)


if __name__ == "__main__":
    main()
