# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Minimal Peer for tests."""

from braintech.obci.experiment.peer.configured_peer import ConfiguredPeer
from braintech.obci.core.utils import properties

__all__ = ('Slave',)


class Slave(ConfiguredPeer):
    """Minimalistic peer which fetch config parameters."""

    param_property = properties.param_property('param_property')
    local_set_query_param = properties.param_property('local_set_query_param')
