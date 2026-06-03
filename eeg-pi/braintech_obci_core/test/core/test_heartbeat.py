# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import math
import time
import threading
import unittest.mock as mock

import pytest
from flaky import flaky

from braintech.obci.core.broker import DEFAULT_HEARTBEAT_DELAY
from braintech.obci.core.broker import messages
from braintech.obci.core.broker.peer import PeerInitUrls
from braintech.obci.core.broker.broker import Broker, PeerInfo
from braintech.obci.core.broker.peer import Peer
from braintech.obci.core.broker.message_handler_mixin import subscribe_message_handler
from braintech.obci.core.utils import wait_until_peers_ready, wait_for_condition, yield_then_shutdown


class HeartbeatMonitoringBroker(Broker):
    """Broker for monitoring it's peers heartbeats."""

    HEARTBEAT_WARNING_INTERVAL = 0.1
    HEARTBEAT_ERROR_INTERVAL = 0.5

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Overwriting intervals for tests purposes
        self.heartbeat_warning_interval = self.HEARTBEAT_WARNING_INTERVAL
        self.heartbeat_error_interval = self.HEARTBEAT_ERROR_INTERVAL

        # Setting timestamps with specific events
        self.hb_error_timestamp = None
        self.hb_error_event = threading.Event()

        self.hb_warning_timestamp = None
        self.hb_warning_event = threading.Event()

        self.hb_jitter_warning_timestamp = None
        self.hb_jitter_warning_event = threading.Event()

    async def _peer_heartbeat_state_changed(self, pi: PeerInfo):
        await super()._peer_heartbeat_state_changed(pi)
        if pi.id != 'HeartbeatGenerator':
            return
        if self.hb_error_timestamp is None and pi.hb_error:
            self.hb_error_timestamp = time.monotonic()
            self.hb_error_event.set()
        if self.hb_warning_timestamp is None and pi.hb_warning:
            self.hb_warning_timestamp = time.monotonic()
            self.hb_warning_event.set()
        if self.hb_jitter_warning_timestamp is None and pi.hb_jitter_warning:
            self.hb_jitter_warning_timestamp = time.monotonic()
            self.hb_jitter_warning_event.set()


class HeartbeatReceiver(Peer):
    HEARTBEATS = 20

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.heartbeats = []
        self.hb_received = threading.Event()

    async def _connections_established(self):
        self._heartbeat_enabled = False
        await super()._connections_established()

    @subscribe_message_handler(messages.HeartbeatMsg)
    async def _handle_heartbeat(self, _):
        self.heartbeats.append(time.monotonic())
        if len(self.heartbeats) >= self.HEARTBEATS:
            self.hb_received.set()


# -------------------------------- Fixtures: ----------------------------------
@pytest.fixture()
def heartbeat_monitoring_broker(broker_rep, broker_xpub, broker_xsub):
    yield from yield_then_shutdown(
        HeartbeatMonitoringBroker(None, [broker_rep], [broker_xpub], [broker_xsub])
    )


@pytest.fixture()
def heartbeat_send_peer(heartbeat_monitoring_broker, broker_rep, peer_pub, peer_rep):
    urls = PeerInitUrls(pub_urls=[peer_pub], rep_urls=[peer_rep], broker_rep_url=broker_rep)
    peer = Peer(urls, 'HeartbeatGenerator')
    yield from yield_then_shutdown(peer)


@pytest.fixture()
def heartbeat_recv_peer(heartbeat_monitoring_broker, broker_rep, peer_pub, peer_rep):
    urls = PeerInitUrls(pub_urls=[peer_pub], rep_urls=[peer_rep], broker_rep_url=broker_rep)
    peer = HeartbeatReceiver(urls, 'HeartbeatReceiver')
    yield from yield_then_shutdown(peer)


# ---------------------------------- Tests: -----------------------------------
@flaky(max_runs=10, min_passes=1)  # race condition.
def test_heartbeat_sending(heartbeat_monitoring_broker, heartbeat_recv_peer, heartbeat_send_peer):
    wait_until_peers_ready([heartbeat_monitoring_broker, heartbeat_send_peer,
                            heartbeat_recv_peer])
    assert heartbeat_recv_peer.hb_received.wait(
        heartbeat_send_peer._heartbeat_delay * heartbeat_recv_peer.HEARTBEATS + 1
    )
    hb = heartbeat_recv_peer.heartbeats
    hb_intervals = [hb[i + 1] - hb[i] for i in range(len(hb) - 1)]
    avg_interval = sum(hb_intervals) / len(hb_intervals)

    # check equality with 10% tolerance
    assert math.isclose(avg_interval, DEFAULT_HEARTBEAT_DELAY, rel_tol=0.1)


@flaky(max_runs=10, min_passes=1)  # race condition.
def test_heartbeat_monitoring(heartbeat_monitoring_broker, heartbeat_send_peer):
    with mock.patch.object(heartbeat_monitoring_broker, 'heartbeat_jitters', lambda heartbeats: False):
        wait_until_peers_ready([heartbeat_monitoring_broker, heartbeat_send_peer])

        # Wait for at leat 1 heartbeat to be delivered
        peer_info = list(heartbeat_monitoring_broker._peers.values())[0]
        wait_for_condition(lambda: len(peer_info.heartbeats))

        heartbeat_send_peer._heartbeat_enabled = False

        condition = (
            heartbeat_monitoring_broker.hb_error_event.wait(4) and
            heartbeat_monitoring_broker.hb_warning_event.wait(4)
        )
        assert condition

        assert heartbeat_monitoring_broker.hb_error_timestamp is not None
        assert heartbeat_monitoring_broker.hb_warning_timestamp is not None
        assert heartbeat_monitoring_broker.hb_warning_timestamp < heartbeat_monitoring_broker.hb_error_timestamp


@flaky(max_runs=10, min_passes=1)  # race condition.
def test_heartbeat_jitters(heartbeat_monitoring_broker, heartbeat_send_peer):
    with mock.patch.object(heartbeat_monitoring_broker, 'heartbeat_jitters') as mock_heartbeat_jitters:
        wait_until_peers_ready([heartbeat_monitoring_broker, heartbeat_send_peer])

        mock_heartbeat_jitters.return_value = False

        # Run until at least 5 heartbeat timestamps are send (requirement to calculate jitter)
        peer = list(heartbeat_monitoring_broker._peers.values())[0]
        wait_for_condition(lambda: len(peer.heartbeats) >= 5)

        assert heartbeat_monitoring_broker.hb_jitter_warning_timestamp is None

        mock_heartbeat_jitters.return_value = True

        assert heartbeat_monitoring_broker.hb_jitter_warning_event.wait(4)
        assert heartbeat_monitoring_broker.hb_jitter_warning_timestamp is not None
