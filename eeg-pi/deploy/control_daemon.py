#!/usr/bin/env python3
"""Generic stdlib-only supervisor + tiny HTTP control API for a Pi streamer.

Why this exists
---------------
Both Pis in the video-EEG system auto-start a hardcoded LSL stream on boot.
We want to control them from the PC (and later a C++/Qt app): which stream
runs, sampling rate / resolution, channels, start/stop, impedance checks,
plus live status.

LSL has no control channel, so control is a *separate* layer. This one
daemon (deployed to both Pis, behaviour driven by a per-host profile JSON)
**owns the streamer process lifecycle**: it spawns the streamer itself and
is the thing that decides whether/what runs, reconciling the running child
to a persisted *desired-state* file. systemd's ``Restart=always`` now keeps
the *daemon* alive; the daemon -- not systemd -- decides about the streamer,
so "stopped" actually stays stopped and a rate/channel change is a clean
terminate -> wait -> relaunch (the only safe way: the amp can't change rate
while sampling and only one process may hold the USB device).

Forward-compat: the streamer command is just an argv template in the
profile. When the EEG driver becomes a C++ binary, only that template line
changes -- the API, the PC panel and a future C++/Qt client are unaffected.

Pure Python standard library (runs on the Pi Zero 2W; no extra deps).

Usage on the Pi::

    ./control_daemon.py --profile control_profile.eeg.json \
        --bind 0.0.0.0 --port 8080

Auth: if env CONTROL_TOKEN is set (or --token-file given) every request
must carry header  X-Control-Token: <token>  (except GET /healthz).
"""

import argparse
import collections
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def _log(msg):
    sys.stderr.write("[control] %s\n" % msg)
    sys.stderr.flush()


def _expand(path):
    """Expand ~ and {HOME} in profile paths."""
    if path is None:
        return None
    return os.path.expanduser(path.replace("{HOME}", os.path.expanduser("~")))


def _sd_notify(state):
    """Best-effort sd_notify (no-op when not run under systemd notify).

    Used in step 2 for the watchdog; harmless to call now.
    """
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return
    try:
        import socket
        if addr.startswith("@"):
            addr = "\0" + addr[1:]
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        s.connect(addr)
        s.sendall(state.encode("utf-8"))
        s.close()
    except Exception:
        pass


# --------------------------------------------------------------------------
# supervisor
# --------------------------------------------------------------------------

class Supervisor:
    """Owns the streamer child and reconciles it to the desired state.

    A single background thread (the reconciler) performs every process
    transition under one lock, so HTTP handlers never block on a spawn and
    there are no races between "child died" and "user changed config".
    """

    def __init__(self, profile):
        self.profile = profile
        self.kind = profile["kind"]                       # "eeg" | "video"
        self.python = _expand(profile["python"])
        self.workdir = _expand(profile["workdir"])
        self.state_file = _expand(profile["state_file"])
        self.lock_file = _expand(profile.get("lock_file"))
        self.usb_release_s = float(profile.get("usb_release_s", 3))
        self.start_grace_s = float(profile.get("start_grace_s", 6))
        self.term_timeout_s = float(profile.get("term_timeout_s", 8))
        self.name_regex = re.compile(profile.get("name_regex", "^[A-Za-z0-9_-]+$"))

        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._stop = threading.Event()

        self._child = None                # subprocess.Popen | None
        self._child_argv = None           # argv the live child was spawned with
        self._child_started = 0.0
        self._child_short_runs = 0        # consecutive too-fast exits
        self._last_exit_code = None
        self._stderr = collections.deque(maxlen=40)
        self._transitioning = False
        self._imp_timer = None            # threading.Timer reverting impedance

        # cached USB probe results (only refreshed when no child holds device)
        self._amp_id = None
        self._probe_channels = []
        self._probe_rates = []
        self._probe_err = None

        self.started_at = time.time()

        # systemd watchdog: when run as Type=notify with WatchdogSec=,
        # systemd exports WATCHDOG_USEC. We must send WATCHDOG=1 at least
        # that often *from the reconciler thread* -- so if the reconciler
        # hangs, systemd restarts us (a separate always-alive pinger would
        # defeat the purpose). Ping at half the interval.
        wd_usec = os.environ.get("WATCHDOG_USEC")
        self._wd_interval = (int(wd_usec) / 1e6 / 2.0) if wd_usec else 0.0
        self._wd_last = 0.0

        self.state = self._load_state()

    def _wd(self):
        """Throttled systemd watchdog ping (no-op when not under watchdog)."""
        if not self._wd_interval:
            return
        now = time.time()
        if now - self._wd_last >= self._wd_interval:
            _sd_notify("WATCHDOG=1")
            self._wd_last = now

    # ---- desired-state persistence ----------------------------------------

    def _load_state(self):
        default = dict(self.profile.get("default_state", {}))
        try:
            with open(self.state_file, "r") as fh:
                disk = json.load(fh)
            if isinstance(disk, dict):
                default.update(disk)
                _log("loaded desired state from %s" % self.state_file)
        except FileNotFoundError:
            _log("no state file; using profile default_state")
        except Exception as exc:
            _log("state file unreadable (%s); using default" % exc)
        return default

    def _save_state(self):
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            tmp = self.state_file + ".tmp"
            with open(tmp, "w") as fh:
                json.dump(self.state, fh, indent=2, sort_keys=True)
            os.replace(tmp, self.state_file)
        except Exception as exc:
            _log("could not persist state: %s" % exc)

    # ---- USB probe (amp id / channels / rates) ----------------------------

    def _probe(self):
        """Run the streamer's --list to learn amp id, channels, rates.

        --list opens the USB device, so this MUST run only when no streamer
        child is alive. Results are cached and reused while streaming.
        """
        argv = [self._sub(tok, {}) for tok in self.profile.get("list_argv", [])]
        if not argv:
            return
        try:
            out = subprocess.run(argv, cwd=self.workdir, capture_output=True,
                                  text=True, timeout=30)
            text = (out.stdout or "") + "\n" + (out.stderr or "")
        except Exception as exc:
            self._probe_err = "list failed: %s" % exc
            _log(self._probe_err)
            return
        amp_re = self.profile.get("ampid_regex", r'id:\s*"(Perun32[^"]*)"')
        m = re.search(amp_re, text)
        if not m:
            self._probe_err = "no amplifier detected via --list"
            self._amp_id = None
            return
        self._amp_id = m.group(1)
        self._probe_err = None
        # channels: the indented line right after "available channels:"
        cm = re.search(r"available channels:\s*\n\s*(.+)", text)
        if cm:
            self._probe_channels = cm.group(1).strip().split()
        rm = re.search(r"available sampling rates:\s*\n\s*(.+)", text)
        if rm:
            rates = []
            for tok in rm.group(1).strip().split():
                try:
                    rates.append(int(float(tok)))
                except ValueError:
                    pass
            if rates:
                self._probe_rates = rates
        _log("probe: amp=%s channels=%d rates=%s"
             % (self._amp_id, len(self._probe_channels), self._probe_rates))

    def _allowed_rates(self):
        return self._probe_rates or list(self.profile.get("allowed_rates", []))

    # ---- argv construction ------------------------------------------------

    def _sub(self, token, ctx):
        """Substitute {python}/{ampid}/{name}/{rate}/{...} in one argv token."""
        token = token.replace("{python}", self.python)
        for key, val in ctx.items():
            token = token.replace("{%s}" % key, str(val))
        return token

    def _build_argv(self, state):
        """Return (argv, error). argv is None if it cannot be built yet."""
        if self.kind == "eeg":
            mode = state.get("mode")
            if mode == "impedance":
                tmpl = self.profile["impedance_argv"]
                name = self.profile.get("impedance_stream_name",
                                        "Perun32-Impedance")
            else:
                tmpl = self.profile["eeg_argv"]
                name = state.get("name", "Perun32")
            if "{ampid}" in " ".join(tmpl) and not self._amp_id:
                return None, "no amplifier detected (is it plugged in?)"
            ctx = {"ampid": self._amp_id or "",
                   "name": name,
                   "impedance_name": self.profile.get("impedance_stream_name",
                                                      "Perun32-Impedance"),
                   "rate": int(state.get("rate", 500))}
            argv = [self._sub(t, ctx) for t in tmpl]
            chans = state.get("channels")
            if chans:
                argv.append(self.profile.get("channels_flag", "-c"))
                argv.extend(str(c) for c in chans)
            return argv, None

        if self.kind == "video":
            tmpl = self.profile["video_argv"]
            ctx = {"name": state.get("name", "Perun32_Video"),
                   "width": int(state.get("width", 960)),
                   "height": int(state.get("height", 720)),
                   "fps": _numfmt(state.get("fps", 30)),
                   "bitrate": int(state.get("bitrate", 4000000)),
                   "gop": int(state.get("gop", 0))}
            argv = [self._sub(t, ctx) for t in tmpl]
            for key, flag in self.profile.get("flags", {}).items():
                if state.get(key):
                    argv.append(flag)
            return argv, None

        return None, "unknown profile kind %r" % self.kind

    # ---- validation (server-side, authoritative) --------------------------

    def validate(self, patch):
        """Validate+normalise a /control patch. Returns (ok, msg, clean)."""
        clean = {}
        if not isinstance(patch, dict):
            return False, "body must be a JSON object", None

        if self.kind == "eeg":
            if "mode" in patch:
                if patch["mode"] not in ("eeg", "impedance", "stopped"):
                    return False, "mode must be eeg|impedance|stopped", None
                clean["mode"] = patch["mode"]
            if "rate" in patch:
                try:
                    rate = int(float(patch["rate"]))
                except (TypeError, ValueError):
                    return False, "rate must be a number", None
                allowed = self._allowed_rates()
                if allowed and rate not in allowed:
                    return False, ("rate %s not allowed; allowed: %s"
                                   % (rate, allowed)), None
                clean["rate"] = rate
            if "channels" in patch:
                ch = patch["channels"]
                if ch is None:
                    clean["channels"] = None
                elif isinstance(ch, list) and all(isinstance(x, str) for x in ch):
                    known = set(self._probe_channels)
                    if known:
                        bad = [c for c in ch if c not in known]
                        if bad:
                            return False, "unknown channels: %s" % bad, None
                    clean["channels"] = ch or None
                else:
                    return False, "channels must be null or a list of names", None
            if "name" in patch:
                if not self.name_regex.match(str(patch["name"])):
                    return False, "name must match %s" % self.name_regex.pattern, None
                clean["name"] = str(patch["name"])
            if "impedance_duration" in patch:
                try:
                    d = int(float(patch["impedance_duration"]))
                except (TypeError, ValueError):
                    return False, "impedance_duration must be a number", None
                if not (5 <= d <= 600):
                    return False, "impedance_duration out of range 5..600", None
                clean["impedance_duration"] = d

        elif self.kind == "video":
            if "mode" in patch:
                if patch["mode"] not in ("video", "stopped"):
                    return False, "mode must be video|stopped", None
                clean["mode"] = patch["mode"]
            ranges = self.profile.get("ranges", {})
            for key in ("width", "height", "fps", "bitrate", "gop"):
                if key in patch:
                    try:
                        val = float(patch[key])
                    except (TypeError, ValueError):
                        return False, "%s must be a number" % key, None
                    lo, hi = ranges.get(key, [None, None])
                    if lo is not None and not (lo <= val <= hi):
                        return False, ("%s out of range %s..%s"
                                       % (key, lo, hi)), None
                    clean[key] = val if key == "fps" else int(val)
            for key in ("hflip", "vflip"):
                if key in patch:
                    clean[key] = bool(patch[key])
            if "name" in patch:
                if not self.name_regex.match(str(patch["name"])):
                    return False, "name must match %s" % self.name_regex.pattern, None
                clean["name"] = str(patch["name"])
        else:
            return False, "unknown profile kind", None

        if not clean:
            return False, "no recognised fields in request", None
        return True, "ok", clean

    # ---- public control entry points (called by HTTP handlers) ------------

    def apply(self, clean):
        with self._lock:
            self.state.update(clean)
            self._save_state()
        self._wake.set()

    def start_impedance(self, duration):
        if self.kind != "eeg":
            return False, "impedance only on the EEG Pi"
        with self._lock:
            prev = {k: self.state.get(k)
                    for k in ("mode", "rate", "channels", "name")}
            if prev["mode"] == "impedance":
                prev = self.state.get("_revert_to", prev)
            self.state["_revert_to"] = prev
            self.state["mode"] = "impedance"
            self.state["impedance_duration"] = duration
            self._save_state()
            if self._imp_timer is not None:
                self._imp_timer.cancel()
            self._imp_timer = threading.Timer(duration + 1.0,
                                              self._revert_impedance)
            self._imp_timer.daemon = True
            self._imp_timer.start()
        self._wake.set()
        return True, "impedance started for %ss" % duration

    def _revert_impedance(self):
        with self._lock:
            revert = self.state.get("_revert_to") or {"mode": "eeg"}
            for k, v in revert.items():
                self.state[k] = v
            self.state.pop("_revert_to", None)
            self._save_state()
            _log("impedance window over; reverting to %s" % revert.get("mode"))
        self._wake.set()

    # ---- child process management -----------------------------------------

    def _spawn(self, argv):
        _log("spawn: %s" % " ".join(argv))
        self._stderr.clear()
        try:
            self._child = subprocess.Popen(
                argv, cwd=self.workdir,
                stdout=None, stderr=subprocess.PIPE,
                start_new_session=True, text=True)
        except Exception as exc:
            self._child = None
            self._stderr.append("spawn failed: %s" % exc)
            _log("spawn failed: %s" % exc)
            return
        self._child_argv = argv
        self._child_started = time.time()
        t = threading.Thread(target=self._drain_stderr,
                              args=(self._child,), daemon=True)
        t.start()

    def _drain_stderr(self, proc):
        try:
            for line in iter(proc.stderr.readline, ""):
                line = line.rstrip("\n")
                if line:
                    self._stderr.append(line)
                    sys.stderr.write("[child] %s\n" % line)
                    sys.stderr.flush()
        except Exception:
            pass

    def _terminate(self):
        proc = self._child
        if proc is None:
            return
        _log("terminating child pid=%s" % proc.pid)
        # SIGINT first: the streamers catch KeyboardInterrupt and shut the
        # USB / LSL outlet down cleanly.
        for sig, wait in ((signal.SIGINT, self.term_timeout_s),
                          (signal.SIGTERM, 3.0)):
            try:
                os.killpg(os.getpgid(proc.pid), sig)
            except ProcessLookupError:
                break
            except Exception as exc:
                _log("signal %s failed: %s" % (sig, exc))
            try:
                proc.wait(timeout=wait)
                break
            except subprocess.TimeoutExpired:
                continue
        else:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass
        self._wd()                      # termination can take ~10s; stay alive
        try:
            self._last_exit_code = proc.poll()
        except Exception:
            self._last_exit_code = None
        self._child = None
        self._child_argv = None

    # ---- the single reconciler thread -------------------------------------

    def _reconcile_once(self):
        with self._lock:
            state = dict(self.state)
            mode = state.get("mode", "stopped")

            # child exited on its own?
            if self._child is not None and self._child.poll() is not None:
                self._last_exit_code = self._child.poll()
                ran = time.time() - self._child_started
                _log("child exited code=%s after %.1fs"
                     % (self._last_exit_code, ran))
                if ran < self.start_grace_s:
                    self._child_short_runs += 1
                else:
                    self._child_short_runs = 0
                self._child = None
                self._child_argv = None

            if mode == "stopped":
                if self._child is not None:
                    self._transitioning = True
                    self._terminate()
                    self._refresh_probe_locked()
                    self._transitioning = False
                return

            desired_argv, err = self._build_argv(state)
            if desired_argv is None:
                # cannot build yet (e.g. amp not detected) -> probe & wait
                if self._child is None:
                    self._refresh_probe_locked()
                self._stderr.append(err or "cannot build command")
                return

            if self._child is not None and self._child_argv == desired_argv:
                return  # already running the right thing

            # need a (re)start
            self._transitioning = True
            try:
                self._wd()
                if self._child is not None:
                    self._terminate()
                    self._wd()
                    time.sleep(self.usb_release_s)
                else:
                    # backoff after repeated fast failures (plan: retry once
                    # with a longer delay before giving the USB another go)
                    if self._child_short_runs >= 1:
                        time.sleep(self.usb_release_s * 2)
                self._wd()
                self._refresh_probe_locked()
                self._wd()
                desired_argv, err = self._build_argv(state)
                if desired_argv is None:
                    self._stderr.append(err or "cannot build command")
                    return
                self._spawn(desired_argv)
            finally:
                self._transitioning = False

    def _refresh_probe_locked(self):
        """Probe USB only when safe (no child holding the device)."""
        if self._child is None:
            self._probe()

    def run_forever(self):
        if self.lock_file:
            try:
                with open(self.lock_file, "w") as fh:
                    fh.write(str(os.getpid()))
            except Exception:
                pass
        self._probe()                       # safe: no child yet
        while not self._stop.is_set():
            self._wd()
            try:
                self._reconcile_once()
            except Exception as exc:
                _log("reconcile error: %s" % exc)
            self._wake.wait(timeout=1.0)
            self._wake.clear()
        with self._lock:
            self._terminate()
        if self.lock_file:
            try:
                os.remove(self.lock_file)
            except OSError:
                pass

    def shutdown(self):
        self._stop.set()
        self._wake.set()

    # ---- introspection ----------------------------------------------------

    def _public_state(self):
        return {k: v for k, v in self.state.items() if not k.startswith("_")}

    def status(self):
        with self._lock:
            alive = self._child is not None and self._child.poll() is None
            st = {
                "kind": self.kind,
                "label": self.profile.get("label", self.kind),
                "state": self._public_state(),
                "child_alive": alive,
                "child_pid": self._child.pid if alive else None,
                "child_argv": self._child_argv,
                "last_exit_code": self._last_exit_code,
                "last_error": (self._stderr[-1] if self._stderr else None),
                "stderr_tail": list(self._stderr)[-8:],
                "transition_in_progress": self._transitioning,
                "uptime_s": round(time.time() - self.started_at, 1),
            }
            if self.kind == "eeg":
                st["amp_detected"] = self._amp_id
                st["probe_error"] = self._probe_err
            return st

    def options(self):
        opt = {"kind": self.kind, "label": self.profile.get("label", self.kind)}
        if self.kind == "eeg":
            opt["modes"] = ["eeg", "impedance", "stopped"]
            opt["rates"] = self._allowed_rates()
            opt["channels"] = list(self._probe_channels)
            opt["name_regex"] = self.name_regex.pattern
        elif self.kind == "video":
            opt["modes"] = ["video", "stopped"]
            opt["ranges"] = self.profile.get("ranges", {})
            opt["flags"] = list(self.profile.get("flags", {}).keys())
            opt["name_regex"] = self.name_regex.pattern
        return opt


def _numfmt(v):
    """Format a number without a trailing .0 (fps may be int-like float)."""
    f = float(v)
    return int(f) if f == int(f) else f


# --------------------------------------------------------------------------
# HTTP API
# --------------------------------------------------------------------------

def make_handler(sup, token):

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):       # quiet; we log what matters ourselves
            pass

        def _send(self, code, obj):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except Exception:
                pass

        def _authed(self):
            if not token:
                return True
            return self.headers.get("X-Control-Token") == token

        def _body(self):
            try:
                n = int(self.headers.get("Content-Length", 0))
                if n <= 0:
                    return {}
                return json.loads(self.rfile.read(n).decode("utf-8"))
            except Exception:
                return None

        def do_GET(self):
            if self.path == "/healthz":
                return self._send(200, {"ok": True})
            if not self._authed():
                return self._send(401, {"error": "missing/invalid token"})
            if self.path == "/status":
                return self._send(200, sup.status())
            if self.path == "/options":
                return self._send(200, sup.options())
            if self.path == "/channels":
                if sup.kind != "eeg":
                    return self._send(404, {"error": "no channels endpoint"})
                return self._send(200, {"channels": sup._probe_channels})
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._authed():
                return self._send(401, {"error": "missing/invalid token"})
            body = self._body()
            if body is None:
                return self._send(400, {"error": "invalid JSON body"})
            if self.path == "/control":
                ok, msg, clean = sup.validate(body)
                if not ok:
                    return self._send(400, {"error": msg})
                sup.apply(clean)
                return self._send(202, {"accepted": True, "applying": True,
                                        "state": sup._public_state()})
            if self.path == "/impedance":
                if sup.kind != "eeg":
                    return self._send(404, {"error": "impedance is EEG-only"})
                dur = body.get("duration",
                               sup.state.get("impedance_duration", 45))
                try:
                    dur = int(float(dur))
                except (TypeError, ValueError):
                    return self._send(400, {"error": "duration must be a number"})
                if not (5 <= dur <= 600):
                    return self._send(400, {"error": "duration out of range 5..600"})
                ok, msg = sup.start_impedance(dur)
                return self._send(202 if ok else 400, {"message": msg})
            return self._send(404, {"error": "not found"})

    return Handler


# --------------------------------------------------------------------------
# entrypoint
# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="Pi streamer control daemon")
    ap.add_argument("--profile", required=True,
                    help="path to the host profile JSON")
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--token-file", default=None,
                    help="file whose contents are the shared auth token "
                         "(else env CONTROL_TOKEN, else no auth)")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    with open(_expand(args.profile), "r") as fh:
        profile = json.load(fh)

    token = os.environ.get("CONTROL_TOKEN")
    if args.token_file:
        try:
            with open(_expand(args.token_file), "r") as fh:
                token = fh.read().strip()
        except Exception as exc:
            _log("token file unreadable: %s" % exc)
    if not token:
        _log("WARNING: no auth token set; API is open on the LAN")

    sup = Supervisor(profile)
    rec = threading.Thread(target=sup.run_forever, daemon=True)
    rec.start()

    httpd = ThreadingHTTPServer((args.bind, args.port),
                                make_handler(sup, token))
    httpd.daemon_threads = True

    def _bye(signum, frame):
        _log("signal %s -> shutting down" % signum)
        sup.shutdown()
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _bye)
    signal.signal(signal.SIGINT, _bye)

    _log("HTTP control API on %s:%d  profile=%s kind=%s"
         % (args.bind, args.port, args.profile, profile.get("kind")))
    # The socket is bound now, so we can serve requests -> tell systemd we
    # are ready (Type=notify). The USB probe runs in the reconciler thread
    # in parallel, so a slow --list never delays unit startup.
    _sd_notify("READY=1")
    try:
        httpd.serve_forever(poll_interval=0.5)
    finally:
        sup.shutdown()
        rec.join(timeout=10)
        _log("stopped")


if __name__ == "__main__":
    main()
