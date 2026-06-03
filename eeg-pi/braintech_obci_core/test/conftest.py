# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

# noinspection PyUnresolvedReferences
import pytest

from braintech.obci.core.settings import OBCISettings
from braintech.obci.core.test.fixtures import *  # noqa
from braintech.obci.core.utils.openbci_logging import init_logging

LOGGING = OBCISettings.LOGGING
LOGGING['handlers']['console']['level'] = 'DEBUG'
init_logging(LOGGING)


@pytest.fixture(scope='session')
def broker_rep():
    yield 'tcp://127.0.0.1:20001'


@pytest.fixture(scope='session')
def broker_xpub():
    yield 'tcp://127.0.0.1:20002'


@pytest.fixture(scope='session')
def broker_xsub():
    yield 'tcp://127.0.0.1:20003'


@pytest.fixture(scope='session')
def peer_pub():
    yield 'tcp://127.0.0.1:*'


@pytest.fixture(scope='session')
def peer_rep():
    yield 'tcp://127.0.0.1:*'
