# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Tests for covering logic of BasePeer class."""

import unittest.mock as mock

import pytest

from braintech.obci.core.broker.base_peer import PeerState
from braintech.obci.core.broker.peer import Peer
from braintech.obci.core.utils import get_peer_config_file_path, wait_until_peers_ready
from braintech.obci.core.utils import wait_for_condition, yield_then_shutdown

from test_peers.master import Master
from braintech.obci.core.broker.asyncio_task_manager import ShuttingDownException
from braintech.obci.core.broker import messages


DEFAULT_PEER_KWARGS = {
    'autoshutdown': False,
    'autostart': False,
}


def check_states(peer, states):
    """Check if peer is in one of the given states.

    returns: tuple(result, error_msg)
    """
    condition = any(peer._state == state for state in states) if states else True
    message = 'Peer should be in state: ' + ' or '.join(map(str, states)) if states else None
    return condition, message


def check_peer_states(original, before_states=(), after_states=()):
    """Check if peer was in the given state before running 'original' method.

    original: peer's method to be decorated
    before_states: state name or iterable of peer state names, which are valid for peer to be in before the method call
    next_states: state name or iterable of peer state names, which are valid for peer to be in after the method call"""

    if not (before_states or after_states):
        raise Exception('You must supply at least one of: before_states, after_states')

    peer = original.__self__

    async def wrapper(*args, **kwargs):
        condition, message = check_states(peer, before_states)
        assert condition, message + ' before run of: {}'.format(original.__name__)

        await original(*args, **kwargs)

        condition, message = check_states(peer, after_states)
        assert condition, message + ' after run of: {}'.format(original.__name__)

    return wrapper


@pytest.fixture(
    params=[
        (Master, DEFAULT_PEER_KWARGS),
    ],
    ids=lambda val: val[0].__name__
)
def peer(request, broker, config_server):
    wait_until_peers_ready([config_server, broker])
    cls, kwargs = request.param
    instance = cls(
        urls=broker.broker_ip,
        peer_id='_'.join([cls.__name__, 'peer_id']),
        peer_name=cls.__name__,
        base_config_file=get_peer_config_file_path(Master),
        **kwargs,
    )
    yield from yield_then_shutdown(instance)


def test_fast_peer_shutdown(broker):
    """Tests if interrupting of peer initialization by shutdown is working properly"""
    peer = Peer(broker.broker_ip, peer_id="FastShutdownPeer")
    # during shutdown can always be called, even on not fully initialized peer
    # async peer initialization task should correctly stop
    peer.shutdown()


def test_peer_shutdown_with_timeout(broker):
    peer = Peer(broker.broker_ip, peer_id="FastShutdownPeer")
    try:
        with pytest.raises(TimeoutError):
            peer.shutdown(0)
    finally:
        peer.shutdown()


async def dummy_task(*args):
    pass
dummy_handler = dummy_task


def test_peer_state_flow(peer):
    """Peer state flow should be kept.
    see: :ref:`Peer States` for reference.
    """
    with mock.patch.multiple(
        peer,
        # Called from _initialize:
        _establish_connections=check_peer_states(
            peer._establish_connections,
            before_states=(PeerState.initializing,),
        ),
        _connections_established=check_peer_states(
            peer._connections_established,  # initialization method, that can be used to
                                            # get information from other peers
            before_states=(PeerState.connected,),  # it is called from connected state, and when it finishes, peer
                                                   # changes its state to ready
        ),
    ):
        try:
            # just after peer start it is not connected
            assert not peer.is_connected
        except AssertionError:
            # peer might already connect, if the computer is fast and another thread will manage to connect it before
            # test starts
            pass
        else:
            assert not peer.is_ready, "When peer is not connected, it should not be ready"
        peer.create_task(dummy_task())  # we can start asyncio tasks for peer
        wait_for_condition(lambda: peer.is_connected)
        assert peer.is_connected
        peer.send_message(messages.OkMsg())  # We can send messages now
        peer.subscribe_for_all_msg_subtype(messages.OkMsg, dummy_handler)  # We can subscribe for messages
        wait_for_condition(lambda: peer.is_ready)
        assert peer.is_ready and not peer.is_running, "Peer should not be running without start"
        peer.start()
        assert peer.is_ready and peer.is_running
        peer.start()  # multiple starts are possible

        peer.stop()
        assert not peer.is_running and peer.is_ready
        peer.stop()  # multiple stops are also possible

        peer.start()
        assert peer.is_running

        peer.create_task(peer.async_shutdown())  # start shutdown process
        wait_for_condition(lambda: peer.is_shutting_down)
        assert peer.is_shutting_down

        # during shutdown most of peers methods are disabled
        with pytest.raises(ShuttingDownException):
            peer.start()
        with pytest.raises(ShuttingDownException):
            peer.send_message(messages.OkMsg())
        with pytest.raises(ShuttingDownException):
            peer.create_task(dummy_task())

        peer.shutdown()
        assert peer.is_finished and peer.is_shutting_down
