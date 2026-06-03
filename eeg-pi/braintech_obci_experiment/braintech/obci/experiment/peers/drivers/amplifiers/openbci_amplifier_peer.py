# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Module with Amplifier Peer for BCI-Framework board."""
from braintech.obci.core.drivers.eeg.openbci_amplifier import OpenBciAmplifier
from braintech.obci.experiment.peers.drivers.amplifiers.amplifier_peer import AmplifierPeer, register_amplifier_peer

__all__ = ('OpenBciAmplifierPeer',)


@register_amplifier_peer
class OpenBciAmplifierPeer(AmplifierPeer):
    """Peer which uses serial over bluetooth connection to get samples from BCI-Framework board."""

    AmplifierClass = OpenBciAmplifier
