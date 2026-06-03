#!/usr/bin/env bash
# Continuous plain-EEG -> LSL stream (the 24/7 stable config: no impedance,
# drift-correction disabled on the Pi). Auto-detects the Perun32 USB id so
# it survives the id changing.
#
# BREAK-GLASS ONLY. The normal supervisor is perun-control.service
# (control_daemon.py). This script / perun-eeg.service are the disabled
# fallback for when the control daemon is down. The guard below refuses to
# run while the control daemon holds the device, so you can't accidentally
# get two supervisors fighting over the single USB amp.
set -euo pipefail

# --- break-glass interlock: never run alongside the control daemon -------
LOCK="$HOME/perun_lsl_driver/deploy/.control.lock"
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then
    echo "run_eeg: control daemon is running (pid $(cat "$LOCK"))." >&2
    echo "run_eeg: use the control API, or stop it first:" >&2
    echo "  systemctl --user stop perun-control.service" >&2
    exit 3
fi

cd "$HOME/perun_lsl_driver"
PY="$HOME/perun_lsl_driver/.venv/bin/python"

# Pull the first amplifier id that looks like a Perun32 out of --list.
ID="$("$PY" -m braintech.obci.experiment.cmd.obci_lsl_stream --list 2>/dev/null \
      | grep -oP 'id:\s*"\KPerun32[^"]*' | head -1 || true)"

if [ -z "${ID:-}" ]; then
    echo "run_eeg: no Perun32 detected (is it plugged in?)" >&2
    exit 1
fi

echo "run_eeg: streaming amplifier id '$ID' as LSL stream 'Perun32'" >&2
exec "$PY" -m braintech.obci.experiment.cmd.obci_lsl_stream \
    -a "$ID" -n Perun32 -s 500
