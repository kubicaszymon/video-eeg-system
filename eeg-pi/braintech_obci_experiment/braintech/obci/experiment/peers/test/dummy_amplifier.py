# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Dummy amplifier providing random signal."""
from braintech.obci.core.broker import messages
from braintech.obci.core.broker.peer import Peer
from braintech.obci.core.utils.signal_generators import AsyncSignalGenerator


__all__ = ('DummyAmplifierPeer',)


class DummyAmplifierPeer(Peer):
    """Amplifier peer generates signal using AsyncSignalGenerator."""

    async def generate_test_signal(self) -> None:
        """
        Task which starts signal generation.

        :return: None
        """
        sig_gen = AsyncSignalGenerator()
        async for samples in sig_gen:
            self.send_message(messages.SignalMessage(data=samples))
