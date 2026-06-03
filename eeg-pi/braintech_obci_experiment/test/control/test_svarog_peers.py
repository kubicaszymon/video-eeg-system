# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.
import os
import pathlib
import time

import pytest

from braintech.obci.experiment.launcher import launcher_tools, svarog_peers
from braintech.obci.experiment.launcher.simple_obci_client import SimpleOBCIClient
from braintech.obci.experiment import messages
from braintech.obci.experiment.messages import SvarogSavingSignalError


def _setup_session(client, signal_filename, wait_for_starting=True):
    scenario_filename = str(pathlib.Path(__file__).parent
                            / 'basic_random_amplifier.ini')
    start = messages.StartEegSignalMsg(
        amplifier_params={'additional_params': {}},
        name="aaa",
        client_push_address="",  # We don't need get notified
        launch_file=scenario_filename
    )
    client.server_req(start)
    experiment_id = _wait_until_experiment_running(client, 'aaa')

    message = messages.SvarogStartSavingSignal(
        experiment_id=experiment_id,
        signal_source_id='amplifier',
        save_tags=True,
        signal_filename=signal_filename,
    )

    response, details = client.server_req(message)
    if not wait_for_starting:
        return response, details
    assert response.type == 'svarog_saving_signal_starting', details
    saving_session_id = response.saving_session_id

    status = _check_status(client, saving_session_id)
    assert status == svarog_peers.Status.INITIALIZATION.value
    return saving_session_id


def test_running_saving_session_without_video_saver(simple_obci_server: SimpleOBCIClient, tmpdir):
    client = simple_obci_server
    signal_filename = tmpdir.join('test.raw')
    saving_session_id = _setup_session(simple_obci_server, str(signal_filename))
    _wait_until_saving_state(client, saving_session_id,
                             svarog_peers.Status.SAVING.value)

    _wait_until_saving_state(client, saving_session_id,
                             svarog_peers.Status.SAVING.value)
    message = messages.SvarogFinishSavingSignal(
        saving_session_id=saving_session_id,
    )
    message.send(client.server_req_socket)
    response, details = client.poll_recv(client.server_req_socket, 4000)
    assert response.type == 'svarog_saving_signal_finishing', details
    assert response.saving_session_id == saving_session_id

    status = _check_status(client, saving_session_id)
    assert status in [svarog_peers.Status.FINISHING.value,
                      svarog_peers.Status.FINISHED.value]

    _wait_until_saving_state(client, saving_session_id,
                             svarog_peers.Status.FINISHED.value)


@pytest.mark.timeout(60)
def test_running_saving_session_with_error(simple_obci_server: SimpleOBCIClient, tmpdir):
    client = simple_obci_server
    if os.environ.get('CI'):
        wrong_path = "/proc/wrong_path"
    else:
        wrong_path = '/.../../wrong_path'

    response, details = _setup_session(client, wrong_path, wait_for_starting=False)

    while True:
        if isinstance(response, SvarogSavingSignalError):
            assert any(('not writable' in values) for values in response.details.values())
            return
        else:
            time.sleep(0.5)


def _wait_until_experiment_running(client, name) -> str:
    while True:
        response = client.get_experiment_details(name)
        response_data = response.dict()
        if 'experiment_status' in response_data:
            experiment_status = response_data['experiment_status']['status_name']
            if experiment_status == launcher_tools.RUNNING:
                break
        time.sleep(0.5)
    assert experiment_status == launcher_tools.RUNNING
    experiment_id = response_data['uuid']
    return experiment_id


def _wait_until_saving_state(client, saving_session_id, state_value: str):
    saving_status = None
    while saving_status != state_value:
        saving_status = _check_status(client, saving_session_id)
        time.sleep(0.5)


def _check_status(client, saving_session_id) -> str:
    message = messages.SvarogCheckSavingSignalStatus(
        saving_session_id=saving_session_id,
    )
    response, details = client.server_req(message, 4000)
    assert response.type == 'svarog_saving_signal_status', details
    assert response.saving_session_id == saving_session_id
    return response.status
