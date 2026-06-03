# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
from pathlib import Path

import pytest

import braintech.obci.experiment
from braintech.obci.experiment.launcher import peer_loader
from braintech.obci.experiment.launcher.system_config import OBCISystemConfigError
from braintech.obci.experiment.peers.acquisition.signal_saver_peer import SignalSaver


def test_peer_loader():
    assert peer_loader.full_class_name(SignalSaver) == ("braintech.obci.experiment.peers.acquisition."
                                                        "signal_saver_peer.SignalSaver")
    config_file = Path(braintech.obci.experiment.__file__).parent / 'peers/acquisition/signal_saver_peer.ini'
    for peer_path in [
        "braintech.obci.experiment.peers.acquisition.signal_saver_peer.SignalSaver",
        "braintech.obci.experiment.peers.acquisition.signal_saver_peer",
        "peers/acquisition/signal_saver_peer.py"
    ]:
        assert peer_loader.normalize_path(peer_path) == ("braintech.obci.experiment.peers.acquisition."
                                                         "signal_saver_peer.SignalSaver"
                                                         )
        assert peer_loader.validate_path(peer_path)
        assert Path(peer_loader.default_config_path(peer_path)) == config_file
    with pytest.raises(ImportError):
        peer_loader.validate_path("peers/acquisition/abcd.py")
    with pytest.raises(ImportError):
        peer_loader.validate_path("peers.acquisition.abcd")
    with pytest.raises(OBCISystemConfigError):
        peer_loader.validate_path("braintech.obci.experiment.peers.acquisition")
