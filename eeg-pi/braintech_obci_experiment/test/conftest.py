# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

# noinspection PyUnresolvedReferences
import pytest  # noqa

from braintech.obci.core.settings import OBCISettings
from braintech.obci.core.test.fixtures import *  # noqa
from braintech.obci.experiment.test.fixtures import *  # noqa
from braintech.obci.core.utils.openbci_logging import init_logging

LOGGING = OBCISettings.LOGGING
LOGGING['handlers']['console']['level'] = 'DEBUG'
init_logging(LOGGING)
