# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.
import os
import signal
import subprocess
import sys
import threading

from braintech.obci.core.utils import is_windows
from . import process
from .process import FAILED, FINISHED, TERMINATED, NON_RESPONSIVE, \
    PING, RETURNCODE, REG_TIMER
from .process_io_handler import DEFAULT_TAIL_RQ


class LocalProcess(process.Process):

    def __init__(self, proc_description, popen_obj, io_handler=None,
                 reg_timeout_desc=None,
                 monitoring_optflags=PING | RETURNCODE,
                 logger=None):
        self.popen_obj = popen_obj
        self.io_handler = io_handler

        super(LocalProcess, self).__init__(proc_description,
                                           reg_timeout_desc, monitoring_optflags,
                                           logger)

    def is_local(self):
        return True

    def _do_handle_timeout(self, type_):
        if type_ == REG_TIMER:
            with self._status_lock:
                self._status = FAILED
                self._status_details = "Failed to register before timeout."

            self.kill()

    def tail_stdout(self, lines=DEFAULT_TAIL_RQ):
        if not self.io_handler:
            return None
        else:
            return self.io_handler.tail_stdout(int(lines))

    def _pre_kill(self):
        self.stop_monitoring()
        if self.io_handler is not None:
            if self.io_handler.is_running():
                self.io_handler.stop_output_handler()

    def _do_killing(self, force=False):
        self.popen_obj.poll()
        if self.popen_obj.returncode is None:
            if force:
                self.logger.debug("KILLING %s %s", self.pid, self.name)
                self.popen_obj.kill()
            else:
                if sys.platform == "win32":
                    self.logger.debug("closing stdin of %s %s", self.name, self.pid)
                    self.popen_obj.stdin.close()
                else:
                    self.logger.debug("sending sigterm %s %s", self.name, self.pid)
                    self.popen_obj.terminate()

    def kill(self, force=False):
        self._pre_kill()
        self._do_killing(force=force)
        self.popen_obj.wait()
        self._update_status()

    def kill_with_force(self):
        self.kill(force=True)

    def _update_status(self) -> None:
        """Update status of this process based on return code or NON_RESPONSIVE status."""
        code = self.popen_obj.poll()
        if code is not None:
            self.logger.info(self.proc_type + " process " + self.name +
                             " pid " + str(self.pid) + " ended with " + str(code))
            with self._status_lock:
                if code == 0:
                    self._status = FINISHED
                    self._status_details = ''
                elif code < 0:
                    self._status = TERMINATED
                    self._status_details = -code
                else:
                    self._status = FAILED
                    self._status_detals = self.tail_stdout(15)
        elif self.status()[0] == NON_RESPONSIVE:
            self.logger.fatal(self.proc_type + "process" + self.name +
                              "pid" + self.pid + "is NON_RESPONSIVE")
            with self._status_lock:
                self.popen_obj.poll()
                if self.popen_obj.returncode is None:
                    self.popen_obj.terminate()
                    self._status = TERMINATED

    def returncode_monitor(self):
        while not self._stop_monitoring:
            try:
                self.popen_obj.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass
            self._update_status()
            status, _ = self.status()
            if status in (FINISHED, TERMINATED, FAILED):
                break

    def finished(self):
        finished = True
        if self._ping_thread is not None:
            finished = not self._ping_thread.is_alive()
        if self._returncode_thread is not None:
            finished = not self._returncode_thread.is_alive()
        return finished and self.popen_obj.returncode is not None

    def process_is_running(self):
        running = True
        if self._ping_thread is not None:
            running = self._ping_thread.is_alive()
        if self._returncode_thread is not None:
            running = running and self._returncode_thread.is_alive()
        return running and self.popen_obj.returncode is None

    @staticmethod
    def install_kill_handler(handler, logger=None):
        if is_windows():
            def _wait_for_stdin_close():
                try:
                    sys.stdin.read()
                finally:
                    if logger:
                        logger.info("Stdin closed. Calling handler")
                    handler()

            threading.Thread(target=_wait_for_stdin_close, daemon=True, name="ClosingThread").start()
        else:
            def _handler(signum, stackframe):
                if logger:
                    logger.info("Signal %d received. Calling handler", signum)
                handler()

            for s in [signal.SIGTERM, signal.SIGINT]:
                signal.signal(s, _handler)


class LocalThreadedProcess(LocalProcess):
    def __init__(self, proc_description, io_handler=None,
                 reg_timeout_desc=None,
                 logger=None):
        proc_description.pid = os.getpid()
        self._thread = threading.Thread(target=self._run, name=proc_description.name, daemon=True)
        self._thread.returncode = None
        super(LocalThreadedProcess, self).__init__(proc_description, self._thread, io_handler=io_handler,
                                                   reg_timeout_desc=reg_timeout_desc,
                                                   monitoring_optflags=0,
                                                   logger=logger)
        self._thread.start()

    def _create_peer(self):
        raise NotImplemented

    def _run(self):
        try:
            self._peer = self._create_peer()
            self._peer.run()
        except Exception:
            self._thread.returncode = 1
            raise
        else:
            self._thread.returncode = 0

    def kill(self, force=False):
        self._peer.shutdown()
        self._thread.join()
        self._status = FINISHED

    def finished(self):
        return self._thread.returncode is not None

    def process_is_running(self):
        return self._thread.returncode is None
