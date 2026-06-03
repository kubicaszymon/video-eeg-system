# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import logging

import zmq

from ..common.message import PollingObject
from braintech.obci.core.broker import messages as messages_core
from braintech.obci.experiment import messages

from . import process
from .process import FAILED, TERMINATED, PING, RETURNCODE, REG_TIMER

logger = logging.getLogger(__name__)


class RemoteProcess(process.Process):
    def __init__(self, proc_description, rq_address,
                 reg_timeout_desc=None,
                 monitoring_optflags=PING,
                 logger=None):
        self.rq_address = rq_address
        self._ctx = None
        # returncode monitoring is not supported in remote processes..
        monitoring_optflags = monitoring_optflags & ~(1 << RETURNCODE)
        super(RemoteProcess, self).__init__(proc_description,
                                            reg_timeout_desc, monitoring_optflags,
                                            logger)

    def is_local(self):
        return False

    def _do_handle_timeout(self, type_):
        if type_ == REG_TIMER:
            self._status = FAILED
            self._status_details = "Failed to register before timeout."

    def registered(self, reg_data):
        super(RemoteProcess, self).registered(reg_data)
        self.desc.pid = reg_data.pid

    def returncode_monitor(self):
        pass

    def kill(self):
        # send "kill" to the process or kill request to its supervisor?
        self.stop_monitoring()
        if not self._ctx:
            self._ctx = zmq.Context()
        rq_sock = self._ctx.socket(zmq.REQ)
        try:
            rq_sock.connect(self.rq_address)
            poller = PollingObject()
            messages.KillProcessMsg(
                pid=self.pid,
                machine=self.machine_ip,
            ).send(rq_sock)
            res, _ = poller.poll_recv(rq_sock, timeout=5000)
        finally:
            rq_sock.close()
        if res:
            res = messages_core.deserialize(res)
            logger.info("Response to kill request: %s", res)
            with self._status_lock:
                self._status = TERMINATED
