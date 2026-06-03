"""Minimal reimplementation of the data containers from the proprietary
``braintech-obci-signal-processing`` package.

Only the two types the Perun32 -> LSL path needs are provided:

* ``Impedance`` -- doubles as (a) per-channel state flags
  (``UNKNOWN`` / ``PRESENT`` / ``NOT_APPLICABLE``) and (b) a container
  carrying per-channel impedance ``ids`` + measured ``data``.
* ``SamplePacket`` -- a packet of ``samples`` + ``ts`` (+ optional impedance).

The API here was reconstructed from how the driver actually uses these
classes; it is intentionally tiny.
"""

import numpy


class _ImpedanceFlag:
    """A unique sentinel so ``is`` and ``==`` identity checks work."""

    __slots__ = ("_name",)

    def __init__(self, name):
        self._name = name

    def __repr__(self):
        return "Impedance.{}".format(self._name)


class Impedance:
    # Per-channel state flags. The driver compares channel.impedance against
    # these with both ``is`` and ``==``, so they must be unique singletons.
    UNKNOWN = _ImpedanceFlag("UNKNOWN")
    PRESENT = _ImpedanceFlag("PRESENT")
    NOT_APPLICABLE = _ImpedanceFlag("NOT_APPLICABLE")

    def __init__(self, ids=None, data=None):
        # ids: list of the per-channel flags above
        # data: numpy array of measured impedance values (or None)
        self.ids = ids
        self.data = data

    def __repr__(self):
        shape = getattr(self.data, "shape", None)
        return "<Impedance ids={!r} data_shape={}>".format(self.ids, shape)


class SamplePacket:
    __slots__ = ("samples", "ts", "impedance")

    def __init__(self, samples, ts, impedance=None):
        self.samples = samples
        self.ts = ts
        # Driver returns impedance=None when not measuring; downstream code
        # unconditionally reads packet.impedance.data, so never store None.
        self.impedance = impedance if impedance is not None else Impedance()

    def __repr__(self):
        s_shape = getattr(self.samples, "shape", None)
        n_ts = len(self.ts) if self.ts is not None else 0
        return "<SamplePacket samples_shape={} n_ts={}>".format(s_shape, n_ts)


# Referenced by a test in obci_core; harmless to expose for compatibility.
NETWORK_FLOAT32 = numpy.float32

__all__ = ["Impedance", "SamplePacket", "NETWORK_FLOAT32"]
