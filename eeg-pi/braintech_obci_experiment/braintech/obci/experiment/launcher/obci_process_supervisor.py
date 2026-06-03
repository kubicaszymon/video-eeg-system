# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import argparse
import logging
import os
import socket
import threading
import time

import zmq

import braintech.obci.experiment.launcher.launcher_tools as launcher_tools
from braintech.obci.core.conf import settings
from braintech.obci.core.control.common import net
from braintech.obci.experiment.error_reporting import install_sentry

from ..common.message import send_msg
from braintech.obci.experiment.launcher.launcher_tools import PROCESS_TO_LAUNCHER_STATUS
from braintech.obci.experiment.launcher.local_process import LocalThreadedProcess, LocalProcess
from braintech.obci.experiment.launcher.obci_control_peer import OBCIControlPeer, basic_arg_parser
from braintech.obci.experiment.launcher.peer_loader import default_config_path
from braintech.obci.experiment.launcher.process import TERMINATED
from braintech.obci.experiment.launcher.process_io_handler import DEFAULT_TAIL_RQ
from braintech.obci.experiment.launcher.subprocess_monitor import (SubprocessMonitor, NO_STDIO,
                                                                   RETURNCODE, ProcessDescription)
from braintech.obci.experiment import messages
from ..peers.control.config_server import ConfigServer
from braintech.obci.core.utils.openbci_logging import enable_handlers
from braintech.obci.core.utils.parent_checking import ParentCheckingThread

TEST_PACKS = 100000


class OBCIProcessSupervisor(OBCIControlPeer):
    msg_handlers = OBCIControlPeer.msg_handlers.copy()
    PEER_TYPE = 'process_supervisor'

    def __init__(self,
                 sandbox_dir,
                 source_addresses=None,
                 source_pub_addresses=None,
                 rep_addresses=None,
                 pub_addresses=None,
                 experiment_uuid='',
                 name=PEER_TYPE,
                 ):
        self.peers = {}
        self.status = launcher_tools.READY_TO_LAUNCH
        self.source_pub_addresses = source_pub_addresses
        self.machine = net.gethostname()
        self.sandbox_dir = sandbox_dir if sandbox_dir else settings.sandbox_dir
        self.ctx = zmq.Context()
        self.mx_data = self.set_mx_data()
        self.env = self.peer_env(self.mx_data)
        self.launch_data = []
        self.peer_order = []
        self._running_peer_order = []
        self._current_part = None
        self.__cfg_launch_info = None
        self.__cfg_morph = False
        self.experiment_uuid = experiment_uuid
        self.peers_to_launch = []
        self.processes = {}
        self.restarting = []
        self.rqs = 0
        self._nearby_machines = net.DNS()

        self.test_count = 0
        self.__cfg_lock = threading.RLock()

        super().__init__(
            source_addresses=source_addresses,
            rep_addresses=rep_addresses,
            pub_addresses=pub_addresses,
            name=name
        )
        self.subprocess_mgr = SubprocessMonitor(self.ctx, self.uuid, logger=self.logger)

    def net_init(self):
        self.source_sub_socket = self.ctx.socket(zmq.SUB)
        self.source_sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

        self._all_sockets.append(self.source_sub_socket)

        if self.source_pub_addresses:
            for addr in self.source_pub_addresses:
                self.source_sub_socket.connect(addr)

        self.config_server_socket, self.cs_addresses = self._init_socket([], zmq.PULL)

        self.cs_addr = net.filter_local(self.cs_addresses)
        if not self.cs_addr:
            self.cs_addr = net.filter_not_local(self.cs_addresses)[0]
        else:
            self.cs_addr = self.cs_addr[0]

        self._all_sockets.append(self.config_server_socket)

        super(OBCIProcessSupervisor, self).net_init()

    def params_for_registration(self):
        mx_data = None
        if None not in self.mx_data:
            mx_data = [self.mx_addr_str(((net.gethostname(), self.mx_data[0][1]), self.mx_data[1])), self.mx_data[1]]
        pid = os.getpid()
        return dict(pid=pid, machine=self.machine,
                    mx_data=mx_data)

    def custom_sockets(self):
        return [self.source_sub_socket, self.config_server_socket]

    def _handle_registration_response(self, response):
        self.launch_data = response.params['launch_data']
        self.peers_to_launch = list(self.launch_data.keys())
        self.peer_order = response.params['peer_order']
        for part in self.peer_order:
            self._running_peer_order.append(list(part))
        self.logger.info("RECEIVED LAUNCH DATA: %s", self.launch_data)

    def set_mx_data(self):

        src_ = net.filter_not_local(self.source_pub_addresses)[:1]
        if not src_:
            src_ = net.filter_local(self.source_pub_addresses, ip=True)[:1]
        src = src_[0]
        src = src[6:].split(':')[0]
        if src == net.gethostname():
            sock = self.ctx.socket(zmq.REP)
            port = str(sock.bind_to_random_port("tcp://127.0.0.1",
                                                min_port=settings.broker_port_range[0],
                                                max_port=settings.broker_port_range[1]))
            sock.close()
            return ('0.0.0.0', port), ""  # empty passwd
        else:
            return None, None

    def mx_addr_str(self, mx_data):
        if mx_data[0] is None:
            return None
        addr, port = mx_data[0]
        self.logger.info("mx addr str:  " + addr + ':' + str(port))
        return addr + ':' + str(port)

    def peer_env(self, mx_data):
        if mx_data[0] is None:
            return None

        env = os.environ.copy()
        addr, port = mx_data[0]
        if addr == '0.0.0.0':
            addr = net.gethostname()

        _env = {
            "BROKER_ADDRESSES": socket.gethostbyname(addr) + ':' + str(port)
        }
        env.update(_env)
        return env

    @msg_handlers.handler(messages.StartConfigServerMsg)
    def handle_start_config_srv(self, message, sock):
        if 'mx' not in self.launch_data:
            mx_addr = message.mx_data[1].split(':')
            mx_addr[1] = int(mx_addr[1])
            md = list(self.mx_data)
            md[0] = tuple(mx_addr)
            self.mx_data = tuple(md)
            self.env = self.peer_env(self.mx_data)
        if "config_server" in self.launch_data:
            self.launch_process("config_server", self.launch_data["config_server"],
                                restore_config=message.restore_config)
            tim = threading.Timer(1.5, self.__if_config_server_conn_didnt_work)
            tim.start()

    def __if_config_server_conn_didnt_work(self):
        with self.__cfg_lock:
            if self.__cfg_launch_info:
                try:
                    send_msg(self._publish_socket, self.__cfg_launch_info)
                except zmq.error.ZMQError:
                    pass
                self.__cfg_launch_info = None
                self.logger.error("connection to config server is shaky :(")

    @msg_handlers.handler(messages.StartPeersMsg)
    def handle_start_peers(self, message, sock):
        self.logger.info("start peers --  my mx_data: %s, received mx_data: %s",
                         self.mx_data, message.mx_data)
        if 'mx' not in self.launch_data:
            mx_addr = message.mx_data[1].split(':')
            mx_addr[1] = int(mx_addr[1])
            md = list(self.mx_data)
            md[0] = tuple(mx_addr)
            self.mx_data = tuple(md)
            self.env = self.peer_env(self.mx_data)
            # tmp.workarounds: wait for mx  on other machine to initialize
            time.sleep(0.75)  # XXX strange sleep

        if message.add_launch_data:
            if self.machine in message.add_launch_data:
                self._launch_processes(message.add_launch_data[self.machine])
        else:
            self._launch_processes(self.launch_data)

    @msg_handlers.handler(messages.ManagePeersMsg)
    def handle_manage_peers(self, message, sock):
        if not message.receiver == self.uuid:
            return

        for peer in message.kill_peers:
            proc = self.processes.get(peer, None)
            if not proc:
                self.logger.error("peer to kill not found: %s", peer)
                continue
            self.logger.info("MORPH:  KILLING %s ", peer)
            proc.kill_with_force()
            self.logger.info("MORPH:  KILLED %s ", peer)
            del self.processes[peer]
            del self.launch_data[peer]

        for peer, data in message.start_peers_data.items():
            self.launch_data[peer] = data
        self.restarting = [peer for peer in message.start_peers_data if peer in message.kill_peers]

        self._launch_processes(message.start_peers_data)

    def _launch_processes(self, launch_data, restore_config=()):
        success = True

        self.status = launcher_tools.LAUNCHING

        ldata = []

        if 'amplifier' in launch_data:
            ldata.append(('amplifier', launch_data['amplifier']))
        for peer, data in launch_data.items():
            if (peer, data) not in ldata and peer != 'config_server':
                ldata.append((peer, data))

        for peer, data in ldata:
            if peer.startswith('mx'):
                continue
            proc, details, wait, info_obj = self.launch_process(peer, data, restore_config=restore_config)
            time.sleep(wait)
            if proc is None:
                success = False
                break

        if success:
            messages.AllPeersLaunchedMsg(
                machine=self.machine,
            ).send(self._publish_socket)

    def launch_process(self, peer, launch_data, restore_config=()):
        data = launch_data
        wait = 0
        path = data['path']
        args = data['args']
        args = self._attach_base_config_path(path, args)
        args += ['-p', 'experiment_uuid', self.experiment_uuid]
        if peer.startswith('config_server'):
            args += ['-p', 'launcher_socket_addr', self.cs_addr]

            if restore_config:
                args += ['-p', 'restore_peers', ' '.join(restore_config)]
        if "log_dir" in args:
            idx = args.index("log_dir") + 1
            log_dir = args[idx]
            log_dir = os.path.join(log_dir, self.name)
            args[idx] = log_dir
        else:
            log_dir = os.path.join(settings.log_dir, self.name)
            args += ['-p', 'log_dir', log_dir]
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        proc, details = self._launch_process('obci_run_peer', [path] + args, data['peer_type'],
                                             peer, env=self.env, capture_io=NO_STDIO)
        info_obj = {
            "path": path,
            "args": args,
            "peer": peer
        }
        if proc is not None:
            self.processes[peer] = proc
        else:
            self.logger.fatal("OBCI LAUNCH FAILED")
            messages.ObciLaunchFailedMsg(
                machine=self.machine,
                path=info_obj['path'],
                args=info_obj['args'],
                details=details,
            ).send(self._publish_socket)
            self.processes = {}
            self.subprocess_mgr.killall(force=True)

        return proc, details, wait, info_obj

    def _launch_process(self, path, args, proc_type, name,
                        env=None, capture_io=NO_STDIO):
        self.logger.debug("launching..... %s %s", path, args)
        if name.startswith('config_server'):
            proc = LocalConfigServer(args, self.machine, env['BROKER_ADDRESSES'])
            self.subprocess_mgr._add_process(proc)
            details = ''
        else:
            proc, details = self.subprocess_mgr.new_local_process(path, args,
                                                                  proc_type=proc_type,
                                                                  name=name,
                                                                  monitoring_optflags=RETURNCODE,
                                                                  capture_io=capture_io,
                                                                  env=env)

        if proc is None:
            self.logger.fatal("process launch FAILED: %s --- %s",
                              path, str(args))
            messages.LaunchErrorMsg(
                sender=self.uuid,
                details=dict(machine=self.machine, path=path,
                             args=args, error=details, peer_id=name),
            ).send(self._publish_socket)
        else:
            self.logger.info("process launch success:" +
                             path + str(args) + str(proc.pid))
            msg = messages.LaunchedProcessInfoMsg(
                sender=self.uuid,
                machine=self.machine,
                pid=proc.pid,
                proc_type=proc_type,
                name=name,
                path=path,
                args=args
            ).serialize()
            if name == "config_server":
                self.__cfg_launch_info = msg
            else:
                send_msg(self._publish_socket, msg)
        return proc, details

    def _attach_base_config_path(self, launch_path, launch_args):
        peer_id = launch_args[0]
        ini = default_config_path(launch_path)
        return [peer_id, ini] + launch_args[1:]

    @msg_handlers.handler(messages.GetTailMsg)
    def handle_get_tail(self, message, sock):
        lines = message.len if message.len else DEFAULT_TAIL_RQ
        peer = message.peer_id
        if peer not in self.launch_data:
            return
        experiment_id = self.launch_data[peer]['experiment_id']
        txt = self.processes[peer].tail_stdout(lines=lines)
        messages.TailMsg(
            txt=txt,
            sender=self.uuid,
            experiment_id=experiment_id,
            peer_id=peer,
        ).send(self._publish_socket)

    @msg_handlers.handler(messages.ExperimentFinishedMsg)
    def handle_experiment_finished(self, message, sock):
        pass

    @msg_handlers.handler(messages.MorphToNewScenarioMsg)
    def handle_morph(self, message, sock):
        pass

    @msg_handlers.handler(messages.NearbyMachinesMsg)
    def handle_nearby_machines(self, message, sock):
        self._nearby_machines.mass_update(message.nearby_machines)

    @msg_handlers.handler(messages.StopAllMsg)
    def handle_stop_all(self, message, sock):
        self._run_killing_thread(force=False)

    @msg_handlers.handler(messages.KillPeerMorphMsg)
    def handle_kill_peer(self, message, sock):
        proc = self.processes.get(message.peer_id, None)

        if proc is not None:  # is on this machine
            if message.morph and message.peer_id == 'config_server':
                self.__cfg_morph = True
            proc.kill()

    @msg_handlers.handler(messages.RqOkMsg)
    def handle_rq_ok(self, message, sock):
        self.rqs += 1
        # print "--> ", self.rqs
        if self.rqs == 10000:
            self.logger.debug("GOT %s %s", str(self.rqs), "messages!")
            self.rqs = 0

    @msg_handlers.handler(messages.ExperimentLaunchErrorMsg)
    def handle_experiment_launch_error(self, message, sock):
        self._run_killing_thread(True)

    @msg_handlers.handler(messages.DeadProcessMsg)
    def handle_dead_process(self, message, sock):
        proc = self.subprocess_mgr.process(message.machine, message.pid)
        if proc is not None:
            proc.mark_delete()
            name = proc.name
            if proc.proc_type == 'obci_peer' and not (name in self.restarting and message.status[0] == TERMINATED):
                self.logger.info("KILLLING! sending obci_peer_"
                                 "dead for process %s", proc.name)

                process_status, details = proc.status()
                assert process_status in PROCESS_TO_LAUNCHER_STATUS
                status = PROCESS_TO_LAUNCHER_STATUS[process_status], details

                messages.ObciPeerDeadMsg(
                    sender=self.uuid,
                    sender_ip=self.machine,
                    peer_id=proc.name,
                    path=proc.path,
                    status=status,
                ).send(self._publish_socket)
            if name in self.restarting:
                self.restarting.remove(name)
            if self.__cfg_morph and name == 'config_server':
                self.__cfg_morph = False

    @msg_handlers.handler(messages.ObciPeerRegisteredMsg)
    def handle_obci_peer_registered(self, message, sock):
        send_msg(self._publish_socket, message.SerializeToString())

    @msg_handlers.handler(messages.ObciPeerParamsChangedMsg)
    def handle_obci_peer_params_changed(self, message, sock):
        send_msg(self._publish_socket, message.SerializeToString())

    @msg_handlers.handler(messages.ObciPeerReadyMsg)
    def handle_obci_peer_ready(self, message, sock):
        self.logger.info("got! " + message.type)
        send_msg(self._publish_socket, message.SerializeToString())

    @msg_handlers.handler(messages.ConfigServerReadyMsg)
    def handle_obci_config_server_ready(self, message, sock):
        # config_server successfully connected to MX, now send "launched_process_info"
        with self.__cfg_lock:
            if self.__cfg_launch_info:
                send_msg(self._publish_socket, self.__cfg_launch_info)
                self.__cfg_launch_info = None

    @msg_handlers.handler(messages.ObciControlMessageMsg)
    def handle_obci_control_message(self, message, sock):
        # ignore :)
        pass

    @msg_handlers.handler(messages.ObciPeerDeadMsg)
    def handle_obci_peer_dead(self, message, sock):
        # ignore :)
        pass

    @msg_handlers.handler(messages.ProcessSupervisorRegisteredMsg)
    def handle_supervisor_registered(self, messsage, sock):
        # also ignore
        pass

    @msg_handlers.handler(messages.KillMsg)
    def handle_kill(self, message, sock):
        self._stop_monitoring = True
        self._run_killing_thread(message.force)

    def _run_killing_thread(self, force):
        killing_thread = threading.Thread(target=self._killing_thread, args=(force,))
        killing_thread.daemon = True
        killing_thread.start()

    def _killing_thread(self, force: bool):
        shutdown_order = self.reversed_peer_order(self.peer_order)
        self.subprocess_mgr.killall(force=force, order=shutdown_order)
        self.interrupted = True

    def reversed_peer_order(self, order):
        result = []
        reversed_tree = reversed(order)
        for el in reversed_tree:
            if isinstance(el, str):
                result.append(el)
            else:
                result += self.reversed_peer_order(el)
        return result

    def clean_up(self):
        self.logger.info("cleaning up")
        self.processes = {}
        self.subprocess_mgr.killall(force=True)
        self.subprocess_mgr.delete_all()

    def _crash_extra_data(self, exception=None):
        data = super(OBCIProcessSupervisor, self)._crash_extra_data(exception)
        data.update({
            'experiment_uuid': self.experiment_uuid,
            'name': self.name
        })
        return data


def process_supervisor_arg_parser():
    parser = argparse.ArgumentParser(parents=[basic_arg_parser()],
                                     description='A process supervisor for OBCI Peers')
    parser.add_argument('--sv-pub-addresses', nargs='+',
                        help='Addresses of the PUB socket of the supervisor')
    parser.add_argument('--sandbox-dir',
                        help='Directory to store temporary and log files')

    parser.add_argument('--name', default='obci_process_supervisor',
                        help='Human readable name of this process')
    parser.add_argument('--experiment-uuid', help='UUID of the parent obci_experiment')
    parser.add_argument('--log-source-name', help='Name for logging handler')
    parser.add_argument('--log-agregator-addresses', nargs='+', help='REP Addresseses for logs aggregator')
    return parser


class LocalConfigServer(LocalThreadedProcess):
    def __init__(self, args, machine, broker_address):
        proc_type = 'config_server'
        process_desc = ProcessDescription(proc_type=proc_type,
                                          name=proc_type,
                                          path=proc_type,
                                          args=args,
                                          machine_ip=machine,
                                          pid=0)
        self._broker_address = broker_address
        super().__init__(process_desc, io_handler=None,
                         reg_timeout_desc=None,
                         logger=None)

    def _create_peer(self):
        args = self.desc.args[1:] + ['--broker-ip', self._broker_address]
        return ConfigServer.create_peer(args)


class LocalProcessSupervisor(LocalThreadedProcess):
    def __init__(self, args, machine):
        process_desc = ProcessDescription(proc_type='obci_process_supervisor',
                                          name='obci_process_supervisor',
                                          path='obci_process_supervisor',
                                          args=args,
                                          machine_ip=machine,
                                          pid=0)
        super().__init__(process_desc, io_handler=None,
                         reg_timeout_desc=None,
                         logger=None)

    def _create_peer(self):
        parser = process_supervisor_arg_parser()
        args = parser.parse_args(self.desc.args)
        return OBCIProcessSupervisor(args.sandbox_dir,
                                     source_addresses=args.sv_addresses,
                                     source_pub_addresses=args.sv_pub_addresses,
                                     rep_addresses=args.rep_addresses,
                                     pub_addresses=args.pub_addresses,
                                     experiment_uuid=args.experiment_uuid,
                                     name=args.name,
                                     )


def run_obci_process_supervisor():
    install_sentry()
    enable_handlers(['srv'])
    ParentCheckingThread().start()
    parser = process_supervisor_arg_parser()
    args = parser.parse_args()

    # we don't finalize this handler, this source name is finalized by experiment
    for log_handler in logging.getLogger().handlers:
        try:
            log_handler.connect(args.log_agregator_addresses, args.log_source_name)
        except AttributeError:
            pass

    process_sv = OBCIProcessSupervisor(args.sandbox_dir,
                                       source_addresses=args.sv_addresses,
                                       source_pub_addresses=args.sv_pub_addresses,
                                       rep_addresses=args.rep_addresses,
                                       pub_addresses=args.pub_addresses,
                                       experiment_uuid=args.experiment_uuid,
                                       name=args.name,
                                       )
    LocalProcess.install_kill_handler(process_sv.shutdown, process_sv.logger)
    process_sv.run()
