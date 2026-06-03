# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Utility functions for braintech.obci.core.control.launcher package."""
import logging
import os
import os.path
import pathlib
import re

from braintech.obci.core.conf import settings
from . import process

NOT_READY = 'not_ready'
READY_TO_LAUNCH = 'ready_to_launch'
LAUNCHING = 'launching'
FAILED_LAUNCH = 'failed_launch'
RUNNING = 'running'
STOPPING = 'stopping'
FINISHED = 'finished'
FAILED = 'failed'
TERMINATED = 'terminated'

EXP_STATUSES = [NOT_READY, READY_TO_LAUNCH, LAUNCHING,
                FAILED_LAUNCH, RUNNING, STOPPING, FINISHED, FAILED, TERMINATED]

POST_RUN_STATUSES = [FINISHED, FAILED, TERMINATED, FAILED_LAUNCH]
RUN_STATUSES = [LAUNCHING, RUNNING]

PROCESS_TO_LAUNCHER_STATUS = {
    process.FINISHED: FINISHED,
    process.FAILED: FAILED,
    process.TERMINATED: TERMINATED,
}

_THIS_DIR = pathlib.Path(__file__).absolute().parent
OBCI_ROOT_DIR = _THIS_DIR.parent.parent

logger = logging.getLogger(__name__)


class ExperimentStatus:

    def __init__(self):
        self.status_name = NOT_READY
        self.details = {}
        self.peers_status = {}

    def set_status(self, status_name, details=None):
        self.status_name = status_name
        self.details = details or {}

    def as_dict(self):
        d = dict(status_name=self.status_name,
                 details=self.details,
                 peers_status={})
        for peer_id, st in self.peers_status.items():
            d['peers_status'][peer_id] = st.as_dict()
        return d

    def peer_status(self, peer_id):
        return self.peers_status.get(peer_id, None)

    def peer_status_exists(self, status_name):
        return status_name in [st.status_name for st in list(self.peers_status.values())]

    def del_peer_status(self, peer_id):
        del self.peers_status[peer_id]


class PeerStatus:

    def __init__(self, peer_id, status_name=NOT_READY):
        self.peer_id = peer_id
        self.status_name = status_name
        self.details = {}

    def set_status(self, status_name, details=()):
        self.status_name = status_name
        self.details = details

    def as_dict(self):
        return dict(peer_id=self.peer_id, status_name=self.status_name,
                    details=self.details)


def obci_root():
    return str(OBCI_ROOT_DIR)


def obci_root_relative(path):
    _path = pathlib.Path(path)
    if _path == OBCI_ROOT_DIR:
        same_dir_exceptional_result = ''
        return same_dir_exceptional_result
    else:
        try:
            relative = _path.relative_to(OBCI_ROOT_DIR)
        except ValueError:
            logger.warning('Tried to make unrelated path relative: %s',
                           path)
            return path
        else:
            return str(relative)


def broker_path():
    """ Used only in obci_process_supervisor.py and supervisor_test.py """
    if which('obci_broker'):
        return which('obci_broker')
    else:
        return str(OBCI_ROOT_DIR / 'bin' / 'obci_broker')


def module_path(module):
    path = module.__file__
    path = '.'.join([path.rsplit('.', 1)[0], 'py'])
    return os.path.normpath(path)


def expand_path(program_path, base_dir=None):
    if not program_path:
        return program_path
    if base_dir is None:
        search_paths = settings.search_paths
    else:
        search_paths = [base_dir]

    program_path = os.path.normpath(program_path)
    program_path = os.path.expanduser(program_path)

    if os.path.isabs(program_path) and os.path.exists(program_path):
        return program_path
    for p in search_paths:
        obcip = os.path.realpath(os.path.join(p, program_path))
        if os.path.exists(obcip):
            return obcip
    if which(program_path):
        return which(program_path)
    else:
        return program_path


def default_config_path(peer_program_path):
    from braintech.obci.experiment.launcher import peer_loader
    return peer_loader.default_config_path(peer_program_path)


def which(file):
    for path in os.environ["PATH"].split(os.pathsep):
        if os.path.exists(os.path.join(path, file)):
            return os.path.join(path, file)
    return None


UBUNTU_INSTALATION_PATH_PREFIX = '/usr/lib/python3/dist-packages/'


def get_system_path_prefix():
    """Return system obci package installation prefix."""
    return UBUNTU_INSTALATION_PATH_PREFIX


def is_builtin_scenario(scenario_path) -> bool:
    """Return true if given obci scenario is builtin, else otherwise."""
    return bool(
        re.match(
            get_system_path_prefix() + '.+',
            expand_path(scenario_path)
        )
    )
