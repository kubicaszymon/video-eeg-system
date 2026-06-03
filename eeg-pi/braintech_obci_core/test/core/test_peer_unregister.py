# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import uuid
from threading import Event

import pytest

from braintech.obci.core.broker import messages
from braintech.obci.core.broker.peer import Peer
from braintech.obci.core.broker.broker import Broker
from braintech.obci.core.broker.peer import PeerInitUrls
from braintech.obci.core.broker.message_handler_mixin import subscribe_message_handler
from braintech.obci.core.utils import wait_until_peers_ready, yield_then_shutdown

import asyncio
import time

URLS = {
    'broker_rep': 'tcp://127.0.0.1:20001',
    'broker_xpub': 'tcp://127.0.0.1:20002',
    'broker_xsub': 'tcp://127.0.0.1:20003',
    'peer_pub': 'tcp://127.0.0.1:*',
    'peer_rep': 'tcp://127.0.0.1:*',
}


class PanicCatcherPeer(Peer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.panic_received = Event()

    async def _connections_established(self):
        await super()._connections_established()

    @subscribe_message_handler(messages.PanicMsg)
    async def _handle_panic(self, msg):
        self._logger.debug('CAPTURED PANIC')
        self.panic_received.set()
        await super()._handle_panic(msg)


class FailingPeer(Peer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def _heartbeat(self) -> None:
        """Periodically send ``HEARTBEAT`` messages."""
        self._logger.debug("Peer '%s': Starting heartbeat...", self.id)
        heartbeat_message = messages.HeartbeatMsg()
        next_heartbeat = time.monotonic()
        hb_sent = 0
        while True:
            if hb_sent < 3:
                await self._send_message(heartbeat_message)
                hb_sent += 1
            cur_time = time.monotonic()
            next_heartbeat = max(next_heartbeat + self._heartbeat_delay, cur_time)
            sleep_duration = next_heartbeat - cur_time
            await asyncio.sleep(sleep_duration)


# -------------------------------- Fixtures: ----------------------------------

@pytest.fixture
def broker():
    yield from yield_then_shutdown(
        Broker(
            None,
            [URLS['broker_rep']],
            [URLS['broker_xpub']],
            [URLS['broker_xsub']]
        )
    )


@pytest.fixture
def plain_peer():
    urls = PeerInitUrls(
        pub_urls=[URLS['peer_pub']],
        rep_urls=[URLS['peer_rep']],
        broker_rep_url=URLS['broker_rep'])
    peerid = 'testing_peer_{}'.format(uuid.uuid4())
    yield from yield_then_shutdown(Peer(urls, peerid))


@pytest.fixture
def failing_peer(broker):
    urls = PeerInitUrls(
        pub_urls=[URLS['peer_pub']],
        rep_urls=[URLS['peer_rep']],
        broker_rep_url=URLS['broker_rep'])
    peerid = 'failing_peer_{}'.format(uuid.uuid4())
    yield from yield_then_shutdown(FailingPeer(urls, peerid))


@pytest.fixture
def panic_catcher_peer(broker):
    urls = PeerInitUrls(
        pub_urls=[URLS['peer_pub']],
        rep_urls=[URLS['peer_rep']],
        broker_rep_url=URLS['broker_rep'],
    )
    yield from yield_then_shutdown(PanicCatcherPeer(urls, 'PanicReceiver'))


# ---------------------------------- Tests: -----------------------------------

def test_peer_unregister(plain_peer, broker):
    wait_until_peers_ready([broker, plain_peer])
    plain_peer.shutdown()
    assert plain_peer.id not in broker._peers
    assert not broker._query_handlers


def test_peer_unregister_error(panic_catcher_peer, plain_peer, broker):
    wait_until_peers_ready([broker, panic_catcher_peer, plain_peer])
    plain_peer.create_task(plain_peer.send_panic('CRASH'))
    assert panic_catcher_peer.panic_received.wait()


def test_sending_panic_on_no_heartbeat_from_failed_peer(panic_catcher_peer,
                                                        failing_peer, broker):
    broker.heartbeat_error_interval = 0.5
    broker.heartbeat_warning_interval = 0.2
    wait_until_peers_ready([broker, panic_catcher_peer, failing_peer])
    assert panic_catcher_peer.panic_received.wait()
