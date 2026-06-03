# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import asyncio
import time
import threading
import pytest

import zmq.asyncio

from braintech.obci.core.broker.base_peer import BasePeer
from braintech.obci.core.broker.peer import Peer, PeerInitUrls
from braintech.obci.core.broker.broker import Broker

from braintech.obci.experiment.peers.test.dummy_amplifier import DummyAmplifierPeer
from braintech.obci.experiment.peers.test.dummy_signal_receiver import DummySignalReceiverPeer
from braintech.obci.experiment.peers.test.dummy_signal_verifier import DummySignalVerifierPeer

from braintech.obci.core.utils import wait_until_peers_ready, wait_for_condition

broker_rep = 'tcp://127.0.0.1:20001'
broker_xpub = 'tcp://127.0.0.1:20002'
broker_xsub = 'tcp://127.0.0.1:20003'
peer_pub = 'tcp://127.0.0.1:*'
peer_rep = 'tcp://127.0.0.1:*'


@pytest.fixture(params=[[None, None],
                        [BasePeer.new_event_loop(), None],
                        [None, zmq.asyncio.Context()],
                        [BasePeer.new_event_loop(), zmq.asyncio.Context()],
                        ],
                ids=['own loop, own context',
                     'shared loop, own context',
                     'own loop, shared context',
                     'shared loop, shared context',
                     ]
                )
def peers_with_broker(request):
    asyncio_loop, zmq_context = request.param
    if asyncio_loop is not None:
        running = threading.Event()

        def run():
            asyncio.set_event_loop(asyncio_loop)
            running.set()
            asyncio_loop.run_forever()

        thread = threading.Thread(target=run, name="Asyncio Loop")
        thread.start()
        assert running.wait(1)

    broker = Broker(None, [broker_rep], [broker_xpub], [broker_xsub],
                    asyncio_loop=asyncio_loop, zmq_context=zmq_context)

    urls = PeerInitUrls(pub_urls=[peer_pub],
                        rep_urls=[peer_rep],
                        broker_rep_url=broker_rep)

    generator_peer = DummyAmplifierPeer(urls, 'Generator',
                                        asyncio_loop=asyncio_loop,
                                        zmq_context=zmq_context)
    receiver_peer = DummySignalReceiverPeer(urls, 'Receiver',
                                            asyncio_loop=asyncio_loop,
                                            zmq_context=zmq_context)
    verifier_peer = DummySignalVerifierPeer(urls, 'Verifier',
                                            asyncio_loop=asyncio_loop,
                                            zmq_context=zmq_context)
    extra_peer = Peer(urls, 'ExtraPeer',
                      asyncio_loop=asyncio_loop,
                      zmq_context=zmq_context)

    all_peers = (generator_peer, receiver_peer, verifier_peer, extra_peer)

    wait_until_peers_ready([broker] + list(all_peers))
    yield all_peers
    verifier_peer.shutdown()
    receiver_peer.shutdown()
    generator_peer.shutdown()
    extra_peer.shutdown()
    broker.shutdown()

    if asyncio_loop is not None:
        asyncio_loop.call_soon_threadsafe(asyncio_loop.stop)
        thread.join(5)
        assert not thread.isAlive()
        asyncio_loop.close()

    if zmq_context is not None:
        zmq_context.destroy(linger=0)


def test_basic_dummy_amp_and_verifier(peers_with_broker):
    generator_peer, receiver_peer, verifier_peer, extra_peer = peers_with_broker

    generator_peer.create_task(generator_peer.generate_test_signal())

    time.sleep(0.5)

    extra_peer.shutdown()
    verifier_peer.signal_ok = None
    wait_for_condition(lambda: verifier_peer.signal_ok, sleep_duration=0.01)
