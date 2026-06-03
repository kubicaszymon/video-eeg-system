"""Minimal reimplementation of ``braintech.utils.singleton_app``.

Used as a cross-process mutex so two processes don't grab the same USB
amplifier at once. Real call sites (reconstructed from the drivers):

    # perun32/device.py -- positional, auto-acquires in __init__:
    SingleProcessApplication('perun32', str(usb_address))

    # perun8/amplifiers.py -- kwargs, deferred acquire:
    SingleProcessApplication(flavor_id=str(i), basename='obci.perunamp',
                             autolock=False)
    ... lock.acquire() ... lock.release()

Contract:
* ``__init__(basename, flavor_id='', autolock=True)`` -- if ``autolock``
  is true, acquire immediately (raising ``SingleInstanceException`` if
  another live process already holds the same basename+flavor_id).
* ``acquire()`` / ``release()`` -- explicit lock control.

Implemented with an OS advisory file lock so it works on both Windows
(your PC) and Linux (the Pi), and the OS frees the lock automatically if
the process dies.
"""

import os
import tempfile


class SingleInstanceException(Exception):
    pass


def _lock_path(basename, flavor_id):
    raw = "{}_{}".format(basename, flavor_id)
    safe = "".join(c if c.isalnum() else "_" for c in raw)
    return os.path.join(tempfile.gettempdir(), "braintech_{}.lock".format(safe))


class SingleProcessApplication:
    def __init__(self, basename, flavor_id="", autolock=True):
        self._basename = basename
        self._flavor_id = flavor_id
        self._path = _lock_path(basename, flavor_id)
        self._fh = None
        if autolock:
            self.acquire()

    def acquire(self):
        if self._fh is not None:
            # Already held by this instance; nothing to do.
            return
        fh = open(self._path, "a+")
        try:
            if os.name == "nt":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError) as exc:
            fh.close()
            raise SingleInstanceException(
                "Another instance holding '{}' is already running "
                "(lock: {})".format(self._basename, self._path)
            ) from exc
        self._fh = fh

    def release(self):
        if self._fh is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        except (OSError, IOError):
            pass
        finally:
            self._fh.close()
            self._fh = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()

    def __del__(self):
        try:
            self.release()
        except Exception:
            pass


# obci_core and the tray app import this name; same behaviour is fine.
class SingleApplicationInstance(SingleProcessApplication):
    pass


__all__ = [
    "SingleInstanceException",
    "SingleProcessApplication",
    "SingleApplicationInstance",
]
