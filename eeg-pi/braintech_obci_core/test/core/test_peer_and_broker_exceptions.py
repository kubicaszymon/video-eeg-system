# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import threading
import pytest
import uuid

from braintech.obci.core.broker import messages
from braintech.obci.core.broker.peer import (Peer,
                                             AlreadyRegisteredException,
                                             NotRegisteredException,
                                             NotInitializedException,
                                             HandlerNotRegisteredException)
from braintech.obci.core.broker.broker import Broker
from braintech.obci.core.broker.peer import PeerInitUrls
from braintech.obci.core.broker.asyncio_task_manager import SHUTDOWN_TIMEOUT
from braintech.obci.core.utils import wait_until_peers_ready, yield_then_shutdown


class _ABC(messages.BaseMessage):
    pass


class _TEST(messages.BaseMessage):
    pass


class _TestException(Exception):
    pass


broker_rep = 'tcp://127.0.0.1:20001'
broker_xpub = 'tcp://127.0.0.1:20002'
broker_xsub = 'tcp://127.0.0.1:20003'
peer_pub = 'tcp://127.0.0.1:*'
peer_rep = 'tcp://127.0.0.1:*'


@pytest.fixture
def lone_peer():
    urls = PeerInitUrls(pub_urls=[peer_pub],
                        rep_urls=[peer_rep],
                        broker_rep_url=broker_rep)
    peer = Peer(urls, uuid.uuid4())
    yield from yield_then_shutdown(peer)


@pytest.fixture(params=[True, False],
                ids=['own_loop', 'shared_loop']
                )
def peers_and_broker(request):
    broker = Broker(None, [broker_rep], [broker_xpub], [broker_xsub])
    urls = PeerInitUrls(pub_urls=[peer_pub],
                        rep_urls=[peer_rep],
                        broker_rep_url=broker_rep)
    peer1 = Peer(urls, '1', autoshutdown=False)
    use_own_msg_loop = request.param
    if use_own_msg_loop:
        peer2 = Peer(urls, '2', autoshutdown=False)
    else:
        peer2 = Peer(urls, '2', asyncio_loop=peer1._loop, zmq_context=peer1._ctx, autoshutdown=False)
    wait_until_peers_ready([broker, peer1, peer2])

    yield broker, peer1, peer2, use_own_msg_loop
    peer2.shutdown()
    peer1.shutdown()
    broker.shutdown()


def test_unconnected_peer_exceptions(lone_peer):

    peer = lone_peer
    with pytest.raises(NotInitializedException):
        peer.subscribe(_ABC)

    with pytest.raises(NotInitializedException):
        peer.unsubscribe(_ABC)

    peer.register_message_handler(_ABC, lambda _: _ABC('0'))
    with pytest.raises(AlreadyRegisteredException):
        peer.register_message_handler(_ABC, lambda _: _ABC('0'))

    peer.unregister_message_handler(_ABC)
    with pytest.raises(NotRegisteredException):
        peer.unregister_message_handler(_ABC)


def test_connected_peer_exceptions(peers_and_broker):
    broker, peer1, peer2, use_own_loop = peers_and_broker

    with pytest.raises(HandlerNotRegisteredException):
        peer1.subscribe(_ABC)


def test_msg_handler_exceptions(peers_and_broker):
    broker, peer1, peer2, use_own_msg_loop = peers_and_broker

    def raise_exception(msg):
        raise _TestException("Random Exception")
    subscribed = threading.Event()

    def subscribed_handler(_):
        peer2.unregister_message_handler(_TEST)
        peer2.register_message_handler(_TEST, raise_exception)
        subscribed.set()
    peer2.subscribe_for_all_msg_subtype(_TEST, subscribed_handler)
    while not subscribed.wait(0.1):
        peer1.send_message(_TEST(peer1.id))
    peer1.send_message(_TEST(peer1.id))
    if use_own_msg_loop:
        with pytest.raises(_TestException):
            peer2._wait_until_finished(SHUTDOWN_TIMEOUT)
    else:
        event = threading.Event()

        async def func():
            with pytest.raises(_TestException):
                await peer2.wait_until_finished_async(SHUTDOWN_TIMEOUT)
            event.set()

        peer2._loop.create_task(func())
        assert event.wait(SHUTDOWN_TIMEOUT)
    peer2._exception = None  # reset exception


def test_peer_shutdown_with_error(peers_and_broker):
    peer = peers_and_broker[2]  # peer 2 must be used in this test, because peer 1 owns shared loop

    with pytest.raises(_TestException):
        peer.shutdown(5, exc=_TestException("Error"))
    peer._exception = None  # reset exception
