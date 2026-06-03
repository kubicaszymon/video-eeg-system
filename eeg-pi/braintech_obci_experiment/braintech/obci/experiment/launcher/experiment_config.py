# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import logging

from ..common import obci_control_settings as settings

from . import launch_file_parser
from . import launcher_tools

logger = logging.getLogger('launcher.experiment_config')


def make(exp_config, launch_file, status, overwrites=None):
    launch_parser = launch_file_parser.LaunchFileParser(
        launcher_tools.obci_root(), settings.DEFAULT_SCENARIO_DIR)
    if not launch_file:
        return False, "Empty scenario."
    try:
        with open(launcher_tools.expand_path(launch_file)) as f:
            logger.info("launch file opened " + launch_file)
            launch_parser.parse(f, exp_config, apply_globals=True)
        if overwrites:
            for [ovr, other] in overwrites:
                exp_config.update_peer_config(other['peer_id'], ovr)
                if other['config_file']:
                    for f in other['config_file']:
                        exp_config.file_update_peer_config(other['peer_id'], f)
    except Exception as e:
        logger.error("Launch file invalid: %s", launch_file, exc_info=True)
        status.set_status(launcher_tools.FAILED_LAUNCH, details=str(e))
        return False, str(e)

    rd, details = exp_config.config_ready()
    if rd:
        status.set_status(launcher_tools.READY_TO_LAUNCH)
    else:
        status.set_status(launcher_tools.NOT_READY, details=details)
        logger.critical("Config not ready..." + str(details))
    return True, None
