# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import os.path

from braintech.obci.core.conf import settings

OBCI_CONTROL_LOG_DIR = os.path.join(settings.log_dir, "control")

PORT_RANGE = settings.broker_port_range

OBCI_HOME_DIR = settings.home_dir
DEFAULT_SANDBOX_DIR = settings.sandbox_dir
DEFAULT_SCENARIO_DIR = settings.scenario_dir

INSTALL_DIR = settings.INSTALL_DIR
