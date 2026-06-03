# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Package providing OBCI launcher Message types, converted from message template dicts."""
from braintech.obci.core.broker.messages.fields import Field
from .launcher_common_types import LauncherMessageBase


class PeerParamValuesMsg(LauncherMessageBase):
    __TYPE__ = 'peer_param_values'
    peer_id = Field(str)
    param_values = Field(dict)


class DeadProcessMsg(LauncherMessageBase):
    __TYPE__ = 'dead_process'
    status = Field(list, tuple)
    machine = Field(str)
    pid = Field(int)


class ProcessSupervisorRegisteredMsg(LauncherMessageBase):
    __TYPE__ = 'process_supervisor_registered'
    machine_ip = Field(str)


class ObciLaunchFailedMsg(LauncherMessageBase):
    __TYPE__ = 'obci_launch_failed'
    machine = Field(str)
    path = Field(str)
    args = Field(list, tuple)
    details = Field(str)


class SetExperimentScenarioMsg(LauncherMessageBase):
    __TYPE__ = 'set_experiment_scenario'
    launch_file_path = Field(str)
    scenario = Field(str)


class LaunchErrorMsg(LauncherMessageBase):
    __TYPE__ = 'launch_error'
    details = Field(dict)
    err_code = Field(str)


class KillPeerMsg(LauncherMessageBase):
    __TYPE__ = 'kill_peer'
    remove_config = Field(bool)
    peer_id = Field(str)


class AllPeersLaunchedMsg(LauncherMessageBase):
    __TYPE__ = 'all_peers_launched'
    machine = Field(str)


class LauncherShutdownMsg(LauncherMessageBase):
    __TYPE__ = 'launcher_shutdown'


class StartExperimentMsg(LauncherMessageBase):
    __TYPE__ = 'start_experiment'


class ManagePeersMsg(LauncherMessageBase):
    __TYPE__ = 'manage_peers'
    kill_peers = Field(list)
    start_peers_data = Field(dict)


class ObciPeerDeadMsg(LauncherMessageBase):
    __TYPE__ = 'obci_peer_dead'
    status = Field(tuple, list)
    path = Field(str)
    peer_id = Field(str)
    experiment_id = Field(str)


class KillPeerMorphMsg(LauncherMessageBase):
    __TYPE__ = '_kill_peer'
    machine = Field(str)
    peer_id = Field(str)
    morph = Field(str, bool)


class KillProcessMsg(LauncherMessageBase):
    __TYPE__ = 'kill_process'
    machine = Field(str)
    pid = Field(int)


class ExperimentStatusChangeMsg(LauncherMessageBase):
    __TYPE__ = 'experiment_status_change'
    peers = Field(dict, None)
    status_name = Field(str)
    uuid = Field(str)
    details = Field(dict, str)


class ExperimentCreatedMsg(LauncherMessageBase):
    __TYPE__ = 'experiment_created'
    launch_file_path = Field(str)
    rep_addrs = Field(list)  # List[str]
    status_name = Field(str)
    ip = Field(str)
    uuid = Field(str)
    pub_addrs = Field(list)  # List[str]
    origin_machine = Field(str)
    details = Field(str)
    name = Field(str)


class GetPeerInfoMsg(LauncherMessageBase):
    __TYPE__ = 'get_peer_info'
    peer_id = Field(str)


class KillExperimentMsg(LauncherMessageBase):
    __TYPE__ = 'kill_experiment'
    strname = Field(str)
    force = Field(bool)


class ConfigServerReadyMsg(LauncherMessageBase):
    __TYPE__ = 'config_server_ready'


class JoinExperimentMsg(LauncherMessageBase):
    __TYPE__ = 'join_experiment'
    path = Field(str, None)
    peer_type = Field(str)
    peer_id = Field(str)


class PeerInfoMsg(LauncherMessageBase):
    __TYPE__ = 'peer_info'
    peer_id = Field(str)
    external_params = Field(dict, None)
    peer_type = Field(str)
    machine = Field(str)
    local_params = Field(dict, None)
    launch_dependencies = Field(dict, None)
    path = Field(str)
    config_sources = Field(dict, None)


class RegisterPeerMsg(LauncherMessageBase):
    __TYPE__ = 'register_peer'
    pub_addrs = Field(list)  # List[str]
    uuid = Field(str)
    name = Field(str)
    peer_type = Field(str)
    other_params = Field(dict)
    rep_addrs = Field(list)  # List[str]


class ObciPeerReadyMsg(LauncherMessageBase):
    __TYPE__ = 'obci_peer_ready'
    peer_id = Field(str)


class GetPeerParamValuesMsg(LauncherMessageBase):
    __TYPE__ = 'get_peer_param_values'
    peer_id = Field(str)


class AddPeerMsg(LauncherMessageBase):
    __TYPE__ = 'add_peer'
    config_sources = Field(None, dict)
    peer_path = Field(str)
    peer_type = Field(str)
    machine = Field(str)
    param_overwrites = Field(dict)
    launch_dependencies = Field(dict, None)
    apply_globals = Field(bool)
    custom_config_path = Field(str, None)
    peer_id = Field(str)


class RemovePeerMsg(LauncherMessageBase):
    __TYPE__ = 'remove_peer'
    peer_id = Field(str)
    machine = Field(str)


class TailMsg(LauncherMessageBase):
    __TYPE__ = 'tail'
    txt = Field(str)
    peer_id = Field(str)
    experiment_id = Field(str)


class StopAllMsg(LauncherMessageBase):
    __TYPE__ = 'stop_all'


class ExperimentTransformationMsg(LauncherMessageBase):
    __TYPE__ = 'experiment_transformation'
    uuid = Field(str)
    old_launch_file = Field(str)
    name = Field(str)
    status_name = Field(str)
    old_name = Field(str)
    launch_file = Field(str)
    details = Field(str)


class GetExperimentInfoMsg(LauncherMessageBase):
    __TYPE__ = 'get_experiment_info'


class GetExperimentContactMsg(LauncherMessageBase):
    __TYPE__ = 'get_experiment_contact'
    strname = Field(str)


class ExperimentLaunchErrorMsg(LauncherMessageBase):
    __TYPE__ = 'experiment_launch_error'
    details = Field(str, dict)
    err_code = Field(str)


class ObciPeerUnregisteredMsg(LauncherMessageBase):
    __TYPE__ = 'obci_peer_unregistered'
    peer_id = Field(str)


class ObciControlMessageMsg(LauncherMessageBase):
    __TYPE__ = 'obci_control_message'
    launcher_message = Field(dict)
    severity = Field(str)
    peer_name = Field(str)
    params = Field(str)
    peer_type = Field(str)
    msg_code = Field(str)
    details = Field(str, dict)


class StartBrokerMsg(LauncherMessageBase):
    __TYPE__ = 'start_broker'
    args = Field(str)


class GetBrokerAddress(LauncherMessageBase):
    __TYPE__ = 'get_broker_address'


class LaunchedProcessInfoMsg(LauncherMessageBase):
    __TYPE__ = 'launched_process_info'
    machine = Field(str)
    name = Field(str)
    proc_type = Field(str)
    path = Field(str)
    args = Field(tuple, list)
    pid = Field(int)
    details = Field(str)


class SaveScenarioMsg(LauncherMessageBase):
    __TYPE__ = 'save_scenario'
    file_name = Field(str)
    force = Field(bool)


class FindEegAmplifiersMsg(LauncherMessageBase):
    __TYPE__ = 'find_eeg_amplifiers'
    amplifier_types = Field(list, tuple)
    client_push_address = Field(str)


class NearbyMachinesMsg(LauncherMessageBase):
    __TYPE__ = 'nearby_machines'
    nearby_machines = Field(dict)


class ExperimentInfoChangeMsg(LauncherMessageBase):
    __TYPE__ = 'experiment_info_change'
    launch_file_path = Field(str)
    name = Field(str)
    uuid = Field(str)


class GetTailMsg(LauncherMessageBase):
    __TYPE__ = 'get_tail'
    peer_id = Field(str)
    len = Field(str)


class ObciPeerParamsChangedMsg(LauncherMessageBase):
    __TYPE__ = 'obci_peer_params_changed'
    peer_id = Field(str)
    params = Field(dict)


class GetExperimentScenarioMsg(LauncherMessageBase):
    __TYPE__ = 'get_experiment_scenario'


class LaunchProcessMsg(LauncherMessageBase):
    __TYPE__ = 'launch_process'
    name = Field(str)
    proc_type = Field(str)
    stderr_log = Field(str, None)
    args = Field(list, tuple)
    machine_ip = Field(str)
    stdout_log = Field(str, None)
    path = Field(str, None)
    capture_io = Field(str, int)


class EegAmplifiersMsg(LauncherMessageBase):
    __TYPE__ = 'eeg_amplifiers'
    amplifier_list = Field(list, tuple)


class BrokerStartedMsg(LauncherMessageBase):
    __TYPE__ = 'broker_started'
    uuid = Field(str)
    address = Field(str)


class NewPeerAddedMsg(LauncherMessageBase):
    __TYPE__ = 'new_peer_added'
    machine = Field(str)
    peer_id = Field(str)
    uuid = Field(str)
    peer_path = Field(str)
    status_name = Field(str)
    config = Field(str)


class KillSentMsg(LauncherMessageBase):
    __TYPE__ = 'kill_sent'
    experiment_id = Field(str)


class StartPeersMsg(LauncherMessageBase):
    __TYPE__ = 'start_peers'
    mx_data = Field(list)
    add_launch_data = Field(str)


class StartConfigServerMsg(LauncherMessageBase):
    __TYPE__ = 'start_config_server'
    restore_config = Field(str)
    args = Field(list)
    mx_data = Field(list)


class StartingExperimentMsg(LauncherMessageBase):
    __TYPE__ = 'starting_experiment'


class LeaveExperimentMsg(LauncherMessageBase):
    __TYPE__ = 'leave_experiment'
    path = Field(str, None)
    peer_type = Field(str)
    peer_id = Field(str)


class UpdatePeerConfigMsg(LauncherMessageBase):
    __TYPE__ = 'update_peer_config'
    launch_dependencies = Field(dict, None)
    local_params = Field(dict, None)
    peer_id = Field(str)
    external_params = Field(dict, None)
    config_sources = Field(dict, None)


class ExperimentFinishedMsg(LauncherMessageBase):
    __TYPE__ = 'experiment_finished'
    details = Field(str)


class ExperimentContactMsg(LauncherMessageBase):
    __TYPE__ = 'experiment_contact'
    rep_addrs = Field(list)  # List[str]
    status_name = Field(str)
    uuid = Field(str)
    machine = Field(str)
    pub_addrs = Field(list)  # List[str]
    details = Field(str, dict)
    name = Field(str)


class MorphToNewScenarioMsg(LauncherMessageBase):
    __TYPE__ = 'morph_to_new_scenario'
    leave_on = Field(str)
    overwrites = Field(str)
    name = Field(str)
    launch_file = Field(str)


class StartEegSignalMsg(LauncherMessageBase):
    __TYPE__ = 'start_eeg_signal'
    amplifier_params = Field(dict)
    name = Field(str)
    client_push_address = Field(str)
    launch_file = Field(str)


class ExperimentScenarioMsg(LauncherMessageBase):
    __TYPE__ = 'experiment_scenario'
    launch_file_path = Field(str)
    uuid = Field(str)
    scenario = Field(str)


class ObciPeerRegisteredMsg(LauncherMessageBase):
    __TYPE__ = 'obci_peer_registered'
    peer_id = Field(str)
    params = Field(dict)


class ExperimentInfoMsg(LauncherMessageBase):
    __TYPE__ = 'experiment_info'
    status = Field(str)
    launch_file_path = Field(str)
    peers = Field(dict)
    experiment_status = Field(dict)
    name = Field(str)
    unsupervised_peers = Field(dict)
    origin_machine = Field(str)
    scenario_dir = Field(str)
    uuid = Field(str, None)
