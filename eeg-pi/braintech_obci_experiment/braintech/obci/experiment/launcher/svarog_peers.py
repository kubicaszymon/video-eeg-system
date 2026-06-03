# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.
import enum
import pathlib
import uuid
from threading import Thread

import zmq
try:
    from braintech.obci.lab.peers.video.video_saver_peer import LiteVideoSaverPeer
except ModuleNotFoundError:  # noqa
    # if loaded without obci_lab then obci server is lite and svarog will never ask for video_recording
    pass

from ..common import message as message_dispatching
from braintech.obci.core.control.common import net
from braintech.obci.core.broker import messages as messages_core
from .. import messages
from ..messages import GetBrokerAddress, RqOkMsg, GetPeerInfoMsg
from braintech.obci.signal_processing.writers import SignalWriter
from ..peers.acquisition.signal_saver_peer import LiteSignalSaverPeer, SaverConfig


class Status(enum.Enum):
    INITIALIZATION = 'initialization'
    SAVING = 'saving'
    FINISHING = 'finishing'
    FINISHED = 'finished'
    ERROR = 'error'


class Runner:
    class InvalidDataSent(Exception):
        def __init__(self, details: dict):
            self.details = details
            super().__init__()

    def __init__(self, experiments, machine, zmq_context):
        self._experiments = experiments
        self._machine = machine
        self._zmq_context = zmq_context
        self._saving_sessions = {}

    def handle_start_saving(self, message: messages.SvarogStartSavingSignal, sock):
        experiment_id = message.experiment_id
        saving_session_id = self._generate_new_session_id()
        try:
            self._validate_start_data(message)
        except self.InvalidDataSent as e:
            msg = messages.SvarogSavingSignalError(
                saving_session_id=saving_session_id,
                details=e.details,
            )
        else:
            session = self._create_session(experiment_id, saving_session_id)
            msg = messages.SvarogSavingSignalStarting(
                saving_session_id=saving_session_id,
            )
            session.start(message.signal_source_id, message.signal_filename,
                          message.save_tags, message.video_filename,
                          message.video_stream_url, message.save_impedance, message.append_timestamps)
        msg.send(sock)

    def _generate_new_session_id(self):
        id = uuid.uuid4().hex[:4]
        is_already_taken = id in self._saving_sessions
        if is_already_taken:
            return self._generate_new_session_id()
        else:
            return id

    def _validate_start_data(self, message: messages.SvarogStartSavingSignal):
        experiment_id = message.experiment_id
        is_experiment_present = experiment_id in self._experiments
        if not is_experiment_present:
            message = 'Experiment with id="{}" does not exist.'.format(experiment_id)
            raise self.InvalidDataSent(details={
                'message': message,
                'available experiments ids': list(self._experiments.keys()),
            })

        self._validate_files_writability(message)

    def _validate_files_writability(self, message):
        path = pathlib.Path(message.signal_filename)
        dirname = path.parent
        paths = SignalWriter.get_paths(str(dirname), path.name)
        if not message.save_tags:
            del paths['tag']

        paths = list(paths.values())
        if message.video_filename:
            paths.append(message.video_filename)

        # svarog has already asked user about file overwriting
        for path_string in paths:
            path = pathlib.Path(path_string)
            try:
                path.open('w')
                path.unlink()
            except PermissionError:
                raise self.InvalidDataSent(details={
                    'message': "Path '%s' is not writable" % str(path_string)
                })

    def _create_session(self, experiment_id, saving_session_id):
        experiment_info = self._experiments[experiment_id]
        session = SvarogSavingSession(id=saving_session_id,
                                      experiment_id=experiment_id,
                                      rep_addrs=experiment_info.rep_addrs,
                                      zmq_context=self._zmq_context,
                                      machine=self._machine)
        self._saving_sessions[saving_session_id] = session
        return session

    def handle_check_status(self, message: messages.SvarogCheckSavingSignalStatus,
                            sock):
        saving_session_id = message.saving_session_id
        try:
            session = self._saving_sessions[saving_session_id]
        except KeyError:
            msg = messages.SvarogSavingSignalError(
                saving_session_id=saving_session_id,
                details={
                    'reason': 'passed session id is missing',
                    'present session ids': list(self._saving_sessions.keys()),
                },
            )
        else:
            status = session.get_status()
            if status == Status.ERROR:
                msg = messages.SvarogSavingSignalError(
                    saving_session_id=saving_session_id,
                    details=session.finish_reason or {},
                )
            else:
                msg = messages.SvarogSavingSignalStatus(
                    saving_session_id=saving_session_id,
                    status=status.value,
                )
        msg.send(sock)

    def handle_finish_saving(self, message: messages.SvarogFinishSavingSignal, sock):
        saving_session_id = message.saving_session_id
        try:
            self._validate_finish_data(saving_session_id)
        except self.InvalidDataSent as e:
            msg = messages.SvarogSavingSignalError(
                saving_session_id=saving_session_id,
                details=e.details,
            )
        else:
            session = self._saving_sessions[saving_session_id]
            msg = messages.SvarogSavingSignalFinishing(
                saving_session_id=saving_session_id,
            )
            session.finish_non_block()
        msg.send(sock)

    def _validate_finish_data(self, saving_session_id):
        if saving_session_id not in self._saving_sessions:
            raise self.InvalidDataSent(details={
                'reason': 'passed session id is missing',
                'present session ids': list(self._saving_sessions.keys()),
            })
        session = self._saving_sessions[saving_session_id]
        experiment_id = session.experiment_id
        if experiment_id not in self._experiments:
            raise self.InvalidDataSent(details={
                'reason': 'experiment is gone',
                'experiment id': experiment_id,
            })
        status = session.get_status()
        if status != Status.SAVING:
            raise self.InvalidDataSent(details={
                'reason': 'session is not saving',
                'current session status': str(status),
            })


class SvarogSavingSession:
    def __init__(self, id, experiment_id, rep_addrs, zmq_context, machine):
        self.id = id
        self.experiment_id = experiment_id
        self._rep_addrs = rep_addrs
        self._zmq_context = zmq_context
        self._machine = machine
        self._poller = message_dispatching.PollingObject()
        self._signal_saver_id = None
        self._video_saver_id = None
        self._finish_ran_manually = False
        self.finish_reason = None
        # get broker address
        self.broker_address = self._get_broker_address()
        self._finishing = False

    def start(self, signal_source_id, signal_filename, save_tags,
              video_filename, video_stream_url, save_impedance, append_timestamps):
        self._signal_saver_id = self._start_signal_saver(signal_source_id, signal_filename, save_tags, save_impedance,
                                                         append_timestamps)
        if video_stream_url:
            self._video_saver_id = self._start_video_saver(video_filename,
                                                           video_stream_url)

    def _start_signal_saver(self, signal_source_id, signal_filename, save_tags, save_impedance, append_timestamps):
        peer_id = 'signal_saver_for_svarog-{}'.format(self.id)
        path = pathlib.Path(signal_filename)

        amplifier_info = messages_core.deserialize(self._send_to_experiment(GetPeerInfoMsg(peer_id='amplifier')))
        amp_params = amplifier_info.local_params

        saver_config = SaverConfig(int(append_timestamps), int(save_impedance),
                                   path.name, str(path.parent), int(save_tags),
                                   amp_params)

        self._signal_saver_peer = LiteSignalSaverPeer(self.broker_address, saver_config, peer_id=peer_id)
        return peer_id

    def _get_broker_address(self):
        answer = messages_core.deserialize(self._send_to_experiment(GetBrokerAddress()))
        if isinstance(answer, RqOkMsg):
            ip = answer.status
        else:
            raise Exception("Experiment returned unexpected answer")
        return ip

    def _start_video_saver(self, video_filename, video_stream_url):
        peer_id = 'video_saver_for_svarog-{}'.format(self.id)
        if video_filename.endswith('/'):
            video_filename += 'video'
        saver_video_extension = '.mkv'
        if not video_filename.endswith(saver_video_extension):
            video_filename += saver_video_extension
        save_path = video_filename

        self._video_saver_peer = LiteVideoSaverPeer(self.broker_address, save_path, video_stream_url, peer_id=peer_id)
        return peer_id

    def get_status(self):
        peers_to_check = []
        if self._signal_saver_id is not None:
            peers_to_check += [self._signal_saver_peer]
        if self._video_saver_id is not None:
            peers_to_check += [self._video_saver_peer]
        if not peers_to_check:
            if self._finish_ran_manually:
                return Status.FINISHED
            else:
                return Status.INITIALIZATION

        aggregated_status = self._aggregate_statuses(peers_to_check)
        has_finished_prematurely = (aggregated_status == Status.FINISHED
                                    and not self._finish_ran_manually) or aggregated_status == Status.ERROR
        if has_finished_prematurely:
            failed_peers = [peer for peer in peers_to_check if peer.is_failed]
            all_details = {}
            for peer in failed_peers:
                all_details[str(peer.id)] = str(peer.panic_reason)
            self.finish(is_manual=False, reason=all_details)
            return Status.ERROR
        elif aggregated_status == Status.ERROR:
            failed_peers = [peer for peer in peers_to_check if peer.is_failed]
            all_details = {}
            for peer in failed_peers:
                all_details[str(peer.id)] = str(peer.panic_reason)
            return aggregated_status
        else:
            return aggregated_status

    def _get_experiment_details(self):
        message = messages.GetExperimentInfoMsg()
        response = self._send_to_experiment(message)
        if response:
            response = messages_core.deserialize(response)
            assert isinstance(response, messages.ExperimentInfoMsg)
            return response.dict()
        else:
            assert False, "No response from the server."

    def _aggregate_statuses(self, peers):
        if any(peer.is_failed for peer in peers):
            return Status.ERROR
        elif all(peer.is_finished for peer in peers):
            return Status.FINISHED
        elif self._finishing:
            return Status.FINISHING
        elif all(peer.signal_saving_session_active for peer in peers):
            return Status.SAVING

        elif any((s.is_connected or s.is_ready or s.is_initializing or s.is_running) for s in peers):
            return Status.INITIALIZATION
        else:
            assert False, []

    def finish(self, is_manual=True, reason=()):
        self._finishing = True
        self._finish_ran_manually = self._finish_ran_manually or is_manual
        self._finish_peer(self._signal_saver_peer)
        if self._video_saver_id:
            self._finish_peer(self._video_saver_peer)
        self.finish_reason = reason

    def finish_non_block(self):
        self._finishing = True
        finishing_thread = Thread(target=self.finish, name="saving finishing")
        finishing_thread.daemon = True
        finishing_thread.start()

    def _finish_peer(self, peer):
        if peer is not None:
            try:
                peer.shutdown()
            except Exception:
                # it was already sent to logs or handled
                pass

    def _send_to_experiment(self, message):
        rep_addrs = net.filter_not_local(self._rep_addrs) or self._rep_addrs
        sock = self._zmq_context.socket(zmq.REQ)
        try:
            for addr in rep_addrs:
                sock.connect(addr)
            message.send(sock)
            response, _ = self._poller.poll_recv(sock, 2000)
            return response
        finally:
            sock.close()
