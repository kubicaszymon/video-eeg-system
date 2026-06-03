# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import pathlib

import subprocess

from braintech.obci.core import utils
from braintech.obci.experiment.launcher import launcher_tools
from braintech.obci.experiment.test import tools as test_tools


_THIS_DIRECTORY = pathlib.Path(__file__).parent


def test_adding_and_removing_peer():
    scenario_path = _THIS_DIRECTORY / 'test_scenarios/amplifier.ini'
    subprocess.run(['obci', 'srv'], check=True)
    try:
        uuid = _launch_scenario(scenario_path)
        _add_peer(uuid)
        _remove_peer(uuid)
    finally:
        _clean_created_files()
        subprocess.run(['obci', 'srv_kill', '--force'], check=True)


def _launch_scenario(scenario_path):
    uuid = test_tools.launch(str(scenario_path))
    wait_for_experiment_status(uuid, launcher_tools.RUNNING)
    assert not _does_signal_saver_have_status(uuid)
    assert not _is_signal_saver_present(uuid)
    assert len(_get_created_files()) == 0
    return uuid


def _add_peer(uuid):
    config_path = (_THIS_DIRECTORY / '../../'
                   / 'braintech/obci/experiment/peers/acquisition/signal_saver_peer.py')
    # config_path = 'braintech.obci.experiment.peers.acquisition.signal_saver_peer'
    config_overwrites = [
        '--peer', 'signal_saver', '-c', 'signal_source', 'amplifier',
        '--peer', 'signal_saver', '-p', 'save_file_name', 'test_add_remove_peer',
    ]
    subprocess.run(['obci', 'add', uuid, str(config_path),
                    '--peer_id', 'signal_saver',
                    '--ovr'] + config_overwrites, check=True)
    utils.wait_for_condition(lambda: _is_signal_saver_present(uuid),
                             timeout=20)
    utils.wait_for_condition(lambda: _does_signal_saver_have_status(uuid))
    wait_for_experiment_status(uuid, launcher_tools.RUNNING)
    assert len(_get_created_files()) == 1


def _remove_peer(uuid):
    subprocess.run(['obci', 'remove', uuid, 'signal_saver'], check=True)
    utils.wait_for_condition(lambda: not _is_signal_saver_present(uuid),
                             timeout=20)
    utils.wait_for_condition(lambda: not _does_signal_saver_have_status(uuid))
    wait_for_experiment_status(uuid, launcher_tools.RUNNING)
    assert len(_get_created_files()) == 3


def wait_for_experiment_status(uuid, status: str):
    def does_status_match():
        info = test_tools.experiment_info(uuid)
        return info['experiment_status']['status_name'] == status

    utils.wait_for_condition(does_status_match)


def _clean_created_files():
    files = _get_created_files()
    for file in files:
        file.unlink()


def _get_created_files() -> [pathlib.Path]:
    return list(pathlib.Path.home().glob('test_add_remove_peer.*'))


def _is_signal_saver_present(experiment_uuid):
    info = test_tools.experiment_info(experiment_uuid)
    return 'signal_saver' in info['peers']


def _does_signal_saver_have_status(experiment_uuid):
    info = test_tools.experiment_info(experiment_uuid)
    return 'signal_saver' in info['experiment_status']['peers_status']
