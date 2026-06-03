# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.
from braintech.obci.experiment.peer.configured_peer import SignalReceiverMixin, ConfiguredPeer
from braintech.obci.core.broker.messages import SignalMessage
from braintech.obci.core.utils.properties import param_property
from braintech.drivers.native_amplifier_lib.amplifier_latency_variability_checker import \
    AmplifierLatencyVariabilityChecker

__all__ = ('LatencyChecker',)


class LatencyChecker(SignalReceiverMixin, ConfiguredPeer):
    sampling_rate = param_property('sampling_rate', float)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._latency_checker = None

    async def _initialized(self):
        await super()._initialized()
        self._latency_checker = AmplifierLatencyVariabilityChecker(sampling_rate=self.sampling_rate, comm_peer=self)
        self.create_task(self._latency_checker.measure_delays())

    async def _signal_message_handler(self, msg: SignalMessage):
        if self._latency_checker is not None:
            self._latency_checker.get_packet(msg.data)
