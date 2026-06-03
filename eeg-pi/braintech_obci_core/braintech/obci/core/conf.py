# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
import importlib
import os

from braintech.obci.core.settings import OBCISettings
from braintech.obci.core.utils.openbci_logging import init_logging

MAIN_CONFIG_NAME = 'obci_config.ini'
OBCI_HOME_DIR = '~/.obci'
OBCI_SETTINGS = 'OBCI_SETTINGS'


def get_settings_class(module_path):
    module = importlib.import_module(module_path)
    return getattr(module, 'settings_class')


SettingsClass = get_settings_class(os.environ.get(OBCISettings.ENV_VAR, 'braintech.obci.core.settings'))
settings = SettingsClass(os.path.join(OBCI_HOME_DIR, MAIN_CONFIG_NAME))  # type: OBCISettings

for dir in ['home_dir', 'scenario_dir', 'log_dir', 'sandbox_dir']:
    if not os.path.exists(getattr(settings, dir)):
        os.mkdir(getattr(settings, dir))

init_logging(settings.logging_config)
