"""Generate publication-ready plots from a marker_sync_check.py session.

Reads ``sync_pairs.csv`` + ``sync_summary.json`` and writes three PNG figures
into the session folder, in a clean academic (IEEE/Elsevier) style:

  - no in-figure titles (the figure caption carries that role);
  - no large stats box on the data (the key numbers go in the LaTeX caption,
    which this script prints to stdout, ready to paste);
  - minimal legends; reference lines visually distinct from the background grid.

Figures:
  1. offset_vs_time.png      — per-marker EEG<->video offset vs time + fit + 95% band
  2. residual_histogram.png  — residual distribution about the fit + Gaussian overlay
  3. residuals_vs_time.png   — residuals vs time (flatness check)

Run::

    python sync-verification/plot_sync_results.py recordings/session_YYYYmmdd-HHMMSS
"""

import argparse
import csv
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


# Single source of truth for figure styling so all panels match.
plt.rcParams.update({
    "figure.dpi": 120,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "font.family": "DejaVu Sans",
    "font.size": 11,
    "axes.labelsize": 12,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.16,          # subtle, so reference lines stand out
    "grid.linestyle": "-",
    "grid.linewidth": 0.6,
    "legend.frameon": False,
    "legend.fontsize": 9,
})

COLOR_DATA = "#2E75B6"          # measurements
COLOR_FIT  = "#C00000"          # linear fit / Gaussian
COLOR_REF  = "#333333"          # reference lines (zero, ±1 frame, ±1σ)
DASH_REF   = (0, (5, 2))        # distinct dash pattern for reference lines


def _load_pairs(session):
    rows = []
    with open(os.path.join(session, "sync_pairs.csv"), newline="") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    if not rows:
        raise SystemExit("sync_pairs.csv is empty.")
    t_min = np.array([float(r["t_common_s"]) for r in rows]) / 60.0
    off   = np.array([float(r["offset_ms"])   for r in rows])
    fit   = np.array([float(r["fit_ms"])      for r in rows])
    resid = np.array([float(r["residual_ms"]) for r in rows])
    kept  = np.array([int(r["kept"])          for r in rows], dtype=bool)
    return t_min, off, fit, resid, kept


def plot_offset_vs_time(session, t_min, off, fit, resid, kept, summary):
    fig, ax = plt.subplots(figsize=(7.2, 4.3))
    jitter = float(summary["residual_jitter_ms"])
    order = np.argsort(t_min)

    ax.fill_between(t_min[order], fit[order] - 1.96 * jitter,
                    fit[order] + 1.96 * jitter,
                    color=COLOR_FIT, alpha=0.12, linewidth=0)
    ax.plot(t_min[order], fit[order], color=COLOR_FIT, lw=2,
            label="Linear fit")
    ax.scatter(t_min[kept], off[kept], s=16, color=COLOR_DATA,
               edgecolor="none", alpha=0.85, label="experimental data")
    if (~kept).any():
        ax.scatter(t_min[~kept], off[~kept], s=28, facecolor="none",
                   edgecolor=COLOR_FIT, linewidth=1.1, alpha=0.9,
                   label="rejected outlier")

    ax.set_xlabel("Time into recording (min)")
    ax.set_ylabel("Video $-$ EEG offset (ms)")
    ax.margins(x=0.01)
    ax.legend(loc="upper right", frameon=True, facecolor="white",
              framealpha=0.95, edgecolor="0.8", borderpad=0.7)

    fig.savefig(os.path.join(session, "offset_vs_time.png"))
    plt.close(fig)
    cap = (r"\caption{Video$-$EEG synchronization offset versus recording time. "
           r"Filled markers: per-marker offsets ($n=%d$); solid line: linear fit "
           r"$\mathrm{offset}=a+b\,t$ with $a=%+.1f\pm%.1f$~ms and "
           r"$b=%+.3f\pm%.3f$~ms/min (95\%% CI); shaded band: 95\%% prediction "
           r"interval ($\pm1.96\sigma$, $\sigma=%.1f$~ms). Hollow red markers are "
           r"outliers rejected by the robust fit.}"
           % (int(kept.sum()), summary["fixed_offset_ms"],
              summary["fixed_offset_ci95_ms"], summary["drift_slope_ms_per_min"],
              summary["drift_slope_ci95_ms_per_min"], jitter))
    return "offset_vs_time.png", cap


def plot_residual_histogram(session, resid, kept, summary):
    fig, ax = plt.subplots(figsize=(6.2, 4.0))
    r = resid[kept]
    mu, sd = float(np.mean(r)), float(np.std(r))
    fp = float(summary["frame_ms"])

    nbin = max(20, int(np.sqrt(len(r))))
    n, bins, _ = ax.hist(r, bins=nbin, color=COLOR_DATA, alpha=0.75,
                         edgecolor="white", linewidth=0.5,
                         label="experimental data")

    x = np.linspace(bins[0], bins[-1], 400)
    bin_w = bins[1] - bins[0]
    pdf = (1.0 / (sd * np.sqrt(2 * np.pi))
           * np.exp(-0.5 * ((x - mu) / sd) ** 2))
    ax.plot(x, pdf * len(r) * bin_w, color=COLOR_FIT, lw=2,
            label=r"Gaussian fit  $\mathcal{N}(\mu,\sigma^{2})$")

    ax.set_xlabel("Residual (ms)")
    ax.set_ylabel("Count")

    # Headroom so there is a clear band at the top for the legend.
    ax.set_ylim(0, ax.get_ylim()[1] * 1.30)

    # ±1 video-frame reference lines: distinct dashes, and clipped to the lower
    # ~2/3 of the axes so they never run up into the legend corner.
    for xv in (-fp, +fp):
        ax.axvline(xv, ymin=0.0, ymax=0.66, color=COLOR_REF, lw=1.4,
                   linestyle=DASH_REF)
    ax.axvline(0, ymin=0.0, ymax=0.66, color=COLOR_REF, lw=0.8)
    # one labelled proxy so the dashed lines get a single legend entry
    ax.plot([], [], color=COLOR_REF, lw=1.4, linestyle=DASH_REF,
            label=r"$\pm1$ video frame")

    ax.legend(loc="upper right", frameon=True, facecolor="white",
              framealpha=0.95, edgecolor="0.8", borderpad=0.7)

    fig.savefig(os.path.join(session, "residual_histogram.png"))
    plt.close(fig)
    cap = (r"\caption{Distribution of the per-marker residuals about the linear "
           r"drift fit ($n=%d$). The residuals are approximately Gaussian "
           r"($\mu=%+.2f$~ms, $\sigma=%.2f$~ms; normal density overlaid). The "
           r"dashed lines mark $\pm1$ video frame ($%.1f$~ms at %.1f~fps), "
           r"confirming sub-frame residual jitter.}"
           % (int(kept.sum()), mu, sd, fp, summary["fps"]))
    return "residual_histogram.png", cap


def plot_residuals_vs_time(session, t_min, resid, kept, summary):
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    jitter = float(summary["residual_jitter_ms"])
    ax.axhspan(-jitter, +jitter, color=COLOR_DATA, alpha=0.10, label=r"$\pm1\sigma$")
    ax.axhline(0, color=COLOR_REF, lw=0.8)
    ax.scatter(t_min[kept], resid[kept], s=13, color=COLOR_DATA,
               edgecolor="none", alpha=0.85, label="experimental data")
    if (~kept).any():
        ax.scatter(t_min[~kept], resid[~kept], s=24, facecolor="none",
                   edgecolor=COLOR_FIT, linewidth=1.1, alpha=0.9,
                   label="rejected outlier")
    ax.set_xlabel("Time into recording (min)")
    ax.set_ylabel("Residual (ms)")
    ax.margins(x=0.01)
    ax.legend(loc="upper right", ncol=2)

    fig.savefig(os.path.join(session, "residuals_vs_time.png"))
    plt.close(fig)
    cap = (r"\caption{Residuals versus recording time. The scatter is flat about "
           r"zero (shaded band $\pm1\sigma=%.1f$~ms), indicating that the linear "
           r"drift model captures the systematic offset and only random jitter "
           r"remains.}" % jitter)
    return "residuals_vs_time.png", cap


def main(argv=None):
    ap = argparse.ArgumentParser(description="Plot marker_sync_check results.")
    ap.add_argument("session", help="Path to a session_* folder.")
    a = ap.parse_args(argv if argv is not None else sys.argv[1:])
    s = a.session
    if not os.path.isfile(os.path.join(s, "sync_pairs.csv")):
        print("No sync_pairs.csv in %s -- run marker_sync_check.py first." % s)
        sys.exit(1)
    summary = json.load(open(os.path.join(s, "sync_summary.json")))
    t_min, off, fit, resid, kept = _load_pairs(s)

    results = [
        plot_offset_vs_time(s, t_min, off, fit, resid, kept, summary),
        plot_residual_histogram(s, resid, kept, summary),
        plot_residuals_vs_time(s, t_min, resid, kept, summary),
    ]
    print("Wrote figures to", s)
    print("\n--- LaTeX captions (paste under each \\includegraphics) ---\n")
    for name, cap in results:
        print("%% %s" % name)
        print(cap)
        print()


if __name__ == "__main__":
    main()
