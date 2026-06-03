# Deploy (video Pi): camera control daemon + break-glass fallback

Symmetric with the EEG Pi. A **control daemon** (`control_daemon.py`, the
`picam-control.service` systemd *user* service) **owns the video streamer**:
it spawns/stops `stream_picam.py` and reconciles it to a persisted desired
state (`picam-state.json`). systemd keeps the *daemon* alive (with a
watchdog); the *daemon* decides about the *streamer*. The PC talks to it
over the same HTTP+JSON API as the EEG Pi (see `../../CONTROL_API_SPEC.md`),
just `kind=video` knobs and port **8081**.

`control_daemon.py` here is a **verbatim copy** of
`perun_lsl_driver/deploy/control_daemon.py` (the two Pis are separate
machines/trees/venvs, no shared import). Keep them identical — verify with:

```bash
diff perun_lsl_driver/deploy/control_daemon.py pi_camera/deploy/control_daemon.py
```

The old `stream_picam.service` + a new guarded `run_picam.sh` are kept as a
**disabled break-glass fallback**.

## One-time install on the video Pi

```bash
# 1. copy this folder to the video Pi (from your PC, PowerShell):
#    scp -r pi_camera/deploy szymon-video@video-pi.local:~/pi_camera/

# 2. on the video Pi:
chmod +x ~/pi_camera/deploy/control_daemon.py ~/pi_camera/deploy/run_picam.sh
mkdir -p ~/.config/systemd/user
cp ~/pi_camera/deploy/picam-control.service ~/.config/systemd/user/
cp ~/pi_camera/deploy/stream_picam.service  ~/.config/systemd/user/
systemctl --user daemon-reload

# 3. switch over: the control daemon replaces the old autostart
systemctl --user disable --now stream_picam.service     # stop + don't boot it
systemctl --user enable  --now picam-control.service    # the new supervisor

# 4. start on boot without being logged in (one-time, needs sudo):
sudo loginctl enable-linger "$USER"
```

Optional auth: set a shared token (env `CONTROL_TOKEN` or `--token-file`),
same as the EEG Pi.

Check it:

```bash
systemctl --user status picam-control.service
curl -s localhost:8081/status  | python3 -m json.tool
curl -s localhost:8081/options | python3 -m json.tool
```

and confirm the `Perun32_Video` LSL stream appears on the PC.

## Daily use

Video streams automatically on boot (daemon reconciles to
`picam-state.json`, default `mode=video 960x720@30 4 Mbps`). Control it
from the PC app's Video Pi dock, or directly:

```bash
curl -s -X POST localhost:8081/control -d '{"width":1280,"height":960,"fps":25}'
curl -s -X POST localhost:8081/control -d '{"bitrate":6000000}'
curl -s -X POST localhost:8081/control -d '{"hflip":true,"vflip":true}'
curl -s -X POST localhost:8081/control -d '{"mode":"stopped"}'
curl -s -X POST localhost:8081/control -d '{"mode":"video"}'
```

A resolution/fps/bitrate change restarts the encoder: `Perun32_Video`
disconnects and reappears with updated `desc/encoding` metadata — the PC
H.264 receiver already rejoins at the next keyframe.

## Break-glass: control daemon down

```bash
systemctl --user stop picam-control.service       # release the camera + lock
systemctl --user start stream_picam.service       # raw 960x720@30, no control
```

`run_picam.sh` refuses to run while the control daemon holds
`deploy/.control.lock` (prevents two supervisors colliding on the single
camera). Always stop `picam-control.service` first. To return to normal:
`systemctl --user stop stream_picam.service && systemctl --user start
picam-control.service`.

## Notes / limitations

- There is no impedance / channel concept for video; `GET /channels` and
  `POST /impedance` return 404 here (EEG-only). `GET /options` advertises
  the video knobs + ranges.
- The camera supports one capture session at a time; a mode/config change
  briefly drops `Perun32_Video`. Consumers tolerate this (rejoin at the
  next keyframe).
- The watchdog only catches a *hung* daemon; a clean crash is covered by
  `Restart=always` and the daemon re-establishes the stream from
  `picam-state.json` on restart.
- `gop=0` means "one keyframe per second" (= fps), as in `stream_picam.py`.
```
