# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.
import sys

from braintech.obci.core.conf import settings
from braintech.obci.core.broker.peer import Peer
from braintech.obci.core.utils.openbci_logging import enable_handlers
from braintech.obci.core.utils.parent_checking import ParentCheckingThread
from braintech.obci.experiment.error_reporting import install_sentry

from ..launcher.local_process import LocalProcess
from ..launcher.peer_loader import get_peer_class

PEER_RUN_CHECK_INTERVAL = 0.1


class MissingArgument(Exception):
    pass


class MissingPeer(Exception):
    pass


def run_new_peer(cls):
    argv = sys.argv[1:] + ['--broker-ip', settings.broker_address]
    ParentCheckingThread().start()
    peer = cls.create_peer(argv)

    def graceful_stop_signal_handler():
        try:
            peer.shutdown(0)
        except TimeoutError:
            pass

    LocalProcess.install_kill_handler(graceful_stop_signal_handler, peer._logger)

    peer.run()


def run():
    install_sentry()
    enable_handlers(['broker'])
    try:
        peer_module_path = sys.argv[1]
    except IndexError:
        raise MissingArgument('No Python module path for peer specified.')
    # remove obci_run_peer entry point from argv
    sys.argv.pop(0)
    peer_class = get_peer_class(peer_module_path)
    is_correct_peer = (peer_class is not None
                       and issubclass(peer_class, Peer))
    if is_correct_peer:
        run_new_peer(peer_class)
    else:
        raise MissingPeer('No peer is defined in the specified module.')
