# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Provides ErrorGeneratorPeer."""
import asyncio
import os
import signal
import sys
import time

from braintech.obci.experiment.peer.configured_peer import ConfiguredPeer

__all__ = ('ErrorGeneratorPeer',)


class ErrorGeneratorPeer(ConfiguredPeer):
    """Peer created for integration tests of logging and crash reporting system."""

    def __init__(self, *args, **kwargs):
        """Created as ConfiguredPeer."""
        super().__init__(*args, **kwargs)
        time.sleep(float(self.get_param('delay')))
        if int(self.get_param('constructor_exc')):
            raise Exception('TEST Exception during constructor')
        if int(self.get_param('constructor_logerror')):
            self._logger.error('TEST log error during constructor')
        if int(self.get_param('constructor_logfatal')):
            self._logger.fatal('TEST log fatal during constructor')

    async def _connections_established(self):
        await super()._connections_established()
        if int(self.get_param('init_exc')):
            raise Exception('TEST Exception during init')
        if int(self.get_param('init_logerror')):
            self._logger.error('TEST log error during init')
        if int(self.get_param('init_logfatal')):
            self._logger.fatal('TEST log fatal during init')

    async def _start(self):
        await super()._start()
        self.create_task(self.critical_task(), critical=True)
        self.create_task(self.noncritical_task(), critical=False)

    async def noncritical_task(self):
        """For generating different events in noncritical asyncio task."""
        await asyncio.sleep(float(self.get_param('delay')))
        if int(self.get_param('task_exc')):
            raise Exception('TEST Exception during noncritical task')
        if int(self.get_param('task_logerror')):
            self._logger.error('TEST log error during noncritical task')
        if int(self.get_param('task_logfatal')):
            self._logger.fatal('TEST log fatal during noncritical task')
        if int(self.get_param('shutdown_with_error')):
            await self.panic(Exception('TEST shutdown with error'))
        if int(self.get_param('kill_self')):
            os.kill(os.getpid(), signal.SIGKILL)
        if int(self.get_param('bad_sys_exit')):
            sys.exit(1)

    async def critical_task(self):
        """For generating different events in critical asyncio task.

        This should activate crash reporting subsystem
        """
        await asyncio.sleep(float(self.get_param('delay')))
        if int(self.get_param('crittask_exc')):
            raise Exception('TEST Exception during critical task')
        if int(self.get_param('crittask_logerror')):
            self._logger.error('TEST log error during critical task')
        if int(self.get_param('crittask_logfatal')):
            self._logger.fatal('TEST log fatal during critical task')

    async def _shutting_down(self):
        """For generating errors during Peer shutdown.

        You should initiate shutdown normally, using obci gui STOP button.
        """
        await asyncio.sleep(float(self.get_param('delay')))
        if int(self.get_param('shutdown_exc')):
            raise Exception('TEST Exception during shutdown')
        if int(self.get_param('shutdown_logerror')):
            self._logger.error('TEST log error during shutdown')
        if int(self.get_param('shutdown_logfatal')):
            self._logger.fatal('TEST log fatal during shutdown')
        await super()._shutting_down()
