# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Module providing RandomAmplifierPeer."""
from braintech.obci.core.drivers.eeg.random_amplifier import RandomAmplifier
from braintech.obci.experiment.peers.drivers.amplifiers.amplifier_peer import AmplifierPeer, register_amplifier_peer

__all__ = ('RandomAmplifierPeer',)


@register_amplifier_peer
class RandomAmplifierPeer(AmplifierPeer):
    """Random amplifier - sends random data (uniform [0;1)) over all channels."""

    AmplifierClass = RandomAmplifier
