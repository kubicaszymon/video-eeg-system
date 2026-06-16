"""Methods-illustration figure: the hardware sync marker in BOTH streams.

(a) the clean EEG `Events` digital marker train (the EEG side of the marker);
(b) a schematic of one *validated* pulse pair from marker_sync_check.py's output
    (`sync_pairs.csv`): the EEG marker and the detected video-LED flash on the
    common LSL clock, with the measured constant offset between them. The offset
    value is the real per-pair number; the LED's faint raw brightness (recorded
    correlation ~0.05) is intentionally not plotted raw — its successful
    detection across the whole run is what `offset_vs_time.png` already shows.

    python sync-verification/plot_marker_overlay.py recordings/session_YYYYmmdd-HHMMSS \
        [--start 120] [--dur 27] [--out <dir>]
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
    "axes.labelsize": 12, "axes.titlesize": 12,
    "axes.spines.top": False, "axes.spines.right": False,
    "legend.frameon": False,
})
C_EEG = "#2E75B6"
C_LED = "#C00000"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session")
    ap.add_argument("--start", type=float, default=120.0)
    ap.add_argument("--dur", type=float, default=27.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    s = args.session
    out = args.out or os.path.join("sync-verification", "results")
    os.makedirs(out, exist_ok=True)

    meta = json.load(open(os.path.join(s, "meta.json")))
    nch = int(meta["eeg_nch"])
    sm = json.load(open(os.path.join(s, "sync_summary.json")))
    ev_idx = int(sm["events_channel_index"])
    jit = float(sm["residual_jitter_ms"])

    ets = np.fromfile(os.path.join(s, "eeg_ts.f64"), dtype="<f8")
    N = ets.size
    eeg = np.memmap(os.path.join(s, "eeg_samples.f32"), dtype="<f4", mode="r", shape=(N, nch))
    events = np.asarray(eeg[:, ev_idx], dtype=np.float64)

    rows = [r for r in csv.DictReader(open(os.path.join(s, "sync_pairs.csv")))
            if r.get("kept", "1") == "1"]
    t_common = np.array([float(r["t_common_s"]) for r in rows])
    off_ms = np.array([float(r["offset_ms"]) for r in rows])
    j = int(np.argmin(np.abs(t_common - args.start)))
    dms = off_ms[j]

    fig, (ax_a, ax_b) = plt.subplots(2, 1, figsize=(8.4, 6.2),
                                     constrained_layout=True)

    # --- (a) clean EEG Events train over a short window ---
    t0 = ets[0] + args.start
    m = (ets >= t0) & (ets <= t0 + args.dur)
    ax_a.plot(ets[m] - t0, events[m], color=C_EEG, lw=1.3)
    ax_a.set_xlim(0, args.dur)
    ax_a.set_ylim(bottom=-0.3)
    ax_a.set_xlabel("time on common LSL clock (s)")
    ax_a.set_ylabel("EEG Events\n(amplitude)")
    ax_a.set_title("(a) EEG sync pulses")

    # --- (b) one validated pulse pair, offset annotated (schematic) ---
    ax_b.set_ylim(0, 1.35)
    ax_b.vlines(0, 0, 1, color=C_EEG, lw=3.0, label="EEG marker (Events pulse)")
    ax_b.vlines(dms, 0, 1, color=C_LED, lw=3.0, label="video LED flash (detected)")
    ax_b.annotate("", xy=(dms, 0.5), xytext=(0, 0.5),
                  arrowprops=dict(arrowstyle="<->", color="#444444", lw=1.5))
    ax_b.text(dms / 2.0, 0.58, f"offset = {dms:+.0f} ms",
              ha="center", fontsize=10, color="#333333")
    lo = min(dms, 0) - 120
    ax_b.set_xlim(lo, max(0, dms) + 220)
    ax_b.set_yticks([])
    ax_b.spines["left"].set_visible(False)
    ax_b.set_xlabel("time relative to EEG marker (ms)")
    ax_b.set_title("(b) Single marker pair")
    ax_b.legend(loc="upper right", fontsize=9)
    p = os.path.join(out, "marker_overlay.png")
    fig.savefig(p); plt.close(fig)
    print("wrote", p)
    print(f"  representative pair at t_common={t_common[j]:.1f}s, offset {dms:+.0f} ms, "
          f"jitter {jit:.1f} ms")


if __name__ == "__main__":
    main()
