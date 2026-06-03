# Deploy: EEG control daemon (PC-controllable) + break-glass fallback

The EEG Pi is now controlled from the PC. A small **control daemon**
(`control_daemon.py`, a systemd *user* service `perun-control.service`)
**owns the LSL streamer**: it spawns/stops it and reconciles it to a
persisted desired state (`perun-state.json`). systemd keeps the *daemon*
alive (with a watchdog); the *daemon* decides about the *streamer*. The PC
talks to it over a tiny HTTP+JSON API (see `../../CONTROL_API_SPEC.md`).

The old `perun-eeg.service` + `run_eeg.sh` + `run_impedance.sh` are kept as
a **disabled break-glass fallback** for when the daemon is down.

## One-time install on the Pi

```bash
# 1. copy this folder to the Pi (from your PC, PowerShell):
#    scp -r deploy szymon@camera-pi.local:~/perun_lsl_driver/

# 2. on the Pi:
chmod +x ~/perun_lsl_driver/deploy/control_daemon.py \
         ~/perun_lsl_driver/deploy/run_eeg.sh \
         ~/perun_lsl_driver/deploy/run_impedance.sh
mkdir -p ~/.config/systemd/user
cp ~/perun_lsl_driver/deploy/perun-control.service ~/.config/systemd/user/
cp ~/perun_lsl_driver/deploy/perun-eeg.service     ~/.config/systemd/user/
systemctl --user daemon-reload

# 3. switch over: the control daemon replaces the old service as supervisor
systemctl --user disable --now perun-eeg.service        # stop + don't boot it
systemctl --user enable  --now perun-control.service    # the new supervisor

# 4. start on boot without being logged in (one-time, needs sudo):
sudo loginctl enable-linger "$USER"
```

Optional auth: set a shared token so the API isn't open on the LAN.

```bash
echo 'choose-a-long-random-string' > ~/perun_lsl_driver/deploy/.control-token
# add to the [Service] section of perun-control.service:
#   Environment=CONTROL_TOKEN=%h/...   (or pass --token-file)
```

By default the API is open (closed research LAN; SSH key already grants a
shell). Add the token if the LAN is shared.

Check it:

```bash
systemctl --user status perun-control.service
curl -s localhost:8080/status   | python3 -m json.tool
curl -s localhost:8080/options  | python3 -m json.tool
```

and confirm the `Perun32` LSL stream appears on the PC.

## Daily use

EEG streams automatically on boot (the daemon reconciles to the persisted
`perun-state.json`, default `mode=eeg, rate=500, all channels`). Control it
from the PC app's EEG dock panel, or directly:

```bash
# change sampling rate (stream briefly reconnects at the new rate)
curl -s -X POST localhost:8080/control -d '{"rate":1000}'
# stream a channel subset (names from GET /channels)
curl -s -X POST localhost:8080/control -d '{"channels":["ExG_1","ExG_2"]}'
# stop / restart the stream
curl -s -X POST localhost:8080/control -d '{"mode":"stopped"}'
curl -s -X POST localhost:8080/control -d '{"mode":"eeg"}'
# on-demand impedance check (auto-reverts to the previous EEG config)
curl -s -X POST localhost:8080/impedance -d '{"duration":45}'
```

Changing rate/channels is a deliberate stream restart: `Perun32`
disconnects and reappears with new metadata — PC consumers already handle
this as a normal reconnect.

## Break-glass: control daemon down

```bash
systemctl --user stop perun-control.service      # release the device + lock
systemctl --user start perun-eeg.service         # raw 500 Hz EEG, no control
ssh szymon@camera-pi.local '~/perun_lsl_driver/deploy/run_impedance.sh 45'
```

`run_eeg.sh` / `run_impedance.sh` refuse to run while the control daemon
holds `deploy/.control.lock` (prevents two supervisors colliding on the
single USB amp). Always stop `perun-control.service` first. To return to
normal: `systemctl --user stop perun-eeg.service && systemctl --user start
perun-control.service`.

## Useful commands (on the Pi)

```bash
systemctl --user restart perun-control.service       # bounce the daemon
journalctl --user -u perun-control.service -f        # live logs (incl. child)
cat ~/perun_lsl_driver/deploy/perun-state.json       # current desired state
```

## Notes / limitations

- The EEG stream genuinely drops during a rate/channel change or impedance
  check; the device can only do one mode at a time and only one process may
  hold the USB. Consumers must tolerate `Perun32` vanishing/reappearing.
- `--list` (amp-id / channel discovery) opens the USB device, so the daemon
  probes only while no streamer child is running and caches the result;
  `GET /channels` / `GET /options` return the cached values.
- The watchdog only catches a *hung* daemon; a clean crash is covered by
  `Restart=always` and the daemon re-establishes the stream from
  `perun-state.json` on restart.
- This is still the interim Python streamer. In the planned C++ driver only
  the `eeg_argv` line in `control_profile.eeg.json` changes — the daemon,
  the API and the PC panel are unaffected.
```
