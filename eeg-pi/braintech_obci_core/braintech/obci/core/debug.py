# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""
We recommend following tools for BCI-Framework debugging:

* PyCharm
* ``install_debug_handler()`` defined in this file

To connect to existing processes with PyCharm or Pyrasite
you need to run is you have a kernel biult with
CONFIG_SECURITY_YAMA option:

``echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope``

and install ``python3-dbg`` package.
"""


def install_debug_handler() -> None:
    """
    Break into a Python console upon:

    * ``SIGUSR1`` (Linux), use: ``kill -SIGUSR1 [pid]`` command
    * ``SIGBREAK`` (Windows: CTRL+Pause/Break)
    """
    def debug_signal_handler(signal, frame):
        del signal
        del frame

        # NOTE: Following debuggers were tested and don't
        #       work with Python3 based BCI-Framework, so don't
        #       waste your time on them.
        #  - RPDB2/Winpdb
        #  - Pyrasite

        try:
            import pudb
            pudb.set_trace()
        except Exception:
            pass

        try:
            import code
            code.interact()
        except Exception as ex:
            print("%r, returning to normal program flow" % ex)

    try:
        import signal
        signal.signal(
            vars(signal).get('SIGBREAK') or vars(signal).get('SIGUSR1'),
            debug_signal_handler
        )
    except ValueError:
        # Typically: ValueError: signal only works in main thread
        pass
