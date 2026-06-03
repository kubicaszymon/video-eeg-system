# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import argparse
import io
import logging
import os
import pprint
import socket
import sys
import time
from threading import Thread
from typing import Optional

import zmq

import braintech.obci.core
from braintech.obci.experiment.error_reporting import install_sentry

from ..common.obci_control_settings import DEFAULT_SANDBOX_DIR, DEFAULT_SCENARIO_DIR
import braintech.obci.experiment.launcher.launcher_tools as launcher_tools
from ..peer.peer_cmd import peer_overwrites_pack
from braintech.obci.core.control.common import net
from ..common.message import PollingObject, send_msg
from . import experiment_config
from . import morph
from .launcher_tools import is_builtin_scenario
from .local_process import LocalThreadedProcess, LocalProcess
from .obci_control_peer import OBCIControlPeer, basic_arg_parser
from .obci_control_peer import RegistrationDescription
from .obci_process_supervisor import OBCIProcessSupervisor, LocalProcessSupervisor
from ..peer.peer_config_serializer import PeerConfigSerializerJSON
from braintech.obci.core.broker import BROKER_TCP_IP_DEFAULT_PORT
from braintech.obci.core.broker.broker import Broker
from braintech.obci.core.broker.message_handler_mixin import subscribe_message_handler
import braintech.obci.experiment.messages as messages
import braintech.obci.core.broker.messages as messages_core
from braintech.obci.core.broker.url_utils_mixin import split_ipv4_address
from braintech.obci.core.utils import TimeoutException, wait_for_condition
from braintech.obci.core.utils.openbci_logging import log_crash, enable_handlers
from braintech.obci.core.utils.parent_checking import ParentCheckingThread
from . import launch_file_parser
from . import subprocess_monitor
from . import system_config
from .launch_file_serializer import serialize_scenario_json
from .subprocess_monitor import SubprocessMonitor, TimeoutDescription, NO_STDIO, ProcessDescription

REGISTER_TIMEOUT = 25
SUPERVISORS_CHECK_INTERVAL = 0.05
SUPERVISORS_TIMEOUT = 60
BROKER_PANIC_CHECK_INTERVAL = 0.05


class AddPeerException(Exception):
    def __init__(self, error_code, details=None):
        super().__init__()
        self.error_code = error_code
        self.details = details


class PanickingBroker(Broker):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_panicking = False
        self.panicking_peers = {}

    @subscribe_message_handler(messages_core.PanicMsg)
    async def _handle_panic(self, msg: messages_core.PanicMsg):
        if msg.was_essential:
            self._logger.info('Setting is_panicking to True')
            self.is_panicking = True
        self.panicking_peers[msg.sender] = msg


class OBCIExperiment(OBCIControlPeer):
    PEER_TYPE = 'experiment'
    msg_handlers = OBCIControlPeer.msg_handlers.copy()

    @log_crash
    def __init__(self, sandbox_dir, launch_file=None,
                 source_addresses=None,
                 source_pub_addresses=None,
                 rep_addresses=None,
                 pub_addresses=None,
                 name=PEER_TYPE,
                 current_ip=None,
                 launch=False,
                 overwrites=None,
                 log_source_name: Optional[str] = None
                 ):
        # TODO TODO TODO !!!!
        # cleaner subclassing of obci_control_peer!!!
        self.sandbox_dir = sandbox_dir if sandbox_dir else DEFAULT_SANDBOX_DIR
        if os.path.exists(launch_file):
            self.launch_file = launch_file
        else:
            self.launch_file = launcher_tools.obci_root_relative(launch_file)
        self.source_pub_addresses = source_pub_addresses
        self.current_ip = current_ip
        self._log_source_name = log_source_name

        self.origin_machine = net.gethostname()
        self._nearby_machines = net.DNS()
        self._notification_confirmation_waiting = False
        super().__init__(source_addresses, rep_addresses, pub_addresses, name)
        self.name = name + ' on ' + self.origin_machine

        self.poller = PollingObject()
        self.supervisors = {}  # machine -> supervisor contact/other info
        self._wait_register = 0
        self._ready_register = 0
        self._kill_and_launch = None
        self.__cfg_morph = False
        self._exp_extension = {}
        self.sv_processes = {}  # machine -> Process objects)
        self.unsupervised_peers = {}
        self.mx_addr = None
        self.mx_pass = None
        self.broker = None  # every experiment has broker
        # after getting kill msg, experiment starts to wait for its supervisors to finish
        self._shutdown_thread = None
        self.subprocess_mgr = SubprocessMonitor(self.ctx, self.uuid,
                                                logger=self.logger)

        if launch_file in ['None', '']:  # command line arg
            self._initialize_experiment_without_config()
        else:
            self.exp_config, self.status = self._initialize_experiment_config(self.launch_file, overwrites)
        self.logger.info("initialised config")

        self.status_changed(self.status.status_name, self.status.details)

    def net_init(self):
        self.source_sub_socket = self.ctx.socket(zmq.SUB)
        self.source_sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

        if self.source_pub_addresses:
            for addr in self.source_pub_addresses:
                self.source_sub_socket.connect(addr)
        self._all_sockets.append(self.source_sub_socket)

        (self.supervisors_rep, self.supervisors_rep_addrs) = self._init_socket([], zmq.REP)
        (self.supervisors_sub, self.supervisors_sub_addrs) = (self.ctx.socket(zmq.SUB), [])

        self._all_sockets.append(self.supervisors_sub)
        self._all_sockets.append(self.supervisors_rep)

        super().net_init()
        self.rep_addresses.append(self._ip_based_addr(net.choose_addr(self.rep_addresses)))
        self.pub_addresses.append(self._ip_based_addr(net.choose_addr(self.pub_addresses)))

    def _ip_based_addr(self, other_addr):
        return 'tcp://' + str(self.current_ip) + ':' + str(net.port(other_addr))

    def params_for_registration(self):
        pid = os.getpid()
        return dict(
            pid=pid,
            origin_machine=self.origin_machine,
            status_name='',
            details='',
            launch_file_path=self.launch_file,
            log_source_name=self._log_source_name,
            sentry_reporting_enabled=is_builtin_scenario(self.launch_file),
        )

    def _handle_registration_response(self, response):
        self._nearby_machines.mass_update(response.params)

    def custom_sockets(self):
        return [self.source_sub_socket, self.supervisors_sub, self.supervisors_rep]

    def args_for_process_sv(self, machine, local=False):
        args = ['--sv-addresses']
        local = self._nearby_machines.is_this_machine(machine)

        a = self._ip_based_addr(net.choose_addr(self.supervisors_rep_addrs))
        if local:
            port = net.port(a)
            a = 'tcp://' + net.gethostname() + ':' + str(port)

        args.append(a)
        args.append('--sv-pub-addresses')
        a = self._ip_based_addr(net.choose_addr(self.pub_addresses))
        if local:
            port = net.port(a)
            a = 'tcp://' + net.gethostname() + ':' + str(port)

        args.append(a)
        name = self.name if self.name and self.name != self.PEER_TYPE else \
            os.path.basename(self.launch_file)
        args += [
            '--sandbox-dir', str(self.sandbox_dir),
            '--name', name + '-' + self.uuid.split('-', 1)[0] + '-' + machine,
            '--log-source-name', str(self._log_source_name),
            '--experiment-uuid', self.uuid,
            '--log-agregator-addresses',
        ]

        # here source addresses are the addresses provided by obci server for communication with obci experiment
        # we can send logs or other info to those addresses

        if local:
            args += net.filter_local(self.source_addresses)
        else:
            addrs = self._ip_based_addr(net.choose_addr(net.filter_not_local(self.source_addresses)))
            args.append(addrs)

        return args

    def _start_obci_process_supervisor(self, machine_addr):
        args = self.args_for_process_sv(machine_addr)
        proc_type = 'obci_process_supervisor'

        self.logger.debug('Starting obci_process_supervisor with params: %s', args)

        if machine_addr == self.origin_machine:
            sv_obj = LocalProcessSupervisor(args, machine_addr)
            self.subprocess_mgr._add_process(sv_obj)
            details = ''
        else:
            try:
                srv_ip = self._nearby_machines.ip(hostname=machine_addr)
            except Exception:
                det = "Machine " + machine_addr + " not found, cannot launch remote process!" + \
                      "Is obci_server running there? " + \
                      "If yes, maybe you should wait for a few seconds and retry."
                self.logger.critical(det)
                return False, det

            conn_addr = 'tcp://' + srv_ip + ':' + net.server_rep_port()
            sv_obj, details = self.subprocess_mgr.new_remote_process(path=None,
                                                                     args=args, proc_type=proc_type,
                                                                     name=self.uuid, machine_ip=machine_addr,
                                                                     conn_addr=conn_addr, capture_io=NO_STDIO
                                                                     )
        if sv_obj is None:
            return False, details

        timeout_handler = TimeoutDescription(timeout=REGISTER_TIMEOUT,
                                             timeout_method=self._handle_register_sv_timeout,
                                             timeout_args=[sv_obj])
        sv_obj.set_registration_timeout_handler(timeout_handler)
        self.sv_processes[machine_addr] = sv_obj
        return sv_obj, None

    def _start_obci_process_supervisors(self, peer_machines):
        self._wait_register = len(peer_machines)
        details = None

        for machine in peer_machines:
            result, details = self._start_obci_process_supervisor(machine)

            if not result:
                self.status.set_status(launcher_tools.FAILED_LAUNCH, details)
                details = "FAILED to start supervisor: {0}".format(details)
                self.logger.fatal(details)
                self.status_changed(self.status.status_name, self.status.details)
                return False, details

            k = result.machine_ip
            self.sv_processes[k] = result
        return True, details

    def _send_launch_data(self):
        pass

    def _start_experiment(self):
        """
        START EXPERIMENT!!!!
        ##################################################################
        """
        result, details = self._start_obci_process_supervisors(self.exp_config.peer_machines())
        if not result:
            messages.ExperimentLaunchErrorMsg(
                sender=self.uuid,
                details=details,
                err_code='supervisor_launch_error',
            ).send(self._publish_socket)
        return result, details

    def _initialize_experiment_config(self, launch_file, overwrites=None):
        status = launcher_tools.ExperimentStatus()

        exp_config = system_config.OBCIExperimentConfig(uuid=self.uuid)
        exp_config.origin_machine = self.origin_machine
        exp_config.launch_file_path = launch_file

        result, details = experiment_config.make(exp_config, launch_file,
                                                 status, overwrites)

        if not launch_file:
            self.logger.fatal("No launch file")
        elif not result:
            self.logger.fatal("- - - - - - - NEW LAUNCH FILE INVALID!!!  - - - - - - - "
                              "status: " + str(status.as_dict()) + str(details))
        else:
            exp_config.status(status)

        return exp_config, status

    def _initialize_experiment_without_config(self):
        self.status = launcher_tools.ExperimentStatus()
        self.status.set_status(launcher_tools.NOT_READY, details="No launch_file")
        self.exp_config = system_config.OBCIExperimentConfig()
        self.exp_config.origin_machine = self.origin_machine

    def status_changed(self, status_name, details, peers=None):
        self.logger.info("status changed: %s", status_name)
        self.notify_server(
            messages.ExperimentStatusChangeMsg(
                status_name=status_name,
                details=details,
                uuid=self.uuid,
                peers=peers,
            ))

    def _send_req(self, message):
        if self._notification_confirmation_waiting:
            msg, error = self.poller.poll_recv(self.source_req_socket, timeout=8000)
            if msg is None:
                raise TimeoutException("Could not receive notification confirmation! Possible deadlock with server")
        message.send(self.source_req_socket)
        self._notification_confirmation_waiting = True

    def notify_server(self, message):
        try:
            self._send_req(message)
        except TimeoutException as ex:
            self.logger.warning("Could not sent notification: %s (%s)", ex)

    def ask_server(self, message):
        self._send_req(message)
        res, _ = self.poller.poll_recv(self.source_req_socket, timeout=8000)
        if res:
            self._notification_confirmation_waiting = False
            return messages_core.deserialize(res)
        else:
            raise TimeoutException

    @msg_handlers.handler(messages.RegisterPeerMsg)  # noqa: C901
    def handle_register_peer(self, message, sock):
        """Experiment"""
        if message.peer_type == OBCIProcessSupervisor.PEER_TYPE:

            machine, pid = message.other_params['machine'], message.other_params['pid']

            if message.other_params['mx_data'] is not None and not self.mx_addr:
                # right now we support only one mx per obci instance
                ip = self._nearby_machines.ip(machine) if self._nearby_machines.dict_snapshot() else \
                    machine

                self.mx_addr = ip + ':' + message.other_params['mx_data'][0].split(':')[1]
                self.mx_pass = message.other_params['mx_data'][1]

            proc = self.subprocess_mgr.process(machine, pid)
            if proc is None:
                messages.RqErrorMsg(
                    err_code='process_not_found',
                    request=message.dict(),
                ).send(sock)
                return

            status, details = proc.status()
            if status != subprocess_monitor.UNKNOWN:
                messages.RqErrorMsg(
                    err_code='process_status_invalid',
                    request=message.dict(),
                    details=(status, details),
                ).send(sock)
                messages.ExperimentLaunchErrorMsg(
                    err_code='registration_error',
                    sender=self.uuid,
                    details=(status, details),
                ).send(self._publish_socket)
                return
            self.logger.info("exp registration message  " + str(vars(message)))
            adr_list = [message.rep_addrs, message.pub_addrs]
            if machine != net.gethostname():
                ip = self._nearby_machines.ip(machine)
                for i, addrs in enumerate([message.rep_addrs, message.pub_addrs]):
                    first = addrs[0]
                    port = net.port(first)
                    adr_list[i] = ['tcp://' + ip + ':' + str(port)]
            self.logger.info("addresses after filtering: %s", str(adr_list))
            desc = self.supervisors[machine] = \
                RegistrationDescription(
                    message.uuid,
                    message.name,
                    adr_list[0],
                    adr_list[1],
                    message.other_params['machine'],
                    message.other_params['pid'])
            proc.registered(desc)
            a = self._choose_process_address(proc, desc.pub_addrs)
            if a is not None:
                self.supervisors_sub_addrs.append(a)
                self.supervisors_sub.setsockopt_string(zmq.SUBSCRIBE, "")
                self.supervisors_sub.connect(a)
                self.logger.info("Connecting to supervisor pub address {0} ({1})".format(a, machine))
            else:
                self.logger.error("Could not find suitable PUB address to connect. (supervisor on " + machine + ")")

            launch_data = self.exp_config.launch_data(machine)
            order = self.exp_config.peer_order()

            messages.RqOkMsg(
                params=dict(launch_data=launch_data, peer_order=order),
            ).send(sock)

            # inform observers
            messages.ProcessSupervisorRegisteredMsg(
                sender=self.uuid,
                machine_ip=desc.machine_ip,
            ).send(self._publish_socket)

            self._wait_register -= 1
            if self._wait_register == 0:
                if self._kill_and_launch:
                    kill, launch, new_supervisors, keep_configs = self._kill_and_launch
                    to_launch = launch[machine]
                    to_kill = kill.get(machine, [])
                    messages.ManagePeersMsg(
                        kill_peers=to_kill,
                        start_peers_data=to_launch,
                        receiver=desc.uuid,
                    ).send(self._publish_socket)
                elif self._exp_extension:
                    ldata = {}
                    peer_id = self._exp_extension[machine][0]
                    ldata[peer_id] = self.exp_config.launch_data(machine)[peer_id]
                    messages.StartPeersMsg(
                        mx_data=self.mx_args(),
                        add_launch_data={machine: ldata},
                    ).send(self._publish_socket)
                else:
                    self.broker = self._create_broker()
                    self.logger.debug('Broker started')
                    res = self.ask_server(
                        #  send message "broker_started" with broker's address to OBCI_SRV
                        messages.BrokerStartedMsg(
                            uuid=self.uuid,
                            address=self.broker.broker_ip,
                        ))

                    self.obci_server_peer_id = res.params['obci_server_peer_id']
                    try:
                        wait_for_condition(self._wait_for_peer)
                    except TimeoutException:
                        self.logger.fatal('Experiment did not connect to Broker.')
                        self.interrupted = True
                    else:
                        messages.StartConfigServerMsg(
                            mx_data=self.mx_args(),
                        ).send(self._publish_socket)

    def _wait_for_peer(self):
        return self.obci_server_peer_id in self.broker._peers

    def _create_broker(self):
        broker_host, broker_port = split_ipv4_address(self.mx_addr, default_port=BROKER_TCP_IP_DEFAULT_PORT)
        broker_host = socket.gethostbyname(broker_host)
        broker_tcp_ip_addr = '{}:{}'.format(broker_host, broker_port)

        rep_urls = ['tcp://*:*']
        xpub_urls = ['tcp://*:*']
        xsub_urls = ['tcp://*:*']
        broker = PanickingBroker(broker_tcp_ip_addr, rep_urls, xpub_urls, xsub_urls)
        broker_watchdog_t = Thread(target=self._broker_watchdog)
        broker_watchdog_t.daemon = True
        broker_watchdog_t.start()
        return broker

    def _broker_watchdog(self):
        while True:
            time.sleep(BROKER_PANIC_CHECK_INTERVAL)  # required, ?use condition variable
            if self.broker.is_panicking:
                def callback_after_timeout():
                    self._send_kill_msg(True)

                self.logger.fatal('Broker got PANIC, shutting down everything')
                # Experiment will try to gracefully kill all local or remote peers
                # using it's normal closing mechanism
                # if peers won't close after SUPERVISORS_TIMEOUT
                # Will use forced closing mechanism
                self._send_kill_msg(False)
                self.__wait_for_subprocesses(timeout_callback=callback_after_timeout)
                break

    def _send_kill_msg(self, force):
        self.ask_server(
            messages.KillExperimentMsg(
                strname=self.uuid,
                force=force,
            ))

    def mx_args(self):
        return ["run_multiplexer", self.mx_addr]

    @msg_handlers.handler(messages.GetBrokerAddress)
    def handle_get_broker_address(self, message, sock):
        messages.RqOkMsg(status=self.broker.broker_ip).send(sock)

    @msg_handlers.handler(messages.LaunchedProcessInfoMsg)
    def handle_launched_process_info(self, message, sock):
        if message.name == 'config_server':
            self.status.peer_status(message.name).set_status(
                launcher_tools.RUNNING)
            time.sleep(0.3)
            if self._kill_and_launch:
                kill_data, launch_data, new_supervisors, keep_configs = self._kill_and_launch
                for machine in kill_data:
                    to_kill = kill_data[machine]
                    if machine in launch_data:
                        to_launch = launch_data[machine]
                    else:
                        to_launch = {}
                    messages.ManagePeersMsg(
                        kill_peers=to_kill,
                        start_peers_data=to_launch,
                        receiver=self.supervisors[machine].uuid,
                    ).send(self._publish_socket)
                for machine in launch_data:
                    if machine not in new_supervisors and machine not in kill_data:
                        to_launch = launch_data[machine]
                        messages.ManagePeersMsg(
                            kill_peers=[],
                            start_peers_data=to_launch,
                            receiver=self.supervisors[machine].uuid,
                        ).send(self._publish_socket)
            else:
                messages.StartPeersMsg(
                    mx_data=self.mx_args(),
                ).send(self._publish_socket)
        elif message.proc_type == 'obci_peer':
            self.status.peer_status(message.name).set_status(
                launcher_tools.LAUNCHING)
        self.status_changed(self.status.status_name, self.status.details,
                            peers={message.name: self.status.peer_status(message.name).status_name})

    @msg_handlers.handler(messages.AllPeersLaunchedMsg)
    def handle_all_peers_launched(self, message, sock):
        if self._exp_extension:
            self._exp_extension = {}
            self.logger.info("all additional peers launched.")
            return

        self._wait_register -= 1
        self.logger.info(str(message) + str(self._wait_register))
        if self._wait_register == 0:
            self.status.set_status(launcher_tools.LAUNCHING)
            self.status_changed(self.status.status_name, self.status.details)
        if not self._kill_and_launch:  # if kill/launch, this variable was set in _kill_and_launch_peers()
            # without mx and config_server, for now default is 1 mx
            self._ready_register = len(self.exp_config.peers) - 1

    def _choose_process_address(self, proc, addresses):
        self.logger.info("(exp) choosing sv address:" + str(addresses))
        addrs = []
        chosen = None
        if proc.is_local():
            addrs = net.filter_local(addresses)
        if not addrs:
            addrs = net.filter_not_local(addresses)
        if addrs:
            chosen = addrs.pop()
        return chosen

    @msg_handlers.handler(messages.GetExperimentInfoMsg)
    def handle_get_experiment_info(self, message, sock):
        messages.RqOkMsg().send(self._publish_socket)
        messages.ExperimentInfoMsg(
            experiment_status=self.status.as_dict(),
            unsupervised_peers=self.unsupervised_peers,
            origin_machine=self.exp_config.origin_machine,
            uuid=self.exp_config.uuid,
            scenario_dir=self.exp_config.scenario_dir,
            peers=self.exp_config.peers_info(),
            launch_file_path=self.exp_config.launch_file_path,
            name=self.name,
        ).send(sock)

    @msg_handlers.handler(messages.GetPeerInfoMsg)
    def handle_get_peer_info(self, message, sock):
        if message.peer_id not in self.exp_config.peers:
            messages.RqErrorMsg(
                request=message.dict(),
                err_code='peer_id_not_found',
            ).send(sock)
        else:
            peer_info = self.exp_config.peers[message.peer_id].info(detailed=True)
            messages.PeerInfoMsg(
                **peer_info
            ).send(sock)

    @msg_handlers.handler(messages.GetPeerParamValuesMsg)
    def handle_get_peer_param_values(self, message, sock):
        if message.peer_id not in self.exp_config.peers:
            messages.RqErrorMsg(
                request=message.dict(),
                err_code='peer_id_not_found',
            ).send(sock)
        else:
            peer_id = message.peer_id
            vals = self.exp_config.all_param_values(peer_id)
            messages.PeerParamValuesMsg(
                peer_id=peer_id,
                param_values=vals,
                sender=self.uuid
            ).send(sock)

    @msg_handlers.handler(messages.GetExperimentScenarioMsg)
    def handle_get_experiment_scenario(self, message, sock):
        jsoned = serialize_scenario_json(self.exp_config)
        messages.ExperimentScenarioMsg(
            scenario=jsoned,
        ).send(sock)

    @msg_handlers.handler(messages.SetExperimentScenarioMsg)
    def handle_set_experiment_scenario(self, message, sock):
        if self.exp_config.peers:
            messages.RqErrorMsg(
                err_code='scenario_already_set',
            ).send(sock)
        else:
            jsonpar = launch_file_parser.LaunchJSONParser(
                launcher_tools.obci_root(), DEFAULT_SCENARIO_DIR)
            self.exp_config.launch_file_path = None

            inbuf = io.StringIO(message.scenario)
            jsonpar.parse(inbuf, self.exp_config)
            self.logger.info("set experiment scenario............... %s" % message.scenario)

            rd, details = self.exp_config.config_ready()
            if rd:
                self.status.set_status(launcher_tools.READY_TO_LAUNCH)
            else:
                self.status.set_status(launcher_tools.NOT_READY, details=details)
                self.logger.warning("scenario not ready %s %s", str(rd), str(details))
            self.exp_config.status(self.status)
            self.launch_file = self.exp_config.launch_file_path = message.launch_file_path
            messages.RqOkMsg().send(sock)
            messages.ExperimentScenarioMsg(
                scenario=message.scenario,
                launch_file_path=message.launch_file_path,
                uuid=self.uuid,
            ).send(self._publish_socket)
            self.notify_server(
                messages.ExperimentInfoChangeMsg(
                    name=self.name,
                    launch_file_path=message.launch_file_path,
                    uuid=self.uuid,
                ))

    @msg_handlers.handler(messages.StartExperimentMsg)
    def handle_start_experiment(self, message, sock):
        if not self.status.status_name == launcher_tools.READY_TO_LAUNCH:
            messages.RqErrorMsg(
                request=message.dict(),
                err_code='exp_status_' + self.status.status_name,
                details=self.status.details,
            ).send(sock)
        else:
            self.status.set_status(launcher_tools.LAUNCHING)
            messages.StartingExperimentMsg(
                sender=self.uuid,
            ).send(sock)
            self.status_changed(self.status.status_name, self.status.details)
            result, details = self._start_experiment()
            if not result:
                messages.ExperimentLaunchErrorMsg(
                    sender=self.uuid,
                    err_code='',
                    details=details,
                ).send(self._publish_socket)
                self.logger.fatal("EXPERIMENT LAUNCH ERROR!!!, {}".format(details))
                self.status.set_status(launcher_tools.FAILED_LAUNCH, details)
            self.status_changed(self.status.status_name, self.status.details)

    @msg_handlers.handler(messages.JoinExperimentMsg)
    def handle_join_experiment(self, message, sock):
        if message.peer_id in self.exp_config.peers or message.peer_id in self.unsupervised_peers:
            messages.RqErrorMsg(
                request=message.dict(),
                err_code='peer_id_in_use',
            ).send(sock)
        elif self.mx_addr is None:
            messages.RqErrorMsg(
                request=message.dict(),
                err_code='mx_not_running',
            ).send(sock)
        elif (self.status.status_name != launcher_tools.RUNNING and
              self.status.status_name != launcher_tools.LAUNCHING):
            # temporary status bug workaround.
            messages.RqErrorMsg(
                request=message.dict(),
                err_code='exp_status_' + self.status.status_name,
                details="",
            ).send(sock)
        else:
            self.unsupervised_peers[message.peer_id] = dict(peer_type=message.peer_type,
                                                            path=message.path)
            messages.RqOkMsg(params=dict(mx_addr=self.mx_addr, )).send(sock)

    @msg_handlers.handler(messages.LeaveExperimentMsg)
    def handle_leave_experiment(self, message, sock):
        if message.peer_id not in self.unsupervised_peers:
            messages.RqErrorMsg(
                request=message.dict(),
                err_code='peer_id_not_found',
            ).send(sock)
        else:
            del self.unsupervised_peers[message.peer_id]
            messages.RqOkMsg().send(sock)

    @msg_handlers.handler(messages.AddPeerMsg)
    def handle_add_peer(self, message, sock):
        """Add new peer to existing scenario. It may run on a different machine than
        already running peers. add_peer works at runtime and before runtime.
        """
        self.logger.info("Handle add peer: " + str(message))
        try:
            response = self._try_adding_peer(message)
        except AddPeerException as e:
            self.logger.warning("Add peer - %", e.error_code)
            if e.details:
                response = messages.RqErrorMsg(
                    request=message.dict(),
                    err_code=e.error_code,
                    details=e.details,
                )
            else:
                response = messages.RqErrorMsg(
                    request=message.dict(),
                    err_code=e.error_code,
                )
        finally:
            response.send(sock)

    def _try_adding_peer(self, message):
        machine = message.machine or self.origin_machine
        peer_id = message.peer_id
        self._validate_state_before_adding_peer(peer_id)
        self._extend_config_with_new_peer(machine, message, peer_id)
        self._launch_added_peer(machine, peer_id)
        return messages.RqOkMsg()

    def _validate_state_before_adding_peer(self, peer_id):
        if self.status.status_name != launcher_tools.RUNNING:
            raise AddPeerException(error_code='experiment_status_incompatible')
        if peer_id in self.exp_config.peers:
            raise AddPeerException(error_code='peer_id_in_use')
        if self.status.peer_status('config_server').status_name != launcher_tools.RUNNING:
            raise AddPeerException(error_code='config_server_not_running')

    def _extend_config_with_new_peer(self, machine, message, peer_id):
        try:
            launch_file_parser.extend_experiment_config(
                self.exp_config,
                peer_id,
                message.peer_path,
                config_sources=message.config_sources,
                launch_deps=message.launch_dependencies,
                custom_config_path=message.custom_config_path,
                param_overwrites=message.param_overwrites,
                machine=machine,
                apply_globals=message.apply_globals,
            )
        except Exception as e:
            if peer_id in self.exp_config.peers:
                self.exp_config.remove_peer(peer_id)
            raise AddPeerException(error_code='problem_with_extending_config',
                                   details=str(e))
        else:
            is_config_ready, details = self.exp_config.config_ready()
            if is_config_ready:
                self.status.peers_status[peer_id] = launcher_tools.PeerStatus(
                    peer_id, status_name=launcher_tools.READY_TO_LAUNCH)
                self._inform_gui_about_new_peer(machine, message.peer_path, peer_id)
            else:
                if peer_id in self.exp_config.peers:
                    self.exp_config.remove_peer(peer_id)
                raise AddPeerException(error_code='config_incomplete',
                                       details=str(details))

    def _inform_gui_about_new_peer(self, machine, peer_path, peer_id):
        ser = PeerConfigSerializerJSON()
        bt = io.StringIO()
        ser.serialize(self.exp_config.peers[peer_id].config, bt)
        peer_conf = bt.getvalue()
        messages.NewPeerAddedMsg(
            peer_id=peer_id,
            machine=machine,
            uuid=self.uuid,
            status_name=launcher_tools.READY_TO_LAUNCH,
            config=peer_conf,
            peer_path=peer_path,
        ).send(self._publish_socket)

    def _launch_added_peer(self, machine, peer_id):
        supervisor = self.supervisors[machine]
        peer_launch_data = self.exp_config.launch_data(machine)[peer_id]
        messages.ManagePeersMsg(
            kill_peers=[],
            start_peers_data={peer_id: peer_launch_data},
            receiver=supervisor.uuid,
        ).send(self._publish_socket)

    @msg_handlers.handler(messages.RemovePeerMsg)
    def handle_remove_peer(self, message, sock):
        peer_id = message.peer_id
        if peer_id in self.exp_config.peers:
            self._remove_peer(peer_id)
            messages.RqOkMsg().send(sock)
        else:
            messages.RqErrorMsg(
                err_code='peer_id_not_found',
                request=message.dict(),
            ).send(sock)

    def _remove_peer(self, peer_id):
        self.exp_config.remove_peer(peer_id)
        message = messages_core.PeerControlMessage(
            peer_id=peer_id,
            action='close',
        )
        self.broker.send_message(message)
        self.status.del_peer_status(peer_id)

    @msg_handlers.handler(messages.KillPeerMsg)
    def handle_kill_peer(self, message, sock):
        peer_id = message.peer_id
        peer = self.exp_config.peers.get(message.peer_id, None)
        if not peer:
            messages.RqErrorMsg(
                request=message.dict(),
                err_code="peer_id_not_found",
            ).send(sock)
            return

        del self.exp_config.peers[peer_id]
        rd, details = self.exp_config.config_ready()
        self.exp_config.peers[peer_id] = peer
        if not rd:
            messages.RqErrorMsg(
                request=message.dict(),
                err_code="config_dependencies_error",
                details=details,
            ).send(sock)
            return
        if message.remove_config:
            peer.del_after_stop = True

        messages.RqOkMsg().send(sock)
        messages.KillPeerMorphMsg(
            peer_id=peer_id,
            machine=(peer.machine or self.origin_machine),
            morph=False,
        ).send(self._publish_socket)

    @msg_handlers.handler(messages.ObciPeerRegisteredMsg)
    def handle_obci_peer_registered(self, message, sock):
        peer_id = message.peer_id
        if peer_id not in self.exp_config.peers:
            self.logger.error("Unknown Peer registered!!! {0}".format(peer_id))
        else:
            self.logger.info("Peer registered!!! {0}".format(peer_id))
            for par, val in message.params.items():
                self.exp_config.update_local_param(peer_id, par, val)
            messages.ObciControlMessageMsg(
                severity='info',
                msg_code='obci_peer_registered',
                launcher_message=message.dict(),
                sender=self.uuid,
                peer_name=self.name,
                peer_type=self.peer_type(),
                sender_ip=self.origin_machine,
            ).send(self._publish_socket)

    @msg_handlers.handler(messages.ObciPeerParamsChangedMsg)
    def handle_obci_peer_params_changed(self, message, sock):
        peer_id = message.peer_id
        if peer_id not in self.exp_config.peers:
            self.logger.error("Unknown Peer update!!! {0}".format(
                self.name, self.peer_type(), peer_id))
        else:
            self.logger.info("Params changed!!! %s %s", peer_id, message.params.keys())
            self.logger.debug(pprint.pformat(message.params))
            for par, val in message.params.items():
                try:
                    self.exp_config.update_local_param(peer_id, par, val)
                except Exception as e:
                    self.logger.error("Invalid params!!! {0} {1} {2}".format(peer_id,
                                                                             message.params, str(e)))

            messages.ObciControlMessageMsg(
                severity='info',
                msg_code='obci_peer_params_changed',
                launcher_message=message.dict(),
                sender=self.uuid,
                peer_name=self.name,
                peer_type=self.peer_type(),
                sender_ip=self.origin_machine,
            ).send(self._publish_socket)

    @msg_handlers.handler(messages.ObciPeerReadyMsg)
    def handle_obci_peer_ready(self, message, sock):
        peer_id = message.peer_id
        if peer_id not in self.exp_config.peers:
            self.logger.error("Unknown Peer update!!! {0}".format(peer_id))
            return
        self.status.peer_status(peer_id).set_status(
            launcher_tools.RUNNING)
        self._ready_register -= 1
        self.logger.info("{0} peer ready! {1} to go".format(peer_id,
                                                            self._ready_register))

        if self._ready_register == 0:
            self.status.set_status(launcher_tools.RUNNING)

        self.status_changed(self.status.status_name, self.status.details,
                            peers={peer_id: self.status.peer_status(peer_id).status_name})

    @msg_handlers.handler(messages.ObciPeerDeadMsg)
    def handle_obci_peer_dead(self, message, sock):
        if message.peer_id not in self.exp_config.peers:
            # during experiment transformation, 'obci_peer_dead' messages may come
            # after explicitly terminating peers and removing them from experiment peers
            # configuration
            self.logger.warning("peer_id %s not found!", message.peer_id)
            return
        status = message.status[0]
        details = message.status[1]
        panic_msg = self.broker.panicking_peers.get(message.peer_id, None)
        if panic_msg:
            if not panic_msg.was_essential:
                status = launcher_tools.FINISHED
            details = panic_msg.data

        self.status.peer_status(message.peer_id).set_status(status, details=details)
        if status == launcher_tools.FAILED:
            messages.StopAllMsg(receiver="").send(self._publish_socket)
            self.status.set_status(launcher_tools.FAILED,
                                   details='Failed process ' + message.peer_id)
            self.logger.fatal("Experiment failed: (process: %s)" % message.peer_id)
        elif (not self.status.peer_status_exists(launcher_tools.RUNNING)
              and self.status.status_name not in (launcher_tools.FAILED, launcher_tools.FAILED_LAUNCH)):
            self.status.set_status(status)
        if self.exp_config.peers[message.peer_id].del_after_stop:
            del self.exp_config.peers[message.peer_id]
            self.status.del_peer_status(message.peer_id)

        if self.__cfg_morph and message.peer_id == 'config_server' and status == launcher_tools.TERMINATED:
            self.__cfg_morph = False
            configs_to_restore = self._kill_and_launch[3]
            messages.StartConfigServerMsg(
                mx_data=self.mx_args(),
                restore_config=configs_to_restore,
            ).send(self._publish_socket)

        message.experiment_id = self.uuid
        send_msg(self._publish_socket, message.SerializeToString())
        self.status_changed(self.status.status_name, self.status.details)

    @msg_handlers.handler(messages.ObciLaunchFailedMsg)
    def handle_obci_launch_failed(self, message, sock):
        if self._exp_extension:
            self.logger.error("launch of additional peers failed")
            self._exp_extension = {}
        pass

    @msg_handlers.handler(messages.LaunchErrorMsg)
    def handle_launch_error(self, message, sock):
        peer_id = message.details["peer_id"]
        if peer_id not in self.exp_config.peers:
            self.logger.error("peer_id" + str(message.peer_id) + "not found!")
            return

        self.status.peer_status(peer_id).set_status(launcher_tools.FAILED_LAUNCH)
        self.status.set_status(launcher_tools.FAILED_LAUNCH,
                               details='Failed to launch process ' + peer_id)
        message.sender = self.uuid
        send_msg(self._publish_socket, message.SerializeToString())
        self.status_changed(self.status.status_name, self.status.details)

    @msg_handlers.handler(messages.UpdatePeerConfigMsg)
    def handle_update_peer_config(self, message, sock):
        if self.status.status_name not in [launcher_tools.NOT_READY,
                                           launcher_tools.READY_TO_LAUNCH]:
            messages.RqErrorMsg(
                err_code='update_not_possible',
                details='Experiment status: ' + self.status.status_name,
            ).send(sock)
        else:
            conf = dict(local_params=message.local_params,
                        external_params=message.external_params,
                        launch_dependencies=message.launch_dependencies,
                        config_sources=message.config_sources)
            peer_id = message.peer_id

            try:
                self.exp_config.update_peer_config(peer_id, conf)
            except Exception as e:
                messages.RqErrorMsg(
                    err_code='update_failed',
                    details=str(e),
                ).send(sock)
            else:
                messages.RqOkMsg().send(sock)

    @msg_handlers.handler(messages.DeadProcessMsg)
    def handle_dead_process(self, message, sock):
        proc = self.subprocess_mgr.process(message.machine, message.pid)
        if proc is not None:
            proc.mark_delete()
            status, details = proc.status()
            self.logger.warning("Process " + proc.proc_type + "dead:" +
                                status + str(details) + proc.name + str(proc.pid))
        self.status_changed(self.status.status_name, self.status.details)

    @msg_handlers.handler(messages.SaveScenarioMsg)
    def handle_save_scenario(self, message, sock):
        messages.RqErrorMsg(err_code='action_not_supported').send(sock)

    @msg_handlers.handler(messages.NearbyMachinesMsg)
    def handle_nearby_machines(self, message, sock):
        self._nearby_machines.mass_update(message.nearby_machines)
        self.current_ip = self._nearby_machines.this_addr_network()
        send_msg(self._publish_socket, message.SerializeToString())

    @msg_handlers.handler(messages.ExperimentFinishedMsg)
    def handle_experiment_finished(self, message, sock):
        # [make mx_messsage]
        # [handler in config_server]
        # stop_all
        # status - finished
        pass

    @msg_handlers.handler(messages.MorphToNewScenarioMsg)
    def handle_morph(self, message, sock):
        # FIXME "LAUNCHING" -- msg bug workaround
        if self.status.status_name not in [launcher_tools.RUNNING, launcher_tools.LAUNCHING]:
            self.logger.error("EXPERIMENT STATUS NOT RUNNING, MORPH NOT ALLOWED")
            if sock.getsockopt(zmq.TYPE) in [zmq.REQ, zmq.ROUTER]:
                messages.RqErrorMsg(
                    err_code='experiment_not_running',
                    details=self.status.details,
                ).send(sock)
            return

        new_launch_file = launcher_tools.obci_root_relative(message.launch_file)
        exp_config, status = self._initialize_experiment_config(new_launch_file,
                                                                message.overwrites)
        self.logger.info("new launch status %s %s", str(exp_config), str(status.status_name))
        if status.status_name != launcher_tools.READY_TO_LAUNCH:
            self.logger.error("NEW SCENARIO NOT READY TO LAUNCH, MOPRH NOT ALLOWED")
            if sock.getsockopt(zmq.TYPE) in [zmq.REQ, zmq.ROUTER]:
                messages.RqErrorMsg(
                    err_code='launch_file_invalid',
                    details=dict(status_name=status.status_name,
                                 details=status.details),
                ).send(sock)
            return

        valid, details = morph.validate_morph_leave_on(self.exp_config, exp_config,
                                                       message.leave_on)
        self.logger.info("morph valid: %s %s", str(valid), str(details))

        if not valid:
            if sock.getsockopt(zmq.TYPE) in [zmq.REQ, zmq.ROUTER]:
                messages.RqErrorMsg(
                    err_code='leave_on_peers_invalid',
                    details=details,
                ).send(sock)
            return

        kill_list, launch_list = morph.diff_scenarios(self.exp_config,
                                                      exp_config, message.leave_on)

        self.logger.info("KILL_LIST " + str(kill_list))
        self.logger.info("LAUNCH_LIST" + str(launch_list))

        old_name = self.name
        old_status = self.status
        self.name = message.name if message.name is not None else new_launch_file
        self.launch_file = new_launch_file
        self.status = status

        old_config = self.exp_config
        self.exp_config = exp_config

        for p in message.leave_on:
            self.exp_config.peers[p] = old_config.peers[p]

        if sock.getsockopt(zmq.TYPE) in [zmq.REP, zmq.ROUTER]:
            messages.StartingExperimentMsg().send(sock)
            self.status.set_status(launcher_tools.LAUNCHING)
            self.notify_server(
                messages.ExperimentTransformationMsg(
                    status_name=self.status.status_name,
                    details=self.status.details,
                    uuid=self.uuid,
                    name=self.name,
                    launch_file=new_launch_file,
                    old_name=old_name,
                    old_launch_file=old_config.launch_file_path,
                ))

        # TODO -- notice obci_server of name/config change

        self._kill_and_launch_peers(kill_list, launch_list, self.exp_config, old_config)
        self._kill_unused_supervisors()

        pst = {}
        for peer in self.status.peers_status:
            if peer not in launch_list and peer not in kill_list:
                self.status.peer_status(peer).set_status(old_status.peer_status(peer).status_name,
                                                         old_status.peer_status(peer).details)

                pst[peer] = self.status.peer_status(peer).status_name

        self.status_changed(self.status.status_name, self.status.details,
                            peers=pst)

        # list: to kill, to restart (unless in leave-on)
        # start supervisors if new machnes specified
        # send launch_data to all
        # start
        # deregister / register in obci_server

    def _kill_and_launch_peers(self, kill_list, launch_list, new_config, old_config):
        kill_data = {}
        for peer in kill_list:
            machine = old_config.peers[peer].machine
            if not machine:
                machine = self.origin_machine
            if machine not in kill_data:
                kill_data[machine] = []
            kill_data[machine].append(peer)

        launch_data = {}
        self._ready_register = 0

        for machine in new_config.peer_machines():
            ldata = new_config.launch_data(machine)
            peers = list(ldata.keys())
            for peer in peers:
                if peer in launch_list:
                    if machine not in launch_data:
                        launch_data[machine] = {}
                    launch_data[machine][peer] = ldata[peer]
                    self._ready_register += 1

        new_supervisors = []
        for machine in launch_data:
            if machine not in old_config.peer_machines():
                new_supervisors.append(machine)

        keep_configs = [peer for peer in old_config.peers if peer not in kill_list]
        self._kill_and_launch = (kill_data, launch_data, new_supervisors, keep_configs)
        if new_supervisors:
            self._wait_register = len(new_supervisors)

            self._start_obci_process_supervisors(new_supervisors)
        # --------------------------------------------------------------------------------------
        self.__cfg_morph = True
        messages.KillPeerMorphMsg(
            peer_id="config_server",
            morph=True,
        ).send(self._publish_socket)

    def _kill_unused_supervisors(self):
        pass

    @msg_handlers.handler(messages.KillMsg)
    def handle_kill(self, message, sock=None):
        if not message.receiver or message.receiver == self.uuid:
            self.status.set_status(launcher_tools.STOPPING)
            self.status_changed(self.status.status_name, self.status.details)
            messages.KillMsg(
                receiver="",
                sender=self.uuid,
                force=message.force,
            ).send(self._publish_socket)
            self.logger.info('sent KILL to supervisors')

            if self._shutdown_thread is None:
                self._shutdown_thread = Thread(target=self._wait_for_subprocesses, args=(message, sock))
                self._shutdown_thread.daemon = True
                self._shutdown_thread.start()

    def __wait_for_subprocesses(self, timeout_callback=None):
        warned = False
        time0 = time.monotonic()
        # for waiting to work and not hang forever, we have to "notify" subprocess manager that w are killing
        # processes he is managing. We have to send message to let subprocess manager react according to the message
        # (force close peers or gracefull shutdown) but subprocess manager doesn't let to send any message to killed
        # peer. On other hand there is lacking support for detection of graceful shutdown of remote peer. So
        # effectively we are killing supervisors twice.
        #
        # But now we can control forcefulness of peer killing and we have ability to wait for remote supervisors to end.
        # Soon to be changed anyways as plans to integrate obci server, experiment and supervisors are incoming.
        while not self._supervisors_finished():
            time.sleep(SUPERVISORS_CHECK_INTERVAL)  # required, ?use condition variable
            if time.monotonic() - time0 > SUPERVISORS_TIMEOUT and not warned:
                warned = True
                if timeout_callback:
                    timeout_callback()

    def _wait_for_subprocesses(self, message, sock):
        self.logger.info('Waiting for supervisors to end')

        def callback():
            self.logger.warn('Process supervisors are taking very long to close '
                             'if something crashed you might want to run '
                             '"obci kill --force %s" to kill this experiment', self.uuid
                             )

        self.__wait_for_subprocesses(timeout_callback=callback)
        self.logger.debug('Supervisors finished, proceeding with shutting down')
        self.interrupted = True  # exiting main run function

    def _supervisors_finished(self):
        supervisors_info = [(i.info()['machine'], i.info()['pid']) for i in self.supervisors.values()]
        return all([self.subprocess_mgr.process(*i).finished() for i in supervisors_info])

    def clean_up(self):
        self.logger.info("exp cleaning up")
        self.subprocess_mgr.killall(force=False)
        self.__wait_for_subprocesses()
        self.subprocess_mgr.stop_monitoring()
        # Shutting down broker (after all peers had shut down)
        if self.broker:
            self.broker.shutdown()
            self.logger.debug('Broker shutdown')

    def _handle_register_sv_timeout(self, sv_process):
        txt = "Supervisor for machine {0} FAILED TO REGISTER before timeout".format(sv_process.machine_ip)
        self.logger.fatal(txt)

        sock = self._push_sock(self.ctx, self._push_addr)

        # inform observers about failure
        messages.ExperimentLaunchErrorMsg(
            sender=self.uuid,
            err_code="create_supervisor_error",
            details=dict(machine=sv_process.machine_ip, error=txt),
        ).send(sock)
        sock.close()

    @msg_handlers.handler(messages.GetTailMsg)
    def handle_get_tail(self, message, sock):
        if self.status.status_name == launcher_tools.RUNNING:
            if message.peer_id not in self.exp_config.peers:
                messages.RqErrorMsg(
                    err_code="peer_not_found",
                    details="No such peer: " + message.peer_id,
                ).send(sock)
                return
            machine = self.exp_config.peer_machine(message.peer_id)
            self.logger.info("getting tail for %s %s", message.peer_id, machine)
            send_msg(self._publish_socket, message.SerializeToString())
            self.client_rq = (message, sock)

    @msg_handlers.handler(messages.TailMsg)
    def handle_tail(self, message, sock):
        if self.client_rq:
            if message.peer_id == self.client_rq[0].peer_id:
                send_msg(self.client_rq[1], message.SerializeToString())

    def _crash_extra_data(self, exception=None):
        import json
        data = super()._crash_extra_data(exception)
        data.update({'experiment_uuid': self.uuid,
                     'launch_file_path': self.launch_file,
                     'name': self.name,
                     'config': json.loads(serialize_scenario_json(self.exp_config))
                     })
        return data

    def _crash_extra_tags(self, exception=None):
        tags = super()._crash_extra_tags(exception)
        tags.update({'experiment_uuid': self.uuid})
        return tags


def experiment_arg_parser():
    parser = argparse.ArgumentParser(parents=[basic_arg_parser()],
                                     description='Create, launch and manage an OBCI experiment.')
    parser.add_argument('--sv-pub-addresses', nargs='+',
                        help='Addresses of the PUB socket of the supervisor')
    parser.add_argument('--sandbox-dir',
                        help='Directory to store temporary and log files')
    parser.add_argument('--launch-file',
                        help='Experiment launch file')
    parser.add_argument('--name', default=OBCIExperiment.PEER_TYPE,
                        help='Human readable name of this process')
    parser.add_argument('--launch', default=False,
                        help='Launch the experiment specified in launch file')
    parser.add_argument('--current-ip', help='IP addr of host machine')
    parser.add_argument('--ovr', nargs=argparse.REMAINDER)

    return parser


class LocalOBCIExperiment(LocalThreadedProcess):
    def __init__(self, args, machine):
        proc_type = 'obci_experiment'
        process_desc = ProcessDescription(proc_type=proc_type,
                                          name=proc_type,
                                          path=proc_type,
                                          args=args,
                                          machine_ip=machine,
                                          pid=0)
        super().__init__(process_desc, io_handler=None,
                         reg_timeout_desc=None,
                         logger=None)

    def _create_peer(self):
        args = experiment_arg_parser().parse_args(self.desc.args)
        log_source_name = '{} - {}'.format(args.name, time.strftime("%Y%m%dT%H%M%S"))
        if args.ovr is not None:
            pack = peer_overwrites_pack(args.ovr)
        else:
            pack = None
        return OBCIExperiment(
            args.sandbox_dir,
            args.launch_file,
            args.sv_addresses,
            args.sv_pub_addresses,
            args.rep_addresses,
            args.pub_addresses,
            args.name,
            args.current_ip,
            args.launch,
            overwrites=pack,
            log_source_name=log_source_name
        )


def run_obci_experiment():
    install_sentry()
    enable_handlers(['srv'])
    ParentCheckingThread().start()
    args = experiment_arg_parser().parse_args()
    pack = None
    if args.ovr is not None:
        pack = peer_overwrites_pack(args.ovr)

    log_source_name = '{} - {}'.format(args.name, time.strftime("%Y%m%dT%H%M%S"))
    for handler in logging.getLogger().handlers:
        try:
            handler.connect(args.sv_addresses, log_source_name, True)
        except (AttributeError, TypeError):
            pass

    version = braintech.obci.core.__version__
    logging.getLogger().info('Starting {} (obci version {})'
                             .format(OBCIExperiment.PEER_TYPE, version))

    exp = OBCIExperiment(
        args.sandbox_dir,
        args.launch_file,
        args.sv_addresses,
        args.sv_pub_addresses,
        args.rep_addresses,
        args.pub_addresses,
        args.name,
        args.current_ip,
        args.launch,
        overwrites=pack,
        log_source_name=log_source_name
    )
    LocalProcess.install_kill_handler(exp.shutdown, exp.logger)
    exp.run()
