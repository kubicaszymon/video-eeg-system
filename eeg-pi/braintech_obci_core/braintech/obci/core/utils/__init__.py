# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import inspect
import os.path
import sys
import time
from typing import Iterable, Callable

from braintech.obci.core.broker import ObciException

DEFAULT_TIMEOUT = 1000000.0
DEFAULT_SLEEP_DURATION = 0.05


class TimeoutException(ObciException):
    pass


def wait_for_condition(condition_func: Callable[[], bool],
                       timeout: float = DEFAULT_TIMEOUT,
                       sleep_duration: float = DEFAULT_SLEEP_DURATION) -> None:
    start_time = time.monotonic()
    while not condition_func():
        time.sleep(sleep_duration)
        if time.monotonic() - start_time > timeout:
            condition_source = inspect.getsource(condition_func)
            raise TimeoutException('Timeout reached (={} seconds) for condition: {}'
                                   .format(timeout, condition_source))


def wait_until_peers_ready(peers_list: Iterable['BasePeer'],
                           timeout: float = DEFAULT_TIMEOUT) -> None:
    base_peers_list = list(peers_list)

    def are_all_ready():
        return all(p.is_ready for p in base_peers_list)

    wait_for_condition(are_all_ready, timeout=timeout)


def yield_then_shutdown(peer):
    yield peer
    peer.shutdown()


def get_peer_config_file_path(peer_class):
    path, _ = os.path.splitext(sys.modules[peer_class.__module__].__file__)
    return path + '.ini'


def yield_test_peer(peer_class, id, name, config, broker, config_server):
    """Yield peer of given class, in test environment with broker and config_server."""
    wait_until_peers_ready([config_server, broker], timeout=60.0)
    peer = peer_class(urls=broker.broker_ip, peer_id=id, peer_name=name,
                      base_config_file=get_peer_config_file_path(peer_class),
                      **config)
    yield peer
    peer.shutdown()


def is_windows():
    return os.name == 'nt'


def is_posix():
    return os.name == 'posix'
