# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.
import atexit
import configparser
import tempfile
from pathlib import Path

from braintech.obci.core.conf import settings
from ..peer.configured_peer import ConfiguredPeer
from ..launcher.launcher_tools import READY_TO_LAUNCH
from ..launcher.peer_loader import full_class_name
from ..peers.control.config_server import ConfigServer
from ..peers.drivers.amplifiers.amplifier_peer import SIGNAL_SOURCES
from braintech.obci.core.utils import openbci_logging as logger

LOGGER = logger.get_logger("DriverDiscovery", "info")


# noinspection PyUnresolvedReferences
def get_amp_classes_defs():
    amp_classes_defs = []
    settings.load_extensions()
    for AmplifierPeerClass in SIGNAL_SOURCES:
        if issubclass(AmplifierPeerClass, ConfiguredPeer):
            amp_classes_defs.append((AmplifierPeerClass.AmplifierClass, AmplifierPeerClass))
    return amp_classes_defs


_temp_scenarios_dir = None


def _create_scenario_config(amplifier_peer_class):
    class_name = full_class_name(amplifier_peer_class)
    scenario_config = configparser.ConfigParser()
    scenario_config['peers'] = {'scenario_path': ''}
    scenario_config['peers.config_server'] = {'path': full_class_name(ConfigServer)}
    scenario_config['peers.amplifier'] = {'path': class_name}
    return scenario_config


def _create_launch_file(amplifier_peer_class):
    global _temp_scenarios_dir
    if _temp_scenarios_dir is None:
        _temp_scenarios_dir = tempfile.TemporaryDirectory(prefix='obci_scenarios')
        atexit.register(_temp_scenarios_dir.cleanup)
    class_name = full_class_name(amplifier_peer_class)
    scenario_path = Path(_temp_scenarios_dir.name) / (class_name + '.ini')
    if not scenario_path.exists():
        scenario_config = _create_scenario_config(amplifier_peer_class)
        with scenario_path.open("w") as f:
            scenario_config.write(f)
    return str(scenario_path)


def find_amplifiers(device_type=None):
    descriptions = []
    for amp_class, ampilfier_peer_module in get_amp_classes_defs():
        try:
            amplifiers_ids = amp_class.get_available_amplifiers(device_type)
        except Exception as ex:
            LOGGER.warning("Discovery failed: {} \n Exception: {}"
                           .format(str(amp_class), ex))
            continue
        for amplifier_id in amplifiers_ids:
            try:
                channels_info = amp_class.get_description(amplifier_id).to_dict()
            except Exception as ex:
                LOGGER.warning("Discovery failed: {} ({}) \n Exception: {}"
                               .format(str(amp_class), amplifier_id, ex))
            else:
                scenario_file = _create_launch_file(ampilfier_peer_module)
                desc = {
                    'experiment_info': {
                        'launch_file_path': scenario_file,
                        'experiment_status': {
                            'status_name': READY_TO_LAUNCH
                        }
                    },
                    'amplifier_peer_info': {
                        'path': full_class_name(ampilfier_peer_module)
                    },
                    'amplifier_params': {
                        'channels_info': channels_info,
                        'additional_params': {
                            'amplifier_id': amplifier_id,
                        },
                        'active_channels': '',
                        'channel_names': '',
                        'sampling_rate': ''
                    },
                }
                descriptions.append(desc)
    return descriptions


def find_drivers():
    return find_amplifiers()


def find_usb_amps():
    return find_amplifiers('usb')


def find_bluetooth_amps():
    return find_amplifiers('bt')


def find_virtual_amps():
    return find_amplifiers('virtual')
