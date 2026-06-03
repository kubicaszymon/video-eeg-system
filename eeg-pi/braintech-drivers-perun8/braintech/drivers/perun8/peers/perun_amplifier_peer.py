# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Module providing PerunAmplifierPeer."""
from braintech.obci.experiment.peers.drivers.amplifiers.amplifier_peer import AmplifierPeer, register_amplifier_peer
from braintech.drivers.perun8.amplifiers import PerunCppAmplifier

__all__ = ('PerunAmplifierPeer',)
try:
    # Try to import also 32 channel perun peer
    import braintech.drivers.perun32.perun32_peer
except ImportError:
    pass


@register_amplifier_peer
class PerunAmplifierPeer(AmplifierPeer):
    """
    Driver for BrainAmplifier. Provides 8 channels EEG channels and 3 acceleration channels.
    """

    AmplifierClass = PerunCppAmplifier
