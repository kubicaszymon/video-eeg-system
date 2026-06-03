"""Generate publication-ready plots from a marker_sync_check.py session.

Reads the ``sync_pairs.csv`` + ``sync_summary.json`` produced by
``marker_sync_check.py`` and writes three PNG figures into the session folder,
ready to insert into a thesis:

1. **offset_vs_time.png**       — the main figure: per-marker EEG<->video
                                  offset vs time, with the linear fit and
                                  95 %% prediction band overlaid. Shows the
                                  fixed offset + drift slope at a glance.
2. **residual_histogram.png**   — distribution of the per-marker residuals
                                  about the linear fit, with mean/std and a
                                  Gaussian overlay. Demonstrates the jitter
                                  is well-behaved (~normal) and sub-frame.
3. **residuals_vs_time.png**    — residuals vs time, to visually rule out
                                  remaining structure (a flat scatter -> the
                                  linear model captures the drift).

Run (PC)::

    .venv-pc\\Scripts\\python pc_examples\\plot_sync_results.py recordings\\session_YYYYmmdd-HHMMSS
"""

import argparse
import csv
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")               # no display required
import matplotlib.pyplot as plt
import numpy as np


# Thesis-friendly defaults. Single source of truth for figure styling so all
# panels match.
plt.rcParams.update({
    "figure.dpi": 120,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "font.family": "DejaVu Sans",
    "font.size": 11,
    "axes.labelsize": 12,
    "axes.titlesize": 13,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linestyle": "--",
    "legend.frameon": False,
})

COLOR_DATA  = "#2E75B6"     # measurements
COLOR_FIT   = "#C00000"     # linear fit
COLOR_BAND  = "#C00000"     # 95% band (same hue, alpha)
COLOR_HIST  = "#2E75B6"
COLOR_GAUSS = "#C00000"


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


def _annotate_box(ax, text, loc="upper right"):
    """Place a multi-line value summary in the corner of an axes."""
    ax.text(0.98 if "right" in loc else 0.02,
            0.97 if "upper" in loc else 0.03, text,
            transform=ax.transAxes,
            ha="right" if "right" in loc else "left",
            va="top"   if "upper" in loc else "bottom",
            fontsize=10,
            bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                      edgecolor="0.6", linewidth=0.8, alpha=0.95))


def plot_offset_vs_time(session, t_min, off, fit, resid, kept, summary):
    fig, ax = plt.subplots(figsize=(7.5, 4.5))

    # Data points: outliers as hollow circles
    ax.scatter(t_min[kept],  off[kept], s=18, color=COLOR_DATA,
               edgecolor="none", alpha=0.85, label="per-marker offset")
    if (~kept).any():
        ax.scatter(t_min[~kept], off[~kept], s=24, facecolor="none",
                   edgecolor=COLOR_DATA, linewidth=0.8, alpha=0.7,
                   label="rejected outlier")

    # Linear fit and 95% prediction band (jitter as +/- 1.96*sigma)
    jitter = float(summary["residual_jitter_ms"])
    order = np.argsort(t_min)
    ax.plot(t_min[order], fit[order], color=COLOR_FIT, lw=2,
            label="linear fit (offset = a + b · t)")
    ax.fill_between(t_min[order],
                    fit[order] - 1.96 * jitter,
                    fit[order] + 1.96 * jitter,
                    color=COLOR_BAND, alpha=0.12,
                    label="95 % prediction band")

    ax.set_xlabel("Time into recording (min)")
    ax.set_ylabel("Offset video − EEG (ms)")
    ax.set_title("EEG↔video synchronization offset over the recording")

    a  = summary["fixed_offset_ms"]
    a_e = summary["fixed_offset_ci95_ms"]
    b  = summary["drift_slope_ms_per_min"]
    b_e = summary["drift_slope_ci95_ms_per_min"]
    span = summary["span_min"]
    text = ("fixed offset  a = %+.1f ± %.1f ms (95 %% CI)\n"
            "drift slope   b = %+.3f ± %.3f ms/min (95 %% CI)\n"
            "residual jitter σ = %.1f ms (≈ %.2f frame at %.1f fps)\n"
            "paired markers   n = %d   over %.1f min"
            % (a, a_e, b, b_e, jitter, jitter / summary["frame_ms"],
               summary["fps"], summary["n_paired"], span))
    _annotate_box(ax, text, "lower left")

    ax.legend(loc="upper right", fontsize=9)
    out = os.path.join(session, "offset_vs_time.png")
    fig.savefig(out)
    plt.close(fig)
    return out


def plot_residual_histogram(session, resid, kept, summary):
    fig, ax = plt.subplots(figsize=(6.0, 4.0))
    r = resid[kept]
    mu, sd = float(np.mean(r)), float(np.std(r))

    nbin = max(20, int(np.sqrt(len(r))))
    n, bins, _ = ax.hist(r, bins=nbin, color=COLOR_HIST, alpha=0.75,
                         edgecolor="white", linewidth=0.5,
                         label="per-marker residual")

    # Gaussian overlay scaled to histogram area
    x = np.linspace(bins[0], bins[-1], 400)
    bin_w = bins[1] - bins[0]
    pdf = (1.0 / (sd * np.sqrt(2 * np.pi))
           * np.exp(-0.5 * ((x - mu) / sd) ** 2))
    ax.plot(x, pdf * len(r) * bin_w, color=COLOR_GAUSS, lw=2,
            label="N(μ, σ²) overlay")

    # Frame-period guide lines
    fp = float(summary["frame_ms"])
    for xv in (-fp, +fp):
        ax.axvline(xv, color="0.5", lw=1, linestyle=":")
    ax.axvline(0, color="0.3", lw=0.8)

    ax.set_xlabel("Residual (ms)  —  offset minus linear fit")
    ax.set_ylabel("Count")
    ax.set_title("Residual distribution after drift correction")

    text = ("μ = %+.2f ms   σ = %.2f ms\n"
            "n = %d markers\n"
            "1 video frame = %.1f ms  (vertical dotted)"
            % (mu, sd, int(kept.sum()), fp))
    _annotate_box(ax, text, "upper left")
    ax.legend(loc="upper right", fontsize=9)

    out = os.path.join(session, "residual_histogram.png")
    fig.savefig(out)
    plt.close(fig)
    return out


def plot_residuals_vs_time(session, t_min, resid, kept, summary):
    fig, ax = plt.subplots(figsize=(7.5, 3.5))
    ax.axhline(0, color="0.3", lw=0.8)
    jitter = float(summary["residual_jitter_ms"])
    ax.axhspan(-jitter, +jitter, color="0.85", alpha=0.6,
               label="±1 σ")
    ax.scatter(t_min[kept],  resid[kept], s=14, color=COLOR_DATA,
               edgecolor="none", alpha=0.85)
    if (~kept).any():
        ax.scatter(t_min[~kept], resid[~kept], s=20, facecolor="none",
                   edgecolor=COLOR_DATA, linewidth=0.8, alpha=0.7,
                   label="rejected outlier")
    ax.set_xlabel("Time into recording (min)")
    ax.set_ylabel("Residual (ms)")
    ax.set_title("Residuals over time (flat scatter ⇒ linear drift is the right model)")
    ax.legend(loc="upper right", fontsize=9)

    out = os.path.join(session, "residuals_vs_time.png")
    fig.savefig(out)
    plt.close(fig)
    return out


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

    paths = [
        plot_offset_vs_time(s, t_min, off, fit, resid, kept, summary),
        plot_residual_histogram(s, resid, kept, summary),
        plot_residuals_vs_time(s, t_min, resid, kept, summary),
    ]
    for p in paths:
        print("wrote", p)


if __name__ == "__main__":
    main()
