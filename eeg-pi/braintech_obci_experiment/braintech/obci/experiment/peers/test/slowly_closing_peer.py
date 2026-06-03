# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Provides an example implementation of peer which delays closing."""

import asyncio
from braintech.obci.experiment.peer.configured_peer import ConfiguredPeer

__all__ = ('SlowlyClosingPeer',)


class SlowlyClosingPeer(ConfiguredPeer):
    """
    Peer which does nothing, but its shutdown takes a while.

    Duration of the shutdown can be specified with "delay" parameter (in seconds, defaults to 10).
    """

    async def _shutting_down(self):
        """
        Perform a shutdown.

        It is guaranteed that the shutdown will take at least "delay" seconds.
        """
        await asyncio.sleep(float(self.get_param('delay')))
        await super()._shutting_down()
