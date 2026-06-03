# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
from braintech.drivers.perun32.amplifier import Perun32Amplifier
from braintech.obci.experiment.peers.drivers.amplifiers.amplifier_peer import AmplifierPeer, register_amplifier_peer
from braintech.obci.core.utils.properties import bool_property


@register_amplifier_peer
class Perun32AmplifierPeer(AmplifierPeer):
    AmplifierClass = Perun32Amplifier

    measure_impedance = bool_property('measure_impedance')
    impedance_filter = bool_property('impedance_filter')

    def _manage_params(self):
        self._amplifier.measure_impedance = self.measure_impedance
        self._amplifier.impedance_filter = self.impedance_filter
        super()._manage_params()
