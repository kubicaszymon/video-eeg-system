"""Compatibility alias.

The original package exposed the same containers under two import paths
(``...signal.containers`` and ``...signal.data_generic_write_proxy``).
Different driver files import from one or the other, so re-export here.
"""

from braintech.obci.signal_processing.signal.containers import (
    Impedance,
    SamplePacket,
    NETWORK_FLOAT32,
)

__all__ = ["Impedance", "SamplePacket", "NETWORK_FLOAT32"]
