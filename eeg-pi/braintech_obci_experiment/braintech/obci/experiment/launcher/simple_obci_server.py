# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import logging
import os.path
import threading

import time
import uuid
from functools import wraps

import zmq

import braintech.obci.core
from braintech.obci.experiment.error_reporting import install_sentry

from ..common.obci_control_settings import DEFAULT_SANDBOX_DIR
from braintech.obci.core.control.common import net
from ..common.message import send_msg, PollingObject
from . import constants as launcher_constants
from .amplifier_finder import find_new_experiments_and_push_results
from .obci_control_peer import OBCIControlPeer
from .obci_experiment import OBCIExperiment, LocalOBCIExperiment
from .obci_server_peer import OBCIServerPeer
from .subprocess_monitor import SubprocessMonitor
from ..peer import peer_cmd
from ..peer.config_defaults import CONFIG_DEFAULTS
from braintech.obci.core.broker import messages as messages_core
from braintech.obci.experiment import messages
from ..peer.configured_peer import ConfiguredMixin
from braintech.obci.core.utils.openbci_logging import log_crash
from braintech.obci.core.utils.parent_checking import ParentCheckingThread
from . import svarog_peers

REGISTER_TIMEOUT = 6
EXPERIMENT_PROCESS_CHECK_INTERVAL = 0.1
LOG_TO_TEXTFILE = False


def check_network_ready(func):
    @wraps(func)
    def wrapper(self, message, sock):
        if self._check_network(sock):
            return func(self, message, sock)

    return wrapper


class SimpleOBCIServer(OBCIControlPeer):
    msg_handlers = OBCIControlPeer.msg_handlers.copy()
    CAPABILITIES = ['online_amplifiers']

    @log_crash
    def __init__(self, rep_addresses=None, pub_addresses=None, name='obci_server'):

        # adding new logging
        self.uuid = str(uuid.uuid4())  # unique identifier
        self._init_logger(name)
        self.experiments = {}
        self.exp_process_supervisors = {}
        super(SimpleOBCIServer, self).__init__(None, rep_addresses,
                                               pub_addresses,
                                               name)

        self.machine = net.gethostname()
        self.svarog_peers_runner = svarog_peers.Runner(
            experiments=self.experiments,
            machine=self.machine,
            zmq_context=self.ctx,
        )
        self.rep_port = int(net.server_rep_port())
        self.pub_port = int(net.server_pub_port())
        self.subprocess_mgr = SubprocessMonitor(self.ctx, self.uuid, logger=self.logger)
        self._experiment_created = threading.Event()

    def _init_logger(self, name):
        self.logger = logging.getLogger('obci_server.{}'.format(self.uuid[:8]))
        version = braintech.obci.core.__version__
        self.logger.info('Starting obci_server (obci version {})'.format(version))

    def nearby_servers(self):
        return {}

    def my_ip(self):
        addr = "127.0.0.1"
        return addr

    def handle_socket_read_error(self, socket, error):
        if socket == self.rep_socket:
            self.logger.warning("reinitialising REP socket")
            self._all_sockets.remove(self.rep_socket)
            self.rep_socket.close()  # linger=0)
            self.rep_socket = None
            time.sleep(0.2)  # XXX strange sleep
            (self.rep_socket, self.rep_addresses) = self._init_socket(
                ['tcp://*:' + str(self.rep_port)], zmq.REP)
            self.rep_socket.setsockopt(zmq.LINGER, 0)
            self._all_sockets.append(self.rep_socket)
            self.logger.info(self.rep_addresses)

        elif socket == self.exp_rep:
            self.logger.info("reinitialising EXPERIMENT REP socket")
            self.exp_rep.close()  # linger=0)

            self.exp_rep, self.exp_rep_addrs = self._init_socket(self.exp_rep_addrs, zmq.REP)
            self.exp_rep.setsockopt(zmq.LINGER, 0)
            self._all_sockets.append(self.exp_rep)

    def peer_type(self):
        return 'obci_server'

    def net_init(self):
        self.exp_rep, self.exp_rep_addrs = self._init_socket([], zmq.REP)
        super(SimpleOBCIServer, self).net_init()

    def custom_sockets(self):
        return [self.exp_rep]

    def clean_up(self):
        pass

    def cleanup_before_net_shutdown(self, kill_message, sock=None):
        messages.KillMsg(receiver="").send(self._publish_socket)
        messages.LauncherShutdownMsg(sender=self.uuid).send(self._publish_socket)
        for sup in self.exp_process_supervisors:
            self.exp_process_supervisors[sup].kill()
        self.logger.info('sent KILL to experiments')

        # waiting for all local experiments
        for exp_info in self.experiments.values():
            process = self.subprocess_mgr.process(self.machine, exp_info.pid)
            if process is not None:
                process.kill()

    def _args_for_experiment(self, sandbox_dir, launch_file, local=False, name=None, overwrites=None):

        args = ['--sv-addresses']
        args += self.exp_rep_addrs
        args.append('--sv-pub-addresses')
        addrs = net.filter_local(self.pub_addresses)

        args += addrs
        exp_name = name if name else os.path.basename(launch_file)

        args += [
            '--sandbox-dir', str(sandbox_dir),
            '--launch-file', str(launch_file),
            '--name', exp_name,
            '--current-ip', self.my_ip()]
        if overwrites is not None:
            args += peer_cmd.peer_overwrites_cmd(overwrites)
        return args

    def start_experiment_process(self, sandbox_dir, launch_file, name=None, overwrites=None):
        args = self._args_for_experiment(sandbox_dir, launch_file,
                                         local=True, name=name, overwrites=overwrites)
        exp_process = LocalOBCIExperiment(args, self.machine)
        self.subprocess_mgr._add_process(exp_process)
        return exp_process, ''

    def handle_register_experiment(self, message, sock):
        machine, pid = message.other_params['origin_machine'], message.other_params['pid']
        status, det = message.other_params['status_name'], message.other_params['details']
        launch_file = message.other_params['launch_file_path']
        log_source_name = message.other_params['log_source_name']

        exp_proc = self.subprocess_mgr.process(machine, pid)

        if exp_proc is None:
            messages.RqErrorMsg(err_code="experiment_not_found").send(sock)
            return

        info = self.experiments[message.uuid] = ExperimentInfo(
            uuid=message.uuid,
            name=message.name,
            rep_addrs=message.rep_addrs,
            pub_addrs=message.pub_addrs,
            registration_time=time.time(),
            origin_machine=machine,
            pid=pid,
            status_name=status,
            details=det,
            launch_file_path=launch_file,
            ip=None,
            log_source_name=log_source_name,
            sentry_reporting_enabled=message.other_params['sentry_reporting_enabled'],
        )

        exp_proc.registered(info)

        info_msg = messages.ExperimentCreatedMsg(
            uuid=info.uuid,
            name=info.name,
            rep_addrs=info.rep_addrs,
            pub_addrs=info.pub_addrs,
            origin_machine=info.origin_machine,
            status_name=status,
            details=det,
            launch_file_path=launch_file,
        )

        self._notify_experiment_created(info_msg)
        info_msg = info_msg.serialize()
        messages.RqOkMsg(
            params=self.nearby_servers(),
        ).send(sock)
        send_msg(self._publish_socket, info_msg)

    def _notify_experiment_created(self, info_msg):
        self._experiment_info = info_msg
        self._experiment_created.set()

    @msg_handlers.handler(messages.SvarogStartSavingSignal)
    def handle_svarog_start_saving_signal(self, message, sock):
        self.svarog_peers_runner.handle_start_saving(message, sock)

    @msg_handlers.handler(messages.SvarogCheckSavingSignalStatus)
    def handle_svarog_check_saving_signal_status(self, message, sock):
        self.svarog_peers_runner.handle_check_status(message, sock)

    @msg_handlers.handler(messages.SvarogFinishSavingSignal)
    def handle_svarog_finish_saving_signal(self, message, sock):
        self.svarog_peers_runner.handle_finish_saving(message, sock)

    @msg_handlers.handler(messages.OBCIServerCapabilitiesReq)
    def handle_obci_server_capabilities(self, message, sock):
        messages.OBCIServerCapabilities(
            capabilities=self.CAPABILITIES
        ).send(sock)

    def create_obci_server_peer(self, broker_address, experiment):
        return OBCIServerPeer(broker_address, experiment.name, self, experiment.log_source_name)

    @msg_handlers.handler(messages.BrokerStartedMsg)
    def handle_broker_started(self, message, sock):
        """Create OBCIServerPeer for experiment."""
        obci_server_peer = self.create_obci_server_peer(message.address, self.experiments[message.uuid])
        self.experiments[message.uuid].obci_server_peer_id = obci_server_peer.id
        messages.RqOkMsg(
            params={'obci_server_peer_id': obci_server_peer.id},
        ).send(sock)

    @msg_handlers.handler(messages.RegisterPeerMsg)
    def handle_register_peer(self, message, sock):
        """Register peer"""
        if message.peer_type == "obci_client":
            messages.RqOkMsg().send(sock)
        elif message.peer_type == OBCIExperiment.PEER_TYPE:
            self.handle_register_experiment(message, sock)
        else:
            super(SimpleOBCIServer, self).handle_register_peer(message, sock)

    def _check_network(self, sock):
        return True

    def _handle_match_name(self, message, sock, this_machine=False):
        matches = self.exp_matching(message.strname)
        match = None
        msg = None
        if not matches:
            msg = messages.RqErrorMsg(
                request=vars(message),
                err_code='experiment_not_found',
            ).serialize()

        elif len(matches) > 1:
            matches = [(exp.uuid, exp.name) for exp in matches]
            msg = messages.RqErrorMsg(
                request=vars(message),
                err_code='ambiguous_exp_name',
                details=matches,
            ).serialize()
        else:
            match = matches.pop()
            if this_machine and match.origin_machine != self.machine:
                msg = messages.RqErrorMsg(
                    request=vars(message),
                    err_code='exp_not_on_this_machine',
                    details=match.origin_machine,
                ).serialize()
                match = None
        if msg and sock.socket_type in [zmq.REP, zmq.ROUTER]:
            send_msg(sock, msg)
        return match

    @msg_handlers.handler(messages.GetExperimentContactMsg)
    def handle_get_experiment_contact(self, message, sock):
        self.logger.debug("##### rq contact for: %s", message.strname)

        info = self._handle_match_name(message, sock)
        if info:
            rep_addrs = net.filter_not_local(info.rep_addrs) or info.rep_addrs
            pub_addrs = net.filter_not_local(info.pub_addrs) or info.pub_addrs
            messages.ExperimentContactMsg(
                uuid=info.uuid,
                name=info.name,
                rep_addrs=rep_addrs,
                pub_addrs=pub_addrs,
                machine=info.origin_machine,
                status_name=info.status_name,
                details=info.details,
            ).send(sock)

    @msg_handlers.handler(messages.ExperimentStatusChangeMsg)
    def handle_experiment_status_change(self, message, sock):
        exp = self.experiments.get(message.uuid, None)
        if not exp:
            if sock.socket_type in [zmq.REP, zmq.ROUTER]:
                messages.RqErrorMsg(
                    err_code='experiment_not_found',
                ).send(sock)
            return
        exp.status_name = message.status_name
        exp.details = message.details
        if sock.socket_type in [zmq.REP, zmq.ROUTER]:
            messages.RqOkMsg().send(sock)

        send_msg(self._publish_socket, message.SerializeToString())

    def exp_matching(self, strname):
        """Match *strname* against all created experiment IDs and
        names. Return those experiment descriptions which name
        or uuid starts with strname.
        """
        match_names = {}
        for uid, exp in self.experiments.items():
            if exp.name.startswith(strname):
                match_names[uid] = exp

        ids = self.experiments.keys()
        match_ids = [uid for uid in ids if uid.startswith(strname)]

        experiments = set()
        for uid in match_ids:
            experiments.add(self.experiments[uid])
        for name, exp in match_names.items():
            experiments.add(exp)

        return experiments

    @msg_handlers.handler(messages.KillExperimentMsg)
    def handle_kill_experiment(self, message, sock):
        match = self._handle_match_name(message, sock, this_machine=True)

        if match:
            if match.kill_timer is not None and message.force is False:
                messages.RqErrorMsg(
                    err_code="already_killed",
                    details="Experiment already shutting down",
                ).send(sock)
            else:
                self.logger.info("sending kill to experiment "
                                 "{0} ({1}), force={2}".format(match.uuid, match.name, message.force))
                messages.KillMsg(
                    receiver=match.uuid,
                    force=message.force,
                ).send(self._publish_socket)

                messages.KillSentMsg(
                    experiment_id=match.uuid,
                ).send(sock)
                pid = match.experiment_pid
                uid = match.uuid
                self.logger.info("Waiting for experiment process {0} to terminate".format(uid))
                match.kill_timer = threading.Thread(target=self._handle_killing_exp, args=[pid, uid, message.force])
                match.kill_timer.start()
                messages.KillSentMsg(
                    experiment_id=match.uuid,
                ).send(self._publish_socket)

    def _handle_killing_exp(self, pid, uid, force=False):
        proc = self.subprocess_mgr.process(self.machine, pid)
        # Experiment should be never force killed
        # if it is - children are left which will not kill by themselves if they are on another computer
        while proc.process_is_running():  # experiment got kill command, it should shut down by itself
            time.sleep(EXPERIMENT_PROCESS_CHECK_INTERVAL)  # required
        self.logger.info("experiment {0} FINISHED".format(uid))
        proc.delete = True
        messages.ExperimentStatusChangeMsg(
            status_name=launcher_constants.FINISHED,
            uuid=uid,
        ).send(self._publish_socket)
        if uid in self.experiments:
            del self.experiments[uid]
        return proc.popen_obj.returncode

    @msg_handlers.handler(messages.FindEegAmplifiersMsg)
    @check_network_ready
    def handle_find_new_eeg_amplifiers(self, message, sock):
        messages.RqOkMsg().send(sock)
        amp_thr = threading.Thread(target=find_new_experiments_and_push_results,
                                   args=[self.ctx, message])
        amp_thr.daemon = True
        amp_thr.start()

    @msg_handlers.handler(messages.StartEegSignalMsg)
    @check_network_ready
    def handle_start_eeg_signal(self, message, sock):
        messages.RqOkMsg().send(sock)
        start_thr = threading.Thread(target=self._start_eeg_signal_experiment,
                                     args=[message])
        start_thr.daemon = True
        start_thr.start()

    def _start_eeg_signal_experiment(self, rq_message):
        amp_params = {}
        amp_params.update(rq_message.amplifier_params['additional_params'])
        del rq_message.amplifier_params['additional_params']
        amp_params.update(rq_message.amplifier_params)

        par_list = {'peer_id': 'amplifier', 'local_params': {}}
        par_list['local_params'].update(CONFIG_DEFAULTS)
        par_list['local_params'].update({k: str(v) for k, v in amp_params.items()})

        overwrites, other_params = ConfiguredMixin._parse_kwargs(par_list)
        launch_file = rq_message.launch_file

        name = rq_message.name
        overwrites = [[overwrites, other_params]]
        result = self._start_experiment(launch_file, name, overwrites)
        if rq_message.client_push_address:
            address = rq_message.client_push_address
            to_client = self.ctx.socket(zmq.PUSH)
            to_client.connect(address)
            if result is None:
                result = messages.RqErrorMsg(
                    err_code="launch_failed",
                    details="No response from server or experiment",
                )
            result.send(to_client)
            to_client.close(linger=-1)
            self.logger.info("sent eeg launch result %.500s to %s", result, address)

    def _start_experiment(self, launch_file, name, overwrites):
        sandbox_dir = DEFAULT_SANDBOX_DIR
        self._experiment_created.clear()
        exp, details = self.start_experiment_process(sandbox_dir, launch_file, name, overwrites)
        if exp:
            if self._experiment_created.wait(10.0):
                return self._send_start_experiment(self._experiment_info.rep_addrs)

    def _send_start_experiment(self, exp_addrs):
        exp_sock = self.ctx.socket(zmq.REQ)
        try:
            for addr in exp_addrs:
                exp_sock.connect(addr)
            msg = messages.StartExperimentMsg()
            msg.send(exp_sock)
            response = PollingObject().poll_recv(exp_sock, 20000)[0]
            if response:
                return messages_core.deserialize(response)
            return None
        finally:
            exp_sock.close()

    def _crash_extra_data(self, exception=None):
        data = super(SimpleOBCIServer, self)._crash_extra_data(exception)
        data.update({
            'experiments': [e.info() for e in self.experiments.values()]
        })
        return data


class ExperimentInfo:
    def __init__(self, uuid, name, rep_addrs, pub_addrs, registration_time, origin_machine, pid, status_name=None,
                 details=None, launch_file_path=None, ip=None, obci_server_peer_id=None, log_source_name=None,
                 sentry_reporting_enabled=True):
        self.uuid = uuid
        self.name = name
        self.rep_addrs = rep_addrs
        self.pub_addrs = pub_addrs
        self.registration_time = registration_time
        self.origin_machine = origin_machine
        self.experiment_pid = pid
        self.kill_timer = None
        self.status_name = status_name
        self.details = details
        self.launch_file_path = launch_file_path
        self.ip = ip
        self.obci_server_peer_id = obci_server_peer_id
        self.log_source_name = log_source_name
        self.sentry_reporting_enabled = sentry_reporting_enabled

    @property
    def machine_ip(self):
        return self.origin_machine

    @property
    def pid(self):
        return self.experiment_pid

    def info(self):
        d = dict(uuid=self.uuid,
                 name=self.name,
                 rep_addrs=self.rep_addrs,
                 pub_addrs=self.pub_addrs,
                 registration_time=self.registration_time,
                 origin_machine=self.origin_machine,
                 experiment_pid=self.experiment_pid,
                 status_name=self.status_name,
                 details=self.details,
                 launch_file_path=self.launch_file_path,
                 ip=self.ip,
                 obci_server_peer_id=self.obci_server_peer_id,
                 log_source_name=self.log_source_name
                 )

        return d


def _run_simple_obci_server():
    install_sentry()
    os.environ['OBCI_HOSTNAME'] = 'localhost'
    srv = SimpleOBCIServer(rep_addresses=['tcp://*:%s' % net.server_rep_port()],
                           pub_addresses=['tcp://*:%s' % net.server_pub_port()])

    ParentCheckingThread(gracefull_delay=10, name="SimpleOBCIServer").start()
    try:
        srv.run()
    except Exception as ex:
        # we must handle any exception or obci_server will not end
        logging.getLogger().exception(ex)


def run():
    _run_simple_obci_server()
