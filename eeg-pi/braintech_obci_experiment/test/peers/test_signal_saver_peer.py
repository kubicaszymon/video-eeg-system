# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import pytest

from braintech.obci.experiment.peers.acquisition.signal_saver_peer import SignalSaver
from braintech.obci.experiment.peers.drivers.amplifiers.random_amplifier_peer import RandomAmplifierPeer
from braintech.obci.core.utils import wait_until_peers_ready, yield_test_peer


@pytest.fixture()
def amplifier(broker, config_server):
    config = {
        'local_params': {
            'autostart': '1',
            'autoshutdown': '0',
            'sampling_rate': '128',
        },
    }
    yield from yield_test_peer(RandomAmplifierPeer, 'amplifier_id', 'amplifier', config, broker, config_server)


@pytest.fixture()
def signal_saver(broker, config_server, amplifier):
    config = {
        'local_params': {
            'autostart': '0',
            'autoshutdown': '0',
            'debug_on': '1'
        },
        'config_sources': {
            'signal_source': amplifier.peer_id,
        }
    }
    yield from yield_test_peer(SignalSaver, 'signal_saver_id', 'signal_saver', config, broker, config_server)


def test_signal_saver(broker, config_server, amplifier, signal_saver):
    """Test normal lifecycle for SignalSaver Peer."""
    wait_until_peers_ready([config_server, broker, amplifier, signal_saver])
    signal_saver.start()

    signal_saver.stop()
    signal_saver.start()
    signal_saver.shutdown()
