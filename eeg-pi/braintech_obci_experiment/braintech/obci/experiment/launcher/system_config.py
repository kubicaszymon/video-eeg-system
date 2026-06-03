# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import codecs
import logging

from braintech.obci.core.broker import ObciException

from ..common.config_helpers import CONFIG_SOURCES, LAUNCH_DEPENDENCIES, LOCAL_PARAMS, EXT_PARAMS
from . import launcher_tools
from ..peer.peer_config_serializer import PeerConfigSerializerCmd
from ..peer import peer_config_parser
from ..peer.peer_config import PeerConfig

from ..common.graph import DirectedGraph, Vertex


class OBCIExperimentConfig:
    def __init__(self, launch_file_path=None, uuid=None,
                 origin_machine=None, logger=None):
        self.uuid = uuid
        self.launch_file_path = launch_file_path

        self.origin_machine = origin_machine if origin_machine else ''
        self.scenario_dir = ''
        self.peers = {}
        self.logger = logger or logging.getLogger("ObciExperimentConfig")

    @property
    def launch_file_path(self):
        return self._launch_file_path

    @launch_file_path.setter
    def launch_file_path(self, path):
        self._launch_file_path = path
        if path:
            self._launch_file_path = launcher_tools.obci_root_relative(path)

    def update_local_param(self, peer_id, p_name, p_value):
        self._validate_peer_existence(peer_id)
        return self.peers[peer_id].config.update_local_param(p_name, p_value)

    def update_external_param(self, peer_id, p_name, src, src_param=None):
        self._validate_peer_existence(peer_id)
        if src_param is None:
            try:
                src, src_param = src.split('.')
            except ValueError:
                raise OBCISystemConfigError("Invalid peer '{}' config entry: {}"
                                            .format(peer_id, p_name))
        return self.peers[peer_id].config.update_external_param_def(p_name, src + '.' + src_param)

    def update_peer_config(self, peer_id, config_dict):
        self._validate_peer_existence(peer_id)
        conf = self.peers[peer_id].config
        dictparser = peer_config_parser.parser('python')
        return dictparser.parse(config_dict, conf, update=True)

    def file_update_peer_config(self, peer_id, file_path):
        self._validate_peer_existence(peer_id)
        parser = peer_config_parser.parser('ini')
        with open(file_path) as f:
            return parser.parse(f, self.peers[peer_id].config, update=True)

    def peer_machine(self, peer_id):
        return self.peers[peer_id].machine

    def extend_with_peer(self, peer_id, peer_path, peer_cfg,
                         config_sources=None, launch_deps=None,
                         param_overwrites=None, machine=None):
        if not config_sources:
            config_sources = peer_cfg.config_sources
        if not launch_deps:
            launch_deps = peer_cfg.launch_deps
        param_overwrites = param_overwrites or {}
        machine = machine or ""
        self.add_peer(peer_id)
        self.set_peer_config(peer_id, peer_cfg)
        self.set_peer_path(peer_id, peer_path)
        self.set_peer_machine(peer_id, machine)
        for src_name, src_id in config_sources.items():
            self.set_config_source(peer_id, src_name, src_id)
        for dep_name, dep_id in launch_deps.items():
            self.set_launch_dependency(peer_id, dep_name, dep_id)
        for par, val in param_overwrites.items():
            self.update_local_param(peer_id, par, val)
        override = peer_id in self.peers
        return override

    def add_peer(self, peer_id):
        self.peers[peer_id] = PeerConfigDescription(peer_id, self.uuid)

    def set_peer_config(self, peer_id, peer_config):
        self.peers[peer_id].config = peer_config

    def set_peer_path(self, peer_id, path):
        self.peers[peer_id].path = path

    def remove_peer(self, peer_id):
        del self.peers[peer_id]

    def set_config_source(self, peer_id, src_name, src_peer_id):
        self._validate_peer_existence(src_peer_id)
        self._validate_peer_existence(peer_id)
        if self.peers[peer_id] is None:
            raise OBCISystemConfigError("Configuration for peer ID '{}' does not exist".format(peer_id))

        self.peers[peer_id].config.set_config_source(src_name, src_peer_id)

    def set_launch_dependency(self, peer_id, dep_name, dep_peer_id):
        self._validate_peer_existence(dep_peer_id)
        self._validate_peer_existence(peer_id)
        if self.peers[peer_id] is None:
            raise OBCISystemConfigError("Configuration for peer ID '{}' does not exist".format(peer_id))

        self.peers[peer_id].config.set_launch_dependency(dep_name, dep_peer_id)

    def set_peer_machine(self, peer_id, machine_name):
        self._validate_peer_existence(peer_id)
        self.peers[peer_id].machine = machine_name

    def all_param_values(self, peer_id):
        self._validate_peer_existence(peer_id)
        config = self.peers[peer_id].config
        not_fresh = config.param_values
        vals = {}
        for key in not_fresh:
            vals[key] = self._param_value(peer_id, key, config)
        return vals

    def _validate_peer_existence(self, peer_id):
        if peer_id not in self.peers:
            raise OBCISystemConfigError("Peer ID '{}' not in peer list: {}"
                                        .format(peer_id, list(self.peers.keys())))

    def local_params(self, peer_id):
        return self.peers[peer_id].config.local_params

    def param_value(self, peer_id, param_name):
        if peer_id not in self.peers:
            raise OBCISystemConfigError("Peer ID '{}' not in peer list. Tried to get value of parameter: {}"
                                        .format(peer_id, param_name))

        config = self.peers[peer_id].config
        return self._param_value(peer_id, param_name, config)

    def _param_value(self, peer_id, param_name, config):
        if param_name in config.local_params:
            return config.local_params[param_name]
        elif param_name in config.ext_param_defs:
            peer, param = config.ext_param_defs[param_name]
            source = config.config_sources[peer]
            return self.param_value(source, param)
        else:
            raise OBCISystemConfigError("Parameter '{}' does not exist in '{}'."
                                        .format(param_name, peer_id))

    def config_ready(self):
        details = {}

        if not self.peers:
            return False, details
        for peer_state in self.peers.values():
            if not peer_state.ready(details):
                return False, details
        valid, details = self._is_launch_dependencies_graph_acyclic()
        if not valid:
            return valid, details
        valid, details = self._is_config_sources_graph_acyclic()
        if not valid:
            return valid, details

        return True, {}

    def _is_launch_dependencies_graph_acyclic(self):
        graph = create_peers_dependency_graph(self.peers, 'list_launch_deps')
        valid, order = graph.topo_sort()
        details = '' if valid else {'desc': "Launch dependencies graph contains a cycle!!!"}
        return valid, details

    def _is_config_sources_graph_acyclic(self):
        graph = create_peers_dependency_graph(self.peers, 'list_config_sources')
        valid, order = graph.topo_sort()
        details = '' if valid else {'desc': "Config sources graph contains a cycle!!!"}
        return valid, details

    def status(self, status_obj):
        ready, details = self.config_ready()
        st = launcher_tools.READY_TO_LAUNCH if ready else launcher_tools.NOT_READY

        status_obj.set_status(st, details=details)
        # TODO details, e.g. info about cycles

        for peer_id in self.peers:
            peer_status = launcher_tools.PeerStatus(peer_id)
            status_obj.peers_status[peer_id] = peer_status
            self.peers[peer_id].status(peer_status)

    def peer_machines(self):
        return {self.origin_machine} | {peer.machine for peer in self.peers.values()
                                        if peer.machine}

    def launch_data(self, machine):
        launch_data = {}

        for peer in self.peers.values():
            peer_machine = peer.machine or self.origin_machine
            if peer_machine == machine:
                launch_data[peer.peer_id] = peer.launch_data()
        return launch_data

    def peer_order(self):
        order = list(self._get_topologically_sorted_peers('list_launch_deps'))
        if order:
            part1 = order[0]
            if 'config_server' in part1:
                part1.remove('config_server')
            order = [['config_server']] + order
        return order

    def _get_topologically_sorted_peers(self, dependant_peers_getter):
        gr = create_peers_dependency_graph(self.peers, dependant_peers_getter)
        _, order = gr.topo_sort()
        for part in order:
            yield [v._model.peer_id for v in part]

    def peers_info(self):
        return {peer: self.peers[peer].info()
                for peer in self.peers}

    def info(self):
        return {
            "uuid": self.uuid,
            "origin_machine": self.origin_machine,
            "launch_file_path": self.launch_file_path,
            "peers": self.peers_info(),
        }


def create_peers_dependency_graph(peer_descriptions, dependants_getter_name):
    graph = DirectedGraph()
    vertices = {}
    for peer_description in peer_descriptions.values():
        get_dependant_peers = getattr(peer_description, dependants_getter_name)
        neighbours = get_dependant_peers()
        if peer_description not in vertices:
            ver_p = Vertex(graph, peer_description)
            vertices[peer_description] = ver_p
            graph.add_vertex(ver_p)
        for neighbour in neighbours:
            neighbour_description = peer_descriptions[neighbour]
            if neighbour_description not in vertices:
                ver_ng = Vertex(graph, neighbour_description)
                vertices[neighbour_description] = ver_ng
                graph.add_vertex(ver_ng)
            graph.add_edge(vertices[peer_description],
                           vertices[neighbour_description])
    return graph


class PeerConfigDescription:

    def __init__(self, peer_id, experiment_id, config=None, path=None, machine=None,
                 logger=None):
        self.peer_id = peer_id

        self.experiment_id = experiment_id

        self.config = PeerConfig(peer_id)
        self.path = path
        self.machine = machine
        self.public_params = []
        self.logger = logger or logging.getLogger("ObciExperimentConfig.peer_id")
        self.del_after_stop = False

    def __str__(self):
        return self.peer_id

    def ready(self, details=None):
        loc_det = {}
        ready = self.config is not None and \
            self.path is not None and\
            self.machine is not None and\
            self.peer_id is not None

        if not ready:
            return ready
        ready = self.config.config_sources_ready(loc_det) and ready
        ready = self.config.launch_deps_ready(loc_det) and ready
        if details is not None:
            details[self.peer_id] = loc_det
        return ready

    def list_config_sources(self):
        return [val for val in self.config.config_sources.values() if
                val in self.config.used_config_sources()]

    def list_launch_deps(self):
        return list(self.config.launch_deps.values())

    def status(self, peer_status_obj):
        det = {}
        ready = self.ready(det)
        st = launcher_tools.READY_TO_LAUNCH if ready else launcher_tools.NOT_READY

        peer_status_obj.set_status(st, details=det)

    def peer_type(self):
        return 'obci_peer'

    def launch_data(self):
        ser = PeerConfigSerializerCmd()
        args = [self.peer_id]
        peer_parser = peer_config_parser.parser("ini")
        base_config = PeerConfig(self.peer_id)
        conf_path = launcher_tools.default_config_path(self.path)
        if conf_path:
            with codecs.open(conf_path, "r", "utf8") as f:
                self.logger.info("parsing default config for peer %s, %s ",
                                 self.peer_id, conf_path)
                peer_parser.parse(f, base_config)

        ser.serialize_diff(base_config, self.config, args)

        return dict(peer_id=self.peer_id, experiment_id=self.experiment_id,
                    path=self.path, machine=self.machine,
                    args=args, peer_type=self.peer_type())

    def info(self, detailed=False):
        info = dict(peer_id=self.peer_id,
                    path=self.path, machine=self.machine, peer_type=self.peer_type()
                    )

        if not self.config:
            return info

        info[CONFIG_SOURCES] = self.config.config_sources
        info[LAUNCH_DEPENDENCIES] = self.config.launch_deps

        if detailed:
            info[LOCAL_PARAMS] = self.config.local_params
            info[EXT_PARAMS] = self.config.ext_param_defs
        return info


class OBCISystemConfigError(ObciException):
    pass


class OBCISystemConfigWarning(Warning):
    pass
