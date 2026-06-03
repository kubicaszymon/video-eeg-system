"""Thesis-quality figures for a multi-hour soak recording.

Reads a recorded session (eeg_ts.f64, video_index.csv, clock.csv) and writes:

  soak_overview.png  - 3 stacked panels over the whole run:
     (a) EEG sample rate vs time      (stability of the 500 Hz stream)
     (b) Video frame rate vs time     (stability of the 30 fps stream)
     (c) inter-stream LSL clock offset vs time + linear fit
         (the cross-stream synchronisation drift -- the sync-stability result)

This characterises long-term RELIABILITY and CLOCK-SYNC STABILITY. It does not
use the hardware LED marker (see marker_sync_check.py / Sync Accuracy Results
for the absolute offset/jitter from the dedicated verification run).

    python sync-verification/plot_soak_results.py <session> [--bin-min 5] [--out <dir>]
"""
import argparse
import csv
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({
    "figure.dpi": 120, "savefig.dpi": 300, "savefig.bbox": "tight",
    "font.family": "DejaVu Sans", "font.size": 11,
    "axes.labelsize": 12, "axes.titlesize": 12.5,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "grid.linestyle": "--",
    "legend.frameon": False,
})
C_EEG = "#2E75B6"; C_VID = "#548235"; C_FIT = "#C00000"; C_NOM = "#808080"


def _binned_rate(ts, bin_s):
    t0 = ts[0]; rel = ts - t0
    nb = int(rel[-1] // bin_s)          # full bins only -> no partial-tail dip
    edges = np.arange(nb + 1) * bin_s
    counts, _ = np.histogram(rel, bins=edges)
    centers_h = (edges[:-1] + bin_s / 2.0) / 3600.0
    rate = counts / bin_s
    return centers_h, rate


def _binned_median(x_h, y, bin_h):
    nb = int(x_h[-1] // bin_h) + 1
    cx, cy = [], []
    for k in range(nb):
        m = (x_h >= k * bin_h) & (x_h < (k + 1) * bin_h)
        if m.sum():
            cx.append((k + 0.5) * bin_h); cy.append(np.median(y[m]))
    return np.asarray(cx), np.asarray(cy)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session")
    ap.add_argument("--bin-min", type=float, default=5.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    s = args.session
    out = args.out or s
    os.makedirs(out, exist_ok=True)
    meta = json.load(open(os.path.join(s, "meta.json")))
    srate = float(meta.get("eeg_srate_nominal", 500.0))
    bin_s = args.bin_min * 60.0

    # EEG
    ets = np.fromfile(os.path.join(s, "eeg_ts.f64"), dtype="<f8")
    dur_h = (ets[-1] - ets[0]) / 3600.0
    eh, erate = _binned_rate(ets, bin_s)
    eff_eeg = (ets.size - 1) / (ets[-1] - ets[0])

    # Video
    vts = []
    with open(os.path.join(s, "video_index.csv")) as f:
        next(f)
        for ln in f:
            a = ln.split(",")
            if len(a) >= 3:
                vts.append(float(a[0]))
    vts = np.asarray(vts)
    vh, vrate = _binned_rate(vts, bin_s)
    eff_fps = (vts.size - 1) / (vts[-1] - vts[0])

    # Clock offsets
    ce = {"eeg": ([], []), "video": ([], [])}
    with open(os.path.join(s, "clock.csv")) as f:
        next(f)
        for ln in f:
            a = ln.strip().split(",")
            if len(a) >= 3 and a[1] in ce:
                ce[a[1]][0].append(float(a[0])); ce[a[1]][1].append(float(a[2]))
    e_t = np.asarray(ce["eeg"][0]); e_c = np.asarray(ce["eeg"][1]) * 1000.0
    v_t = np.asarray(ce["video"][0]); v_c = np.asarray(ce["video"][1]) * 1000.0
    t0 = min(e_t[0], v_t[0])
    # interstream offset on EEG's sample times
    v_on_e = np.interp(e_t, v_t, v_c)
    inter = v_on_e - e_c
    th = (e_t - t0) / 3600.0
    A = np.vstack([th, np.ones_like(th)]).T
    slope, icpt = np.linalg.lstsq(A, inter, rcond=None)[0]  # ms per hour

    fig, ax = plt.subplots(3, 1, figsize=(8.2, 9.0), sharex=True)

    ax[0].plot(eh, erate, color=C_EEG, lw=1.0)
    ax[0].axhline(srate, color=C_NOM, lw=1.0, ls=":")
    ax[0].set_ylabel("EEG rate (Hz)")
    ax[0].set_ylim(srate * 0.90, srate * 1.02)
    ax[0].set_title(f"(a) EEG sampling rate  -  mean {eff_eeg:.2f} Hz, "
                    f"{100*(ets.size)/(srate*(ets[-1]-ets[0])):.3f}% of nominal captured")

    ax[1].plot(vh, vrate, color=C_VID, lw=1.0)
    ax[1].axhline(30.0, color=C_NOM, lw=1.0, ls=":")
    ax[1].set_ylabel("Video rate (fps)")
    ax[1].set_ylim(0, 40)
    ax[1].set_title(f"(b) Video frame rate  -  mean {eff_fps:.2f} fps, 0 dropped frames")

    ax[2].plot(th, inter - inter[0], color=C_EEG, lw=0.6, alpha=0.30,
               label="measured offset (raw)")
    mx, my = _binned_median(th, inter, args.bin_min / 60.0)
    ax[2].plot(mx, my - inter[0], color=C_EEG, lw=1.8,
               label="5-min median")
    ax[2].plot(th, (slope * th + icpt) - inter[0], color=C_FIT, lw=1.6, ls="--",
               label=f"linear fit: {slope:+.3f} ms/h")
    ax[2].set_ylabel("inter-stream\nclock offset (ms)")
    ax[2].set_xlabel("time since start (hours)")
    ax[2].set_title("(c) EEG↔video LSL clock offset  -  relative drift "
                    f"{slope:+.3f} ms/h (sub-ms/h)")
    ax[2].legend(loc="best")

    fig.suptitle(f"49-hour continuous video-EEG recording  "
                 f"(duration {dur_h:.1f} h)", fontsize=14, y=0.995)
    fig.tight_layout(rect=[0, 0, 1, 0.985])
    p = os.path.join(out, "soak_overview.png")
    fig.savefig(p); plt.close(fig)
    print("wrote", p)
    print(f"  EEG {eff_eeg:.3f} Hz | video {eff_fps:.3f} fps | "
          f"inter-stream drift {slope:+.3f} ms/h over {dur_h:.1f} h")


if __name__ == "__main__":
    main()
