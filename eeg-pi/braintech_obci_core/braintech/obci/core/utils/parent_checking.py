# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Module providing thread which checks if its parent has changed(died)."""
import os
import signal
import threading
import time

import psutil


class ParentCheckingThread(threading.Thread):
    """Thread which checks if it's parent is alive."""

    def __init__(self, gracefull_delay=0, name=""):
        """
        Create a separate thread to control whether parent of the current process is alive.

        If at any later time, parent of the current process dies, the current process will be terminated.
        This thread will be daemonized.
        """
        super().__init__(target=self._loop, daemon=True, name=name + "ParentCheckingThread")
        self.initial_parent_pid = os.getppid()
        self._gracefull_delay = gracefull_delay

    def _loop(self):
        """Used as thread target."""
        while psutil.pid_exists(self.initial_parent_pid):
            time.sleep(0.5)  # required
        if self._gracefull_delay:
            os.kill(os.getpid(), signal.SIGINT)
            time.sleep(self._gracefull_delay)
        # If parent (ex Experiment) disappears child (peer) has no way to exit gracefully
        os.kill(os.getpid(), signal.SIGKILL)
