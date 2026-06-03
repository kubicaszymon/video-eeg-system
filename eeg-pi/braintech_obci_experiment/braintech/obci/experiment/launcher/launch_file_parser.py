# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import codecs
import configparser
import json
import logging
import os
import warnings

from ..peer.peer_config import PeerConfig
from ..peer.peer_config_parser import parser
from . import peer_loader
from .launcher_tools import expand_path, default_config_path
from .system_config import OBCISystemConfigError
from ..peer.config_defaults import CONFIG_DEFAULTS

PEERS = "peers"
CONFIG_SRCS = "config_sources"
LAUNCH_DEPS = "launch_dependencies"
EXT_PRMS = "external_params"
LOCAL_PRMS = "local_params"

SYS_SECTIONS = [PEERS]


class ScenarioParser:

    def parse(self, p_file, p_config_obj, apply_globals=False):
        self._prepare(p_file, p_config_obj)
        self._do_parse(apply_globals)
        return True

    def _do_parse(self, apply_globals=False):
        self._apply_globals = apply_globals
        self._check_sections()
        self._load_general_settings()
        peer_sections = self._peer_sections()  # select peers i.e. peers.config_server', 'peers.amplifier'

        self._load_peer_ids(peer_sections)  # create an empty sections headers
        self._load_launch_data(peer_sections)  # load data from config file

        self._set_config_params()  # load and set parameters from scenario file

    def _find_peer_path(self, peer_path):
        peer_loader.validate_path(peer_path)
        return peer_path

    def _load_peer(self, peer_id, peer_items):
        # FIXME rewrite cleaner

        machine_set = False
        config_section_contents = ''

        for (param, value) in peer_items:
            if param == "path":
                peer_path = self._find_peer_path(value)
                self.config.set_peer_path(peer_id, peer_path)

            elif param == "config":
                if self.config.scenario_dir:
                    warnings.warn("Choosing {0} for {1} config\
 instead of a file in scenario dir {2}!!!".format(value, peer_id, self.config.scenario_dir))
                config_section_contents = value

            elif param == "machine":
                machine_set = True
                self._set_peer_machine(peer_id, value)
            else:
                pass
                # raise OBCISystemConfigError("Unrecognized launch file option {0}".format(param))
        if not machine_set:
            self._set_peer_machine(peer_id, '')
        if not config_section_contents:
            if self.config.scenario_dir:
                config_section_contents = os.path.join(self.config.scenario_dir, peer_id + '.ini')
            else:
                # well, then we'll try to load default .ini for this peer or,
                # if default config does not exist, leave config empty
                pass
        self._parse_peer_config_section(peer_id, config_section_contents, peer_path)


class LaunchFileParser(ScenarioParser):

    def __init__(self, obci_base_dir, scenario_base_dir, logger=None):
        self.base_dir = obci_base_dir
        self.scenario_dir = scenario_base_dir
        self.parser = None
        self.config = None
        self.logger = logger or logging.getLogger("launcher.LaunchFileParser")

    def _prepare(self, p_file, p_config_obj):
        self.parser = configparser.ConfigParser({
            'dir': os.path.dirname(os.path.abspath(getattr(p_file, 'name', '.')))
        })
        self.parser.readfp(p_file)
        self._scenario_file = p_file.name
        self.config = p_config_obj

    def _check_sections(self):
        for section in self.parser.sections():
            main_s = self.__main_section(section)
            if main_s not in SYS_SECTIONS:
                raise OBCISystemConfigError("Unrecognized launch file section: {0}".format(main_s))

    def _load_general_settings(self):
        if self.parser.has_option(PEERS, 'mx'):
            self.config.mx = self.parser.get(PEERS, 'mx')

        if self.parser.has_option(PEERS, 'scenario_dir'):
            self.config.scenario_dir = self.parser.get(PEERS, 'scenario_dir')
            self.config.scenario_dir = expand_path(self.config.scenario_dir, base_dir=self.scenario_dir)

    def _load_peer_ids(self, peer_sections):
        for section in peer_sections:
            peer_id = self._peer_id(section)
            self.config.add_peer(peer_id)

    def _get_items(self, section_name):
        return [x for x in self.parser.items(section_name) if x[0] not in self.parser.defaults()]

    def _load_launch_data(self, peer_sections):
        for sec in peer_sections:
            items = self._get_items(sec)
            peer_id = self._peer_id(sec)
            self._load_peer(peer_id, items)

    def _parse_peer_config(self, peer_id, config_path, peer_program_path):
        peer_cfg, peer_parser = parse_peer_default_config(
            peer_id, peer_program_path, self.logger,
            self._apply_globals)
        if config_path:
            with codecs.open(config_path, "r", "utf8") as f:
                self.logger.info("parsing _custom_ config for peer %s, %s ", peer_id, config_path)
                peer_parser.parse(f, peer_cfg)

        self.config.set_peer_config(peer_id, peer_cfg)

    def _parse_peer_config_section(self, peer_id, peer_config_section, peer_path):
        scenario_dirname = os.path.dirname(self._scenario_file)
        peer_config_file_relative = os.path.join(scenario_dirname, peer_config_section)
        if peer_config_section and os.path.exists(peer_config_file_relative):
            peer_config_file = peer_config_file_relative
        else:
            peer_config_file = expand_path(peer_config_section)

        self._parse_peer_config(peer_id, peer_config_file, peer_path)

    def _set_config_params(self):

        map_sections = {CONFIG_SRCS: self.config.set_config_source,
                        LAUNCH_DEPS: self.config.set_launch_dependency,
                        EXT_PRMS: self.config.update_external_param,
                        LOCAL_PRMS: self.config.update_local_param}

        for key_sec, fun_sec in map_sections.items():
            for sec in self.__sections(key_sec):
                for sec_name, sec_id in self._get_items(sec):
                    fun_sec(self._peer_id(sec), sec_name, sec_id)

    def _set_peer_machine(self, peer_id, machine_name):
        self.config.set_peer_machine(peer_id, machine_name)

    def _peer_id(self, conf_section):
        return conf_section.split('.')[1]

    def __main_section(self, conf_section):
        return conf_section.split('.', 1)[0]

    def _peer_sections(self):
        return [sec for sec in self.parser.sections() if
                sec.startswith(PEERS + '.') and
                len(sec.split('.')) == 2]

    def __sections(self, section):
        return [sec for sec in self.parser.sections() if
                sec.startswith(PEERS + '.') and
                sec.endswith(section)]


class LaunchJSONParser(ScenarioParser):

    def __init__(self, obci_base_dir, scenario_base_dir, logger=None):
        self.base_dir = obci_base_dir
        self.scenario_dir = scenario_base_dir
        self.config = None
        self.logger = logger or logging.getLogger("launcher.LaunchJSONParser")
        self.load = {}

    def parse(self, p_file, p_config_obj, apply_globals=False):
        self._prepare(p_file, p_config_obj)
        self._do_parse(apply_globals)
        return True

    def _prepare(self, p_file, p_config_obj):
        self.load = json.load(p_file)
        self.config = p_config_obj

    def _peer_sections(self):
        items = list(self.load[PEERS].keys())
        if 'scenario_dir' in items:
            items.remove('scenario_dir')
        return items

    def _check_sections(self):
        for section in self.load.keys():
            if section not in SYS_SECTIONS:
                raise OBCISystemConfigError("Unrecognized launch file section: {0}".format(section))

    def _load_general_settings(self):
        items = self.load[PEERS]

        if 'scenario_dir' in items:
            self.config.scenario_dir = items['scenario_dir']
            self.config.scenario_dir = expand_path(self.config.scenario_dir, base_dir=self.scenario_dir)

    def _load_peer_ids(self, peer_sections):
        for peer_id in peer_sections:
            self.logger.info("adding peer %s", peer_id)
            self.config.add_peer(peer_id)

    def _load_launch_data(self, peer_sections):
        for sec in peer_sections:
            items = list(self.load[PEERS][sec].items())
            self._load_peer(sec, items)

    def _parse_peer_config_section(self, peer_id, peer_config_section, peer_path):
        # we do not apply globals when parsing JSON - we just assume
        # the globals are already in the JSON config
        # TODO! apply them if parameter _apply_globals is set
        # and they are not present in the config

        peer_cfg, peer_parser = parse_peer_default_config(
            peer_id, peer_path, self.logger)
        config = peer_config_section
        if config:
            self.logger.info("parsing _custom_ JSON config "
                             "for peer %s. %s ", peer_id, str(config))
            json_parser = parser("python")
            json_parser.parse(config, peer_cfg)

        self.config.set_peer_config(peer_id, peer_cfg)
        peer_sec = self.load[PEERS][peer_id]
        if CONFIG_SRCS in peer_sec:
            for src_name, src_id in peer_sec[CONFIG_SRCS].items():
                self.config.set_config_source(peer_id, src_name, src_id)
        if LAUNCH_DEPS in peer_sec:
            for dep_name, dep_id in peer_sec[LAUNCH_DEPS].items():
                self.config.set_launch_dependency(peer_id, dep_name, dep_id)

    def _set_config_params(self):
        pass

    def _set_peer_machine(self, peer_id, machine_name):
        self.config.set_peer_machine(peer_id, machine_name)

    def _peer_id(self, section):
        return section


def parse_peer_default_config(peer_id, peer_program_path, logger=None, apply_globals=False):
    peer_parser = parser("ini")
    peer_cfg = PeerConfig(peer_id)
    conf_path = default_config_path(peer_program_path)
    if apply_globals:
        for param, value in CONFIG_DEFAULTS.items():
            peer_cfg.add_local_param(param, value)
    if conf_path:

        with codecs.open(conf_path, "r", "utf8") as f:
            if logger:
                logger.debug("parsing default config for peer %s, %s ", peer_id, conf_path)
            peer_parser.parse(f, peer_cfg)

    return peer_cfg, peer_parser


def extend_experiment_config(exp_config, peer_id, peer_path,
                             config_sources=None, launch_deps=None,
                             custom_config_path=None, param_overwrites=None,
                             machine=None, apply_globals=True):
    peer_cfg, cfg_parser = parse_peer_default_config(
        peer_id, peer_path, apply_globals=apply_globals)
    if custom_config_path:
        logging.getLogger("launcher.LaunchJSONParser").debug("parsing _custom_ config for peer  ", peer_id,
                                                             custom_config_path)
        with codecs.open(custom_config_path, "r", "utf8") as f:
            cfg_parser.parse(f, peer_cfg)

    return exp_config.extend_with_peer(peer_id, peer_path, peer_cfg,
                                       config_sources, launch_deps,
                                       param_overwrites, machine)
