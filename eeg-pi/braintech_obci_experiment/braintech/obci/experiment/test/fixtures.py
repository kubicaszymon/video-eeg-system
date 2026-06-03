# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import subprocess
import sys
from subprocess import TimeoutExpired

import pytest

from braintech.obci.core import utils
from ..launcher.simple_obci_client import SimpleOBCIClient
from ..peers.acquisition.reusable_signal_saver_peer import ReusableSignalSaver
from ..peers.control.config_server import ConfigServer
from ..peers.drivers.amplifiers.random_amplifier_peer import RandomAmplifierPeer
from .tools import create_peer
from braintech.obci.core.utils import yield_then_shutdown, get_peer_config_file_path, is_windows


def pytest_configure(config):
    sys._called_from_test = True


def pytest_unconfigure(config):
    if hasattr(sys, '_called_from_test'):
        del sys._called_from_test


# https://docs.pytest.org/en/latest/example/simple.html#incremental-testing-test-steps
# Make test (in class marked as incremental) as xfail for each fixture id used
# Fixture used must be of scope='class' to work correctly
def pytest_runtest_makereport(item, call):
    if 'incremental' in item.keywords:
        parent = item.parent
        if not hasattr(parent, '_previousfailed'):
            parent._previousfailed = {}
        if call.excinfo is not None:
            parent._previousfailed[item._genid] = item


def pytest_runtest_setup(item):
    if 'incremental' in item.keywords:
        previousfailed = getattr(item.parent, '_previousfailed', {})
        if item._genid in previousfailed:
            pytest.xfail(
                'previous test failed ({})'.format(
                    previousfailed[item._genid].name
                )
            )


@pytest.fixture(scope='module')
def config_server(broker):
    yield from yield_then_shutdown(
        ConfigServer(
            broker.broker_ip,
            peer_id='config_server',
            base_config_file=get_peer_config_file_path(ConfigServer),
        )
    )


@pytest.fixture()
def xfwm():
    if is_windows():
        return
    process = subprocess.Popen(['xfwm4'])
    yield
    try:
        process.kill()
    except ProcessLookupError:
        pass


@pytest.fixture()
def ffmpeg_testsrc():
    process = subprocess.Popen('ffmpeg -f lavfi -re -i testsrc=rate=10 -f v4l2 -framerate 10 /dev/video0 -loglevel 8'
                               .split())
    yield
    process.kill()


@pytest.fixture()
def svarog():
    process = subprocess.Popen('svarog')
    yield
    process.kill()


@pytest.fixture()
def simple_obci_server():
    server = subprocess.Popen("simple_obci_server")
    client = SimpleOBCIClient()
    client.ping_server(3000)
    yield client
    client.srv_kill()
    try:
        server.wait(10.0)
    except TimeoutExpired:
        server.kill()
        raise


@pytest.fixture(scope='module')
def amplifier(broker, config_server):
    config = {
        'local_params': {
            'autostart': '1',
            'autoshutdown': '0',
        },
    }
    peer = create_peer(RandomAmplifierPeer, broker, name='amplifier',
                       dependencies=[config_server], config=config)
    yield from utils.yield_then_shutdown(peer)


@pytest.fixture
def reusable_signal_saver(broker, config_server, amplifier):
    config = {
        'local_params': {
            'autostart': '0',
            'autoshutdown': '0',
            'debug_on': '0',
        },
        'launch_dependencies': {
            'signal_source': amplifier.id,
        }
    }
    peer = create_peer(ReusableSignalSaver, broker, name='reusable_signal_saver',
                       dependencies=[config_server, amplifier], config=config)
    yield from utils.yield_then_shutdown(peer)
