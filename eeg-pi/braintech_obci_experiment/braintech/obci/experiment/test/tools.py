# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Module for common functions used in integration tests."""
import json
import re
import subprocess
import uuid
from contextlib import contextmanager
from unittest import mock

from braintech.obci.core import utils


def experiment_info(experiment_uuid: str, peer_id: str = None) -> dict:
    if peer_id:
        assert experiment_uuid, 'experiment_uuid must be supplied for peer_id to work'
        args = ['obci', 'info', experiment_uuid, peer_id]
    else:
        args = ['obci', 'info', experiment_uuid]
    output = subprocess.check_output(args).decode('utf-8')
    return json.loads(output.split('^^', maxsplit=1)[1].rstrip('\nNone'))


def experiments_uuids() -> list:
    """Return uuids for all running experiments."""
    output = subprocess.check_output(['obci', 'info']).decode('utf-8')
    uuids = [
        match.groupdict()['uuid']
        for match in re.finditer('uuid:  (?P<uuid>(\w+-){4}\w+)', output)
        if match is not None
    ]
    return uuids


def launch(scenario_path: str, overwrites: tuple = (), name=None) -> str:
    """Launch obci scenario and return it's name (used as id)."""
    name = name or uuid.uuid4().hex
    command = ['obci', 'launch', scenario_path, '--name', name]
    if overwrites:
        command += ['--ovr'] + list(overwrites)
    subprocess.run(command)
    return name


@contextmanager
def disable_sampling_rate_check():
    with mock.patch('braintech.obci.core.drivers.eeg.eeg_amplifier.AmplifierDescription.is_sampling_rate_valid',
                    return_value=True):
        yield


def create_peer(cls, broker, name, dependencies, config=None):
    if config is None:
        config = {}
    for dependency in dependencies:
        utils.wait_until_peers_ready([broker, dependency], timeout=3)
    config_path = utils.get_peer_config_file_path(cls)
    return cls(
        urls=broker.broker_ip,
        peer_id='{}_id'.format(name),
        peer_name=name,
        base_config_file=config_path,
        **config,
    )
