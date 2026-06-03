#!/usr/bin/env bash
# On-demand electrode-impedance check.
#
# Why a stop/start dance: the Perun32 can do EITHER clean EEG OR impedance
# (impedance mode injects a small current + filters the signal), and only
# one process can hold the USB device at a time. So we briefly stop the
# continuous EEG service, run an impedance pass that publishes its own
# short-lived LSL stream 'Perun32-Impedance', then resume EEG.
#
# Trigger it from the PC over SSH, e.g.:
#   ssh szymon@camera-pi.local '~/perun_lsl_driver/deploy/run_impedance.sh'
#   ssh szymon@camera-pi.local '~/perun_lsl_driver/deploy/run_impedance.sh 30'
#
# Arg 1 = impedance duration in seconds (default 25). Allow ~15 s minimum:
# the impedance averaging buffer needs time to fill before values are valid.
set -uo pipefail

# --- break-glass interlock: never run alongside the control daemon -------
# The normal way to do an impedance check is now  POST /impedance  to the
# control daemon. This SSH script is the fallback for when the daemon is
# down; refuse to run while it holds the USB device.
LOCK="$HOME/perun_lsl_driver/deploy/.control.lock"
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then
    echo "impedance: control daemon is running (pid $(cat "$LOCK"))." >&2
    echo "impedance: use the control API instead:" >&2
    echo "  curl -X POST localhost:8080/impedance -d '{\"duration\":45}'" >&2
    echo "or stop it first: systemctl --user stop perun-control.service" >&2
    exit 3
fi

DUR="${1:-25}"
cd "$HOME/perun_lsl_driver"
PY="$HOME/perun_lsl_driver/.venv/bin/python"

resume_eeg() {
    echo "impedance: resuming continuous EEG service" >&2
    systemctl --user start perun-eeg.service || true
}
# Guarantee EEG comes back even if anything below fails.
trap resume_eeg EXIT

echo "impedance: stopping continuous EEG service" >&2
systemctl --user stop perun-eeg.service || true

# Wait for the USB device to be fully released by the stopped EEG process.
sleep 3

ID="$("$PY" -m braintech.obci.experiment.cmd.obci_lsl_stream --list 2>/dev/null \
      | grep -oP 'id:\s*"\KPerun32[^"]*' | head -1 || true)"

if [ -z "${ID:-}" ]; then
    echo "impedance: no Perun32 detected; aborting check" >&2
    exit 1
fi

echo "impedance: measuring '$ID' for ${DUR}s as LSL stream 'Perun32-Impedance'" >&2
# stream_perun32.py forces measure_impedance + adds the *_impedance channels.
# `timeout` ends the pass; `|| true` so a non-zero exit still resumes EEG.
timeout "${DUR}s" "$PY" stream_perun32.py \
    -a "$ID" -n Perun32-Impedance -s 500 || true

echo "impedance: check complete" >&2
# resume_eeg() runs here via the EXIT trap.
