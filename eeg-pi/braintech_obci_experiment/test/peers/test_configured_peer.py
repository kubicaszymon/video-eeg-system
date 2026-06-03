# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Tests for covering logic of ConfiguredPeer class."""

import unittest.mock as mock

import pytest

from braintech.obci.core.broker import ObciException
from braintech.obci.core.broker import messages
from braintech.obci.core.utils import (
    get_peer_config_file_path,
    TimeoutException,
    wait_for_condition,
    wait_until_peers_ready,
    yield_then_shutdown,
)

from test_peers.master import Master
from test_peers.slave import Slave


# -------------------------------- Fixtures: ----------------------------------

@pytest.fixture()
def master(broker, config_server):
    wait_until_peers_ready([config_server, broker])
    master_config = {
        'local_params': {
            'value': 42,  # Magic value for testing
            'param_property': 'Hello world!',
        },
    }
    yield from yield_then_shutdown(
        Master(
            urls=broker.broker_ip,
            peer_id='master_peer_id',
            peer_name='master',
            base_config_file=get_peer_config_file_path(Master),
            **master_config
        )
    )


@pytest.fixture()
def slave(broker, config_server, master):
    slave_config = {
        'config_sources': {
            'master': 'master_peer_id',
        },
        'external_params': {
            'value': 'master.value',
            'param_property': 'master.param_property',
        },
        'launch_dependencies': {
            'master': 'master_peer_id',
        },
    }
    yield from yield_then_shutdown(
        Slave(
            urls=broker.broker_ip,
            peer_id='slave_peer_id',
            peer_name='slave',
            base_config_file=get_peer_config_file_path(Slave),
            **slave_config
        )
    )


# ---------------------------------- Tests: -----------------------------------
@pytest.mark.incremental
class TestSetParamPropagation:
    def test_peers_parameters_should_be_propagated(self, broker, config_server, master, slave):
        """Test if peers parameters are propagated to another peers.

        Change in peers parameters (especially external ones) should be
        propagated to other peers initialized from this one.
        """
        wait_until_peers_ready([config_server, broker, master, slave])

        master_value = master.get_param('value')
        slave_value = slave.get_param('value')
        assert master_value == slave_value

    def test_peer_config_can_be_changed_from_another_peer(self, broker, config_server, master, slave):
        """Test if it is possible to change peer configuration from other peer.

        Peer which configuration is going to change should be initialized from
        other peer.
        """
        wait_until_peers_ready([config_server, broker, master, slave])

        master_value = master.get_param('value')
        assert master_value == slave.get_param('value')

        master_value = str(int(master_value) + 1)
        master.set_param('value', master_value)

        try:
            wait_for_condition(lambda: slave.get_param('value') == master_value)
        except TimeoutException:
            pytest.fail(
                "Value did't propagate. slave_val = {}; master_val = {}".format(
                    slave.get_param('value'), master.get_param('value')
                )
            )


@pytest.mark.incremental
class TestParamPropertyPropagation:
    def test_peers_param_properties_should_be_propagated(self, broker, config_server, master, slave):
        """Test if peers 'param properties' are propagated to another peers.

        Change in peers 'param properties' (especially external ones) should be
        propagated to other peers initialized from this one.
        """
        wait_until_peers_ready([config_server, broker, master, slave])

        master_value = master.param_property
        slave_value = slave.param_property

        assert master_value == slave_value

    def test_peer_param_property_can_be_changed_from_another_peer(self, broker, config_server, master, slave):
        """Test if it is possible to change peer 'param property' from other peer.

        Peer which 'param property' is going to change should be initialized from
        other peer.
        """
        wait_until_peers_ready([config_server, broker, master, slave])

        assert master.param_property == slave.param_property

        master_value = 'Goodbye world :"( ...'
        master.param_property = master_value

        try:
            wait_for_condition(
                lambda: slave.param_property == master_value,
            )
        except TimeoutException:
            pytest.fail(
                "Value did't propagate. slave_val = {}; master_val = {}".format(
                    slave.param_property, master.param_property
                )
            )


def test_peer_param_property_can_not_be_changed_when_it_is_running(
        broker, config_server, master, slave
):
    """Test if it is impossible to change peer config when it's running.

    Peer's external value should not be changed when this peer is running.
    (Exception should be raised in that case)
    """
    wait_until_peers_ready([config_server, broker, master, slave])

    with mock.patch.object(slave._state, '_is_running', return_value=True):

        with pytest.raises(ObciException):
            slave._update_changed_params(master.id, {'value': 'new_value'})


def test_update_changed_params(broker, config_server, master, slave):
    """Unit test for ConfiguredPeer._update_changed_params()"""
    wait_until_peers_ready([config_server, broker, master, slave])
    slave._update_changed_params('master_peer_id', {'value': 'new_value'})
    assert slave.get_param('value') == 'new_value'


def _check_by_param_property(obj, name, value):
    value_peer = getattr(obj, name)
    return value == value_peer


def _check_by_get_param(obj, name, value):
    return value == obj.get_param(name)


def _get_peer_url(comms_peer, peer_id):
    message = messages.PeerUrlQuery(target=peer_id, target_url='',
                                    sender_id=comms_peer.peer_id)
    resp_future = comms_peer.create_task(comms_peer.ask_broker(message))
    resp = resp_future.result()
    if resp.target_url and resp.target == peer_id:
        return resp.target_url
    else:
        raise Exception("Couldn't get slave peer url! Answer: {}".format(resp))


@pytest.mark.parametrize("check_func",
                         [_check_by_param_property, _check_by_get_param],
                         ids=['check by param_property', 'check by get_param'])
def test_set_param_query(broker, config_server, master, slave, check_func):
    """Unit test for ConfiguredPeer should change it's local param on query."""
    wait_until_peers_ready([config_server, broker, master, slave])
    assert check_func(slave, 'local_set_query_param', 'test1')
    new_value = 'atest2'
    url = _get_peer_url(master, slave.id)
    message = messages.PeerSetParamQuery(key='local_set_query_param', value=new_value)
    resp = master.create_task(master.ask_peer(url, message)).result()
    assert isinstance(resp, messages.OkMsg), "PeerSetParamQuery should return OkMsg"
    assert check_func(slave, 'local_set_query_param', new_value), "Param should be updated"
    message = messages.PeerSetParamQuery(key='non_existent', value=new_value)
    resp = master.create_task(master.ask_peer(url, message)).result()
    assert resp.details == 'key_error', "NonExistent properties should return key error"
