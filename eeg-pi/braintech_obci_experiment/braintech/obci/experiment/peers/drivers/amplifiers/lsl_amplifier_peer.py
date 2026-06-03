# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

from braintech.obci.core.drivers.eeg.lsl_amplifier import LSLAmplifierAdapter
from braintech.obci.experiment.peers.drivers.amplifiers.amplifier_peer import AmplifierPeer, register_amplifier_peer

__all__ = ('LSLAmplifierPeer',)


@register_amplifier_peer
class LSLAmplifierPeer(AmplifierPeer):
    AmplifierClass = LSLAmplifierAdapter
