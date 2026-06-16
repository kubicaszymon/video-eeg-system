"""Re-vectorise an existing soak_overview.png whose source session is gone.

The original 3-panel figure (plot_soak_results.py) was only kept as a 300-dpi
PNG and the recording it was made from is no longer on disk. Inkscape autotrace
is useless on it (it traces every antialiased pixel). Instead this script
*digitises the plotted curves straight out of the raster* and re-draws them with
the original figure's matplotlib styling, producing a genuine vector file
(crisp text, real line paths):

    soak_overview.svg
    soak_overview.pdf

Fidelity: panels (a)/(b) and panel (c)'s 5-min median + linear fit are recovered
faithfully; panel (c)'s light raw-offset cloud is reconstructed as a per-column
envelope (shape matches, individual samples are approximate). The axes, ticks,
labels, titles, nominal lines and legend are NOT traced -- they are redrawn from
the original code, so they are pixel-clean.

    python sync-verification/vectorize_soak_overview.py \
        [--png results/soak_overview.png] [--out results]
"""
import argparse
import os

import numpy as np
from PIL import Image

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

# ---- styling identical to plot_soak_results.py -----------------------------
plt.rcParams.update({
    "figure.dpi": 120, "savefig.dpi": 300, "savefig.bbox": "tight",
    "font.family": "DejaVu Sans", "font.size": 11,
    "axes.labelsize": 12, "axes.titlesize": 12.5,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "grid.linestyle": "--",
    "legend.frameon": False,
})
C_EEG = (46, 117, 182)    # #2E75B6
C_VID = (84, 130, 53)     # #548235
C_FIT = (192, 0, 0)       # #C00000
H_EEG, H_VID, H_FIT = "#2E75B6", "#548235", "#C00000"
C_NOM = "#808080"

# ---- pixel <-> data calibration (from tick-mark detection) ------------------
PX_X0, H_X0 = 373.0, 0.0          # x px 373  -> 0 h
PX_X1, H_X1 = 2333.0, 50.0        # x px 2333 -> 50 h
A_TOP, A_BOT = 94.0, 798.0        # panel a: 510 Hz (row 94) .. 450 Hz (row 798)
A_VTOP, A_VBOT = 510.0, 450.0
B_TOP, B_BOT = 940.0, 1645.0      # panel b: 40 fps .. 0 fps
B_VTOP, B_VBOT = 40.0, 0.0
C_ZERO_PX, C_MS_PER_PX = 2111.0, 25.0 / 121.6   # panel c: px 2111 -> 0 ms
PANEL_A = (90, 799)
PANEL_B = (905, 1650)
PANEL_C = (1755, 2492)
PLOT_X = (300, 2392)              # columns inside the axes box


def x_to_h(px):
    return H_X0 + (px - PX_X0) * (H_X1 - H_X0) / (PX_X1 - PX_X0)


def y_to_a(py):
    return A_VBOT + (A_BOT - py) * (A_VTOP - A_VBOT) / (A_BOT - A_TOP)


def y_to_b(py):
    return B_VBOT + (B_BOT - py) * (B_VTOP - B_VBOT) / (B_BOT - B_TOP)


def y_to_c(py):
    return (C_ZERO_PX - py) * C_MS_PER_PX


def _dist(im, rgb):
    return (np.abs(im[:, :, 0] - rgb[0]) + np.abs(im[:, :, 1] - rgb[1])
            + np.abs(im[:, :, 2] - rgb[2]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--png", default="results/soak_overview.png")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    here = os.path.dirname(os.path.abspath(__file__))
    png = args.png if os.path.isabs(args.png) else os.path.join(here, args.png)
    out = args.out or os.path.dirname(png)
    os.makedirs(out, exist_ok=True)

    im = np.asarray(Image.open(png).convert("RGB")).astype(int)
    x0, x1 = PLOT_X
    cols = np.arange(x0, x1)

    eeg_d = _dist(im, C_EEG)
    vid_d = _dist(im, C_VID)
    fit_d = _dist(im, C_FIT)
    r, g, b = im[:, :, 0], im[:, :, 1], im[:, :, 2]
    bluish = (b - r > 15) & (b - g > 8) & (b > 150)   # raw cloud (alpha 0.30)
    # permissive blue for the thin, anti-aliased panel-a trace (the flat 500 Hz
    # line is a 1 px line largely hidden under the dotted nominal line, so the
    # strict colour-distance test misses it). Excludes the grey grid/nominal.
    blue_line = (b - r > 12) & (b - g > 8) & (b < 248) & (r < 215)

    # blank out the original legend (upper-right of panel c) so its colour
    # samples + text are not mistaken for data. No real curve enters this box
    # (after ~hour 31 the offset is flat near 0 ms, well below it).
    LGND_X = (1595, 2360)
    LGND_Y = (1750, 2010)
    for d in (eeg_d, vid_d, fit_d):
        d[LGND_Y[0]:LGND_Y[1], LGND_X[0]:LGND_X[1]] = 999
    bluish[LGND_Y[0]:LGND_Y[1], LGND_X[0]:LGND_X[1]] = False

    # ---- panel (a): EEG sampling rate (flat 500 Hz + reconnect dip) ----------
    ay0, ay1 = PANEL_A
    ah, arate = [], []
    for x in cols:
        rows = np.where(blue_line[ay0:ay1, x])[0]
        if rows.size >= 2:
            ah.append(x_to_h(x))
            arate.append(y_to_a(ay0 + rows.max()))   # lowest point -> keeps dip
    ah, arate = np.asarray(ah), np.asarray(arate)

    # ---- panel (b): video frame rate (flat 30 fps) ---------------------------
    by0, by1 = PANEL_B
    bh, brate = [], []
    for x in cols:
        rows = np.where(vid_d[by0:by1, x] < 60)[0]
        if rows.size:
            bh.append(x_to_h(x))
            brate.append(y_to_b(by0 + rows.mean()))
    bh, brate = np.asarray(bh), np.asarray(brate)

    # ---- panel (c): inter-stream clock offset --------------------------------
    cy0, cy1 = PANEL_C
    raw_segs, mh, mval, fh, fval = [], [], [], [], []
    for x in cols:
        sl_eeg = eeg_d[cy0:cy1, x] < 55          # opaque median (solid blue)
        sl_blue = bluish[cy0:cy1, x]             # raw cloud (light blue)
        sl_fit = fit_d[cy0:cy1, x] < 70          # dashed red fit
        med = np.where(sl_eeg)[0]
        raw = np.where(sl_blue | sl_eeg)[0]      # median sits inside the cloud
        fit = np.where(sl_fit)[0]
        h = x_to_h(x)
        if raw.size:
            raw_segs.append([(h, y_to_c(cy0 + raw.max())),
                             (h, y_to_c(cy0 + raw.min()))])
        if med.size:
            mh.append(h); mval.append(y_to_c(cy0 + med.mean()))
        if fit.size:
            fh.append(h); fval.append(y_to_c(cy0 + fit.mean()))
    mh, mval = np.asarray(mh), np.asarray(mval)
    fh, fval = np.asarray(fh), np.asarray(fval)
    # the fit is a straight line by construction -> refit for a clean vector path
    if fh.size >= 2:
        s, i = np.polyfit(fh, fval, 1)
        fx = np.array([0.0, max(ah[-1] if ah.size else 49.0, fh[-1])])
        fy = s * fx + i

    # ---- redraw with the original styling ------------------------------------
    fig, ax = plt.subplots(3, 1, figsize=(8.2, 9.0), sharex=True)

    ax[0].plot(ah, arate, color=H_EEG, lw=1.0)
    ax[0].axhline(500.0, color=C_NOM, lw=1.0, ls=":")
    ax[0].set_ylabel("EEG rate (Hz)")
    ax[0].set_ylim(450.0, 510.0)
    ax[0].set_title("(a) EEG sampling rate")

    ax[1].plot(bh, brate, color=H_VID, lw=1.0)
    ax[1].axhline(30.0, color=C_NOM, lw=1.0, ls=":")
    ax[1].set_ylabel("Video rate (fps)")
    ax[1].set_ylim(0, 40)
    ax[1].set_title("(b) Video frame rate")

    ax[2].add_collection(LineCollection(raw_segs, colors=H_EEG, linewidths=0.6,
                                        alpha=0.30, label="measured offset (raw)"))
    ax[2].plot(mh, mval, color=H_EEG, lw=1.8, label="5-min median")
    if fh.size >= 2:
        ax[2].plot(fx, fy, color=H_FIT, lw=1.6, ls="--", label="linear fit")
    ax[2].set_ylabel("inter-stream\nclock offset (ms)")
    ax[2].set_xlabel("Time since start (h)")
    ax[2].set_title("(c) Inter-stream clock offset")
    ax[2].set_ylim(-75, 60)
    ax[2].legend(loc="upper right", frameon=False)
    ax[2].autoscale_view()

    fig.tight_layout()
    for ext in ("svg", "pdf", "png"):
        p = os.path.join(out, f"soak_overview_vector.{ext}")
        fig.savefig(p)
        print("wrote", p)
    plt.close(fig)


if __name__ == "__main__":
    main()
