# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Module providing DummyAmplifierPeer."""
from braintech.obci.experiment.peers.drivers.amplifiers.amplifier_peer import AmplifierPeer, register_amplifier_peer
from braintech.drivers.native_amplifier_lib.dummy_amplifier import DummyCppBaseAmplifier

__all__ = ('DummyAmplifierPeer',)


@register_amplifier_peer
class DummyAmplifierPeer(AmplifierPeer):
    """
    Amplifier which sends different sinusoids, saws etc for testing.

    Uses python3-obci-cpp-amplifiers binary extension module.
    """

    AmplifierClass = DummyCppBaseAmplifier
