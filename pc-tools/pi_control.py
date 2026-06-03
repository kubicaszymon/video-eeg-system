"""PC-side client for the Pi streamer control daemon.

Framework-agnostic (stdlib only) so it works from the PyQt prototype today
and a future C++/Qt app's logic can mirror it 1:1. Implements the contract
in ``CONTROL_API_SPEC.md``.

- ``ControlClient`` — one blocking HTTP+JSON call per method, short timeout,
  optional shared-token header. Returns ``(code, payload)`` where ``code``
  is the HTTP status, or ``None`` when the Pi/daemon is unreachable.
- ``ControlPoller`` — a daemon thread that polls ``/status`` (and
  occasionally ``/options`` + ``/channels``) and exposes a thread-safe
  ``snapshot()``. Mirrors the ``EegReceiver`` poll/snapshot/stop pattern in
  ``sync_prototype.py`` so the GUI never blocks on the network.

Both Pis use the same client; just point it at a different host/port.
"""

import json
import threading
import urllib.error
import urllib.request


class ControlClient:
    def __init__(self, host, port, token=None, timeout=4.0):
        self.base = "http://%s:%d" % (host, int(port))
        self.token = token
        self.timeout = timeout

    def _req(self, method, path, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base + path, data=data,
                                     method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("X-Control-Token", self.token)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read().decode("utf-8") or "{}"
                return r.status, json.loads(raw)
        except urllib.error.HTTPError as e:
            try:
                payload = json.loads(e.read().decode("utf-8") or "{}")
            except Exception:
                payload = {}
            return e.code, payload
        except (urllib.error.URLError, OSError, ValueError) as e:
            # connection refused / DNS / timeout / bad JSON -> unreachable
            return None, {"error": str(getattr(e, "reason", e))}

    # ---- API surface (see CONTROL_API_SPEC.md) ----
    def healthz(self):
        return self._req("GET", "/healthz")

    def status(self):
        return self._req("GET", "/status")

    def options(self):
        return self._req("GET", "/options")

    def channels(self):
        return self._req("GET", "/channels")

    def control(self, patch):
        return self._req("POST", "/control", patch)

    def impedance(self, duration):
        return self._req("POST", "/impedance", {"duration": duration})


class ControlPoller(threading.Thread):
    """Background poller. snapshot() is cheap + thread-safe for the UI."""

    def __init__(self, client, period=1.0):
        super().__init__(daemon=True)
        self.client = client
        self.period = period
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._status = None
        self._options = None
        self._channels = None
        self.reachable = False
        self.daemon_up = False

    def run(self):
        meta_countdown = 0
        while not self._stop.is_set():
            code, st = self.client.status()
            with self._lock:
                if code is None:
                    self.reachable = False
                    self.daemon_up = False
                else:
                    self.reachable = True
                    self.daemon_up = (code == 200)
                    if code == 200:
                        self._status = st
            # /options + /channels change rarely -> fetch on first success
            # then refresh every ~30 polls.
            if self.daemon_up and meta_countdown <= 0:
                co, opt = self.client.options()
                cc, chn = self.client.channels()
                with self._lock:
                    if co == 200:
                        self._options = opt
                    if cc == 200:
                        self._channels = chn.get("channels")
                meta_countdown = 30
            meta_countdown -= 1
            self._stop.wait(self.period)

    def snapshot(self):
        with self._lock:
            return {
                "reachable": self.reachable,
                "daemon_up": self.daemon_up,
                "status": self._status,
                "options": self._options,
                "channels": self._channels,
            }

    def stop(self):
        self._stop.set()
