#!/usr/bin/env bash
# Continuous Pi-camera -> LSL H.264 video stream (the stable 960x720@30
# config). BREAK-GLASS ONLY: the normal supervisor is picam-control.service
# (control_daemon.py). This script / stream_picam.service are the disabled
# fallback for when the control daemon is down. The guard below refuses to
# run while the control daemon holds the camera, so two supervisors can't
# fight over the single camera device.
set -euo pipefail

# --- break-glass interlock: never run alongside the control daemon -------
LOCK="$HOME/pi_camera/deploy/.control.lock"
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then
    echo "run_picam: control daemon is running (pid $(cat "$LOCK"))." >&2
    echo "run_picam: use the control API, or stop it first:" >&2
    echo "  systemctl --user stop picam-control.service" >&2
    exit 3
fi

cd "$HOME/pi_camera"
PY="$HOME/pi_camera/.venv-video/bin/python"

echo "run_picam: streaming as LSL stream 'Perun32_Video'" >&2
exec "$PY" stream_picam.py -n Perun32_Video -W 960 -H 720 -f 30 -b 4000000
