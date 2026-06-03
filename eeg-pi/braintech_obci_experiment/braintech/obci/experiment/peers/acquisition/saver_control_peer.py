# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Module providing Saver control Peer."""
import time
import asyncio

from braintech.obci.experiment.peer.configured_peer import ConfiguredPeer
from braintech.obci.core.utils.message_helpers import send_finish_saving

__all__ = ('SaverControl',)


class SaverControl(ConfiguredPeer):
    """Peer which waits some time and then sends broadcast message "finish_saving"."""

    async def _connections_established(self):
        await super()._connections_established()
        self.sleep_time_s = int(self.get_param('acquisition_time_s'))
        self._logger.info(''.join(['[', str(self.config.peer_id), '] INITIALIZED!', str(self.sleep_time_s)]))

    async def _start(self):
        await super()._start()
        self.create_task(self._run())

    async def _run(self):
        await asyncio.sleep(self.sleep_time_s)
        self._logger.info(''.join(['[', str(self.config.peer_id), '] SEND CONTROL!']))
        time0 = time.time()
        self._logger.info("T-before: " + repr(time0))
        await send_finish_saving(self)
        time_curr = time.time()
        self._logger.info("T-after: " + repr(time_curr) + 'duration: ' + repr(time_curr - time0))
