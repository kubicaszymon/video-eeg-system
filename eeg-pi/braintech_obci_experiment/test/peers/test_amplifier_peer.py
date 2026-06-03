#!/usr/bin/env python3
# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import asyncio
import os
import threading
import time
from concurrent.futures import Future

import numpy
import pytest
from flaky import flaky

from braintech.obci.core.broker import messages as messages_core
from braintech.obci.experiment import messages
from braintech.obci.core.broker.message_handler_mixin import subscribe_message_handler, register_message_handler
from braintech.obci.core.broker.peer import Peer
from braintech.obci.experiment.peers.control.config_server import ConfigServer
from braintech.obci.experiment.peers.drivers.amplifiers.file_amplifier_peer import FileAmplifierPeer
from braintech.obci.experiment.peers.drivers.amplifiers.random_amplifier_peer import RandomAmplifierPeer
from braintech.obci.signal_processing.read_manager import ReadManager
from braintech.obci.experiment.test.tools import disable_sampling_rate_check
from braintech.obci.core.utils import get_peer_config_file_path, wait_until_peers_ready, yield_then_shutdown


try:
    from braintech.drivers.native_amplifier_lib.peers.dummy_amplifier_peer import DummyAmplifierPeer
except Exception:
    class DummyAmplifierPeer:
        SKIP_TEST = True

try:
    from braintech.drivers.tmsi.peers.tmsi_amplifier_peer import TmsiAmplifierPeer
except Exception:
    class TmsiAmplifierPeer:
        SKIP_TEST = True


class _TestConfigServer(ConfigServer):

    def __init__(self, *args, **kwargs):
        self.ready_times = {}
        super().__init__(*args, **kwargs)

    @register_message_handler(messages.PeerReady)
    async def _handle_peer_ready(self, msg):
        self.ready_times[msg.sender] = time.time()
        return await super()._handle_peer_ready(msg)


class _TagReceiver(Peer):

    def __init__(self, *args, data_dir='.', **kwargs):
        super().__init__(*args, **kwargs)
        self.reset()
        self.siglen = None
        self.tagnum = None
        self.autoshutdown = 1
        self.autostart = 1

    def reset(self):
        self.taglist = []
        self.tagtimes = []
        self.samples = []

    def set_time0(self):
        self.t0 = time.time()

    def set_lengths(self, siglen, tagnum, sigevent, tagevent):
        self.siglen = siglen
        self.tagnum = tagnum
        self.sigevent = sigevent
        self.tagevent = tagevent

    async def _connections_established(self):
        await super()._connections_established()

    @subscribe_message_handler(messages_core.TagMsg)
    async def handle_tag(self, msg: messages_core.TagMsg):
        self.taglist.append(msg)
        self.tagtimes.append(time.time() - self.t0)
        if len(self.taglist) == self.tagnum:
            self.tagevent.set()

    @subscribe_message_handler(messages_core.SignalMessage)
    async def handle_signal(self, msg: messages_core.SignalMessage):
        for sample in msg.data.samples:
            self.samples.append(sample)
        if len(self.samples) == self.siglen:
            self.sigevent.set()


data_dir = os.path.join(os.path.dirname(__file__), 'data')

file_amplifier_def = FileAmplifierPeer, {'local_params': {'data_file_dir': data_dir, 'data_file_name': 'wakeEEG'}}
tag_amplifier_def = FileAmplifierPeer, {'local_params': {'data_file_dir': data_dir,
                                                         'data_file_name': 'wakeEEG',
                                                         'tags_file_name': 'wakeEEG',
                                                         'info_file_name': 'wakeEEG',
                                                         'autostart': '0'}}


@pytest.fixture
def config_server(broker):
    yield from yield_then_shutdown(
        _TestConfigServer(
            broker.broker_ip,
            peer_id='config_server',
            base_config_file=get_peer_config_file_path(ConfigServer)
        )
    )


@pytest.fixture
def tags_signal():
    rm = ReadManager(os.path.join(data_dir, 'wakeEEG.obci.xml'),
                     os.path.join(data_dir, 'wakeEEG.obci.raw'),
                     os.path.join(data_dir, 'wakeEEG.obci.tag'))
    yield rm.get_tags(), rm


tmsi_input_url = 'file://' + os.path.join(data_dir, 'tmsi_raw_data_1')


def _amplifier(request, broker, config_server):
    AmplifierClass, kwargs = request.param
    amplifier = AmplifierClass(broker.broker_ip,
                               external_config_file=None,
                               base_config_file=get_peer_config_file_path(AmplifierClass),
                               peer_id='amplifier',
                               **kwargs)
    yield from yield_then_shutdown(amplifier)


@pytest.fixture(
    params=[
        (RandomAmplifierPeer, {}),
        file_amplifier_def,
        pytest.mark.skipif(hasattr(DummyAmplifierPeer, 'SKIP_TEST'),
                           reason='DummyAmplifierPeer not available')((DummyAmplifierPeer, {})),
        pytest.mark.skipif(hasattr(TmsiAmplifierPeer, 'SKIP_TEST'),
                           reason='TmsiAmplifierPeer not available')(TmsiAmplifierPeer,
                                                                     {'peer_id': 'amplifier_id'}, tmsi_input_url),
    ],
    ids=lambda val: val[0].__name__
)
def amplifier(request, broker, config_server):
    yield from _amplifier(request, broker, config_server)


# only amplifiers for test_end_data
@pytest.fixture(params=[file_amplifier_def], ids=lambda val: val[0].__name__)
def ending_amplifier(request, broker, config_server):
    yield from _amplifier(request, broker, config_server)


@pytest.fixture(params=[tag_amplifier_def], ids=lambda val: val[0].__name__)
def tag_amplifier(request, broker, config_server):
    wait_until_peers_ready([config_server, broker])
    amp = _amplifier(request, broker, config_server)
    recv = _TagReceiver(urls=broker.broker_ip, peer_id='TagReceiver', data_dir=data_dir)
    yield next(amp), recv


@pytest.fixture
def peer(broker):
    peer = Peer(broker.broker_ip)
    wait_until_peers_ready([peer])
    peer.first_amp_message = Future()

    def _amp_message(msg):
        if not peer.first_amp_message.done():
            peer.first_amp_message.set_result((msg, time.time()))

    peer.subscribe_for_all_msg_subtype(messages_core.SignalMessage, _amp_message)
    yield from yield_then_shutdown(peer)


def test_ready(peer, amplifier, config_server):
    msg, sample_time = peer.first_amp_message.result(5)
    peer_id = msg.sender
    assert peer_id in config_server.ready_times, "Peer should communicate ready before first sample"
    sample_offset = sample_time - config_server.ready_times[peer_id]
    assert 0 <= sample_offset <= 0.2, "Ready should be just before first sample"

    sample_packet = msg.data
    assert sample_packet.sample_count == amplifier.samples_per_packet
    assert sample_packet.channel_count == len(amplifier.active_channels)
    assert len(amplifier.get_param('channel_gains').split(';')) > 1
    assert len(amplifier.get_param('channel_offsets').split(';')) > 1


@flaky(max_runs=10, min_passes=1)  # this test is a one big (unfixable?) race-condition
@pytest.mark.timeout(30)
def test_no_block(amplifier: Peer):
    wait_until_peers_ready([amplifier])
    amplifier._logger.info('#STOP############')

    amplifier.stop_sampling()

    rate = 4
    real_counter = -1
    test_counter = 0

    if isinstance(amplifier, TmsiAmplifierPeer):
        pytest.skip("TODO this test is not suitable for TmsiAmplifierPeer")

    async def _fast_sampling():
        nonlocal test_counter
        nonlocal real_counter
        sleep_time = 1.0 / (amplifier.sampling_rate * rate / amplifier.samples_per_packet)
        while amplifier.is_sampling:
            if real_counter >= 0:
                test_counter += amplifier.samples_per_packet
            else:
                real_counter = 0
            await asyncio.sleep(sleep_time)

    event = threading.Event()

    standard_get_packet = amplifier._get_packet

    async def custom_get_packet(*args, **kwargs):
        nonlocal real_counter
        if real_counter >= 0:
            real_counter += amplifier.samples_per_packet
        if real_counter >= 16:
            event.set()
        return await standard_get_packet(*args, **kwargs)

    amplifier._get_packet = custom_get_packet

    async def custom_send_message(msg):
        pass  # do not send anything

    amplifier._send_message = custom_send_message
    with disable_sampling_rate_check():
        amplifier.sampling_rate = 16
        amplifier.samples_per_packet = 1
        amplifier._logger.info('#RESET############')

        amplifier.reset()
    amplifier._logger.info('#START############')

    amplifier.start_sampling()

    amplifier.create_task(_fast_sampling())  # this can finish before sampling really started
    amplifier._logger.info('#FAST SAMPLING############')

    assert event.wait()
    assert test_counter > real_counter, 'Test message rate should be faster then amplifier rate'


def test_end_data(ending_amplifier: Peer):
    wait_until_peers_ready([ending_amplifier])  # shuting down of not initialized peers is not working

    ending_amplifier.stop_sampling()
    with disable_sampling_rate_check():
        ending_amplifier.sampling_rate = 2048
        ending_amplifier.samples_per_packet = 512
        ending_amplifier.reset()
    ending_amplifier.start_sampling()
    time.sleep(ending_amplifier._amplifier.duration + 1)
    assert not ending_amplifier.is_sampling, "Amplifier should stop sampling"


def test_tag_sending(tag_amplifier, tags_signal):
    signal_e = threading.Event()
    tags_e = threading.Event()
    wait_until_peers_ready(tag_amplifier)
    tags, rm = tags_signal
    amp, recv = tag_amplifier
    with disable_sampling_rate_check():
        amp.sampling_rate = 5000
        amp.samples_per_packet = 256
        recv.reset()
        recv.set_lengths(rm.get_all_samples().shape[1], len(tags), signal_e, tags_e)
        amp.reset()
    amp.create_task(amp._start())
    recv.set_time0()

    assert signal_e.wait(10)
    assert tags_e.wait(5)

    for n, tag in enumerate(tags):
        tagname = tag['name']
        tag_recv = recv.taglist[n]
        assert tag_recv.name == tagname
    for n, i in enumerate(rm.iter_samples()):
        assert numpy.array_equal(recv.samples[n], i)
