# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import pytest

from braintech.obci.experiment.peer import peer_cmd


@pytest.mark.incremental
class TestPeerOverwritesPack:
    def test_no_data_to_pack(self):
        output = peer_cmd.peer_overwrites_pack([])
        assert type(output) == list
        assert not output

    def test_single_local_param_to_pack(self):
        input = ['--peer', 'amplifier', '-p', 'amplifier_id', 'dummy']
        output = peer_cmd.peer_overwrites_pack(input)
        assert type(output) == list
        assert len(output) == 1
        assert output[0] == [
            {'config_sources': {},
             'external_params': {},
             'launch_dependencies': {},
             'local_params': {'amplifier_id': 'dummy'}},
            {'config_file': [],
             'peer_id': 'amplifier'},
        ]

    def test_multiple_local_params_to_pack(self):
        input = [
            '--peer', 'amplifier', '-p', 'amplifier_id', 'dummy',
            '--peer', 'amplifier', '-p', 'monster', 'yes_please',
            '--peer', 'amplifier', '-p', 'order_pizza', 'not_today',
        ]
        output = peer_cmd.peer_overwrites_pack(input)
        assert type(output) == list
        assert len(output) == 3
        assert output[0] == [
            {'config_sources': {},
             'external_params': {},
             'launch_dependencies': {},
             'local_params': {'amplifier_id': 'dummy'}},
            {'config_file': [],
             'peer_id': 'amplifier'},
        ]
        assert output[1] == [
            {'config_sources': {},
             'external_params': {},
             'launch_dependencies': {},
             'local_params': {'monster': 'yes_please'}},
            {'config_file': [],
             'peer_id': 'amplifier'},
        ]
        assert output[2] == [
            {'config_sources': {},
             'external_params': {},
             'launch_dependencies': {},
             'local_params': {'order_pizza': 'not_today'}},
            {'config_file': [],
             'peer_id': 'amplifier'},
        ]

    def test_multiple_peers_to_pack(self):
        input = [
            '--peer', 'amplifier', '-p', 'amplifier_id', 'dummy',
            '--peer', 'exemplifier', '-p', 'wading_thru_the_code', 'unfortunately',
            '--peer', 'perkator_complex', '-p', 'dummy', 'nope',
        ]
        output = peer_cmd.peer_overwrites_pack(input)
        assert type(output) == list
        assert len(output) == 3
        assert output[0] == [
            {'config_sources': {},
             'external_params': {},
             'launch_dependencies': {},
             'local_params': {'amplifier_id': 'dummy'}},
            {'config_file': [],
             'peer_id': 'amplifier'},
        ]
        assert output[1] == [
            {'config_sources': {},
             'external_params': {},
             'launch_dependencies': {},
             'local_params': {'wading_thru_the_code': 'unfortunately'}},
            {'config_file': [],
             'peer_id': 'exemplifier'},
        ]
        assert output[2] == [
            {'config_sources': {},
             'external_params': {},
             'launch_dependencies': {},
             'local_params': {'dummy': 'nope'}},
            {'config_file': [],
             'peer_id': 'perkator_complex'},
        ]

    def test_all_param_types(self):
        input = [
            '--peer', 'amplifier', '-p', 'samplifier_id', '5',
            '--peer', 'amplifier', '-c', 'some_config_source', 'mein_gott',
            '--peer', 'amplifier', '-e', 'smelling_napalm', 'only_in_the_morning',
            '--peer', 'amplifier', '-d', 'do_d', 'do_dalszej_diagnozy',
        ]
        output = peer_cmd.peer_overwrites_pack(input)
        assert type(output) == list
        assert len(output) == 4
        assert output[0] == [
            {'config_sources': {},
             'external_params': {},
             'launch_dependencies': {},
             'local_params': {'samplifier_id': '5'}},
            {'config_file': [],
             'peer_id': 'amplifier'},
        ]
        assert output[1] == [
            {'config_sources': {'some_config_source': 'mein_gott'},
             'external_params': {},
             'launch_dependencies': {},
             'local_params': {}},
            {'config_file': [],
             'peer_id': 'amplifier'},
        ]
        assert output[2] == [
            {'config_sources': {},
             'external_params': {'smelling_napalm': 'only_in_the_morning'},
             'launch_dependencies': {},
             'local_params': {}},
            {'config_file': [],
             'peer_id': 'amplifier'},
        ]
        assert output[3] == [
            {'config_sources': {},
             'external_params': {},
             'launch_dependencies': {'do_d': 'do_dalszej_diagnozy'},
             'local_params': {}},
            {'config_file': [],
             'peer_id': 'amplifier'},
        ]


@pytest.mark.incremental
class TestMergeOverwritesPerPeer:
    def test_empty(self):
        merged = peer_cmd.merge_overwrites_per_peer([])
        assert merged == []

    def test_single_peer_single_type(self):
        input = [
            '--peer', 'amplifier', '-p', 'samplifier_id', '5',
        ]
        packed = peer_cmd.peer_overwrites_pack(input)
        merged = peer_cmd.merge_overwrites_per_peer(packed)
        assert packed == merged

    def test_single_peer_all_types(self):
        input = [
            '--peer', 'amplifier', '-p', 'samplifier_id', '5',
            '--peer', 'amplifier', '-c', 'some_config_source', 'mein_gott',
            '--peer', 'amplifier', '-e', 'smelling_napalm', 'only_in_the_morning',
            '--peer', 'amplifier', '-d', 'do_d', 'do_dalszej_diagnozy',
        ]
        packed = peer_cmd.peer_overwrites_pack(input)
        merged = peer_cmd.merge_overwrites_per_peer(packed)
        assert type(merged) == list
        assert len(merged) == 1
        assert merged[0] == [
            {'config_sources': {'some_config_source': 'mein_gott'},
             'external_params': {'smelling_napalm': 'only_in_the_morning'},
             'launch_dependencies': {'do_d': 'do_dalszej_diagnozy'},
             'local_params': {'samplifier_id': '5'}},
            {'config_file': [],
             'peer_id': 'amplifier'},
        ]

    def test_multiple_peers(self):
        input = [
            '--peer', 'amplifier', '-p', 'samplifier_id', '5',
            '--peer', 'lol', '-c', 'some_config_source', 'mein_gott',
            '--peer', 'lol', '-e', 'smelling_napalm', 'only_in_the_morning',
        ]
        packed = peer_cmd.peer_overwrites_pack(input)
        merged = peer_cmd.merge_overwrites_per_peer(packed)
        assert type(merged) == list
        assert len(merged) == 2
        sorted_merged = sorted(merged, key=lambda x: x[1]['peer_id'])
        assert sorted_merged == [
            [
                {'config_sources': {},
                 'external_params': {},
                 'launch_dependencies': {},
                 'local_params': {'samplifier_id': '5'}},
                {'config_file': [],
                 'peer_id': 'amplifier'},
            ],
            [
                {'config_sources': {'some_config_source': 'mein_gott'},
                 'external_params': {'smelling_napalm': 'only_in_the_morning'},
                 'launch_dependencies': {},
                 'local_params': {}},
                {'config_file': [],
                 'peer_id': 'lol'},
            ],
        ]
