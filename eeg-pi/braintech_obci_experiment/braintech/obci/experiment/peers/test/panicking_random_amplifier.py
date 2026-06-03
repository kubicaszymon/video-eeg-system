# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Module containing amplifier peers for testing errors."""
import asyncio


__all__ = ('PanickingRandomAmplifierPeer', )

from braintech.obci.experiment.peers.drivers.amplifiers.random_amplifier_peer import RandomAmplifierPeer


class PanickingRandomAmplifierPeer(RandomAmplifierPeer):
    """Test amplifier which panics within a short time from initialization."""

    async def ready(self, *args, **kwargs):
        """Prepare the peer, then schedule panic."""
        await super().ready(*args, **kwargs)
        self.create_task(self.wait_then_panic())

    async def wait_then_panic(self):
        """Make the peer panic after a short wait."""
        await asyncio.sleep(5)
        await self.panic(Exception("Simulated amplifier error."))
