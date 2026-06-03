# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.
import itertools
import os
import argparse
from ..common.config_helpers import (LOCAL_PARAMS, EXT_PARAMS, CONFIG_SOURCES, PEER_CONFIG_SECTIONS,
                                     LAUNCH_DEPENDENCIES,
                                     CS, LP, LD, EP)

from ..launcher.launcher_tools import expand_path

from . import peer_config_parser
from . import peer_config_serializer
from . import peer_config


class BasePeerCmdParser:

    def __init__(self, add_help=True):

        self.parser = argparse.ArgumentParser(usage="%(prog)s peer_id base_config_file [options]", add_help=add_help)
        self.configure_argparser(self.parser)
        self.parser.add_argument('peer_id',
                                 help="Unique name for this instance of this peer")
        self.conf_parser = self.parser

    def configure_argparser(self, parser):

        parser.add_argument(LP, '--' + LOCAL_PARAMS,
                            nargs='+',
                            action=LocParamAction,
                            help="Local parameter override value: param_name, value.")
        parser.add_argument(EP, '--' + EXT_PARAMS, nargs=2, action=ExtParamAction,
                            help="External parameter override value: param_name value .")

        parser.add_argument(CS, '--' + CONFIG_SOURCES, nargs=2, action=ConfigSourceAction,
                            help="Config source ID assignment: src_name peer_id")
        parser.add_argument(LD, '--' + LAUNCH_DEPENDENCIES, nargs=2, action=LaunchDepAction,
                            help="Launch dependency ID assignment: dep_name peer_id")

        parser.add_argument('-f', '--config_file', type=path_to_file, action='append',
                            help="Additional configuration files: [path_to_file].ini")

    def parse_cmd(self, some_args=None):
        args = self.parser.parse_args(some_args)

        config_overrides = {}
        other_params = {}

        for attr, val in vars(args).items():
            if attr in PEER_CONFIG_SECTIONS:
                config_overrides[attr] = val if val is not None else {}
            else:
                other_params[attr] = val
        if other_params['config_file'] is None:
            other_params['config_file'] = []
        return config_overrides, other_params


class PeerCmd(BasePeerCmdParser):

    def __init__(self, add_help=True):
        super(PeerCmd, self).__init__(add_help)
        self.parser.add_argument('base_config_file', type=path_to_file,
                                 help="Base and mandatory configuration file for this peer.\n\
                            (there should be a your_module_name.ini in the same directory as your_module_name.")


class PeerParamAction(argparse.Action):

    def __call__(self, parser, namespace, values, option_string=None):
        par, value = values[0], values[1]
        dic = getattr(namespace, self.dest)
        if dic is None:
            dic = {}
        dic[par] = value
        setattr(namespace, self.dest, dic)


class LocParamAction(PeerParamAction):

    def __call__(self, parser, namespace, values, option_string=None):
        if len(values) < 2:
            raise argparse.ArgumentTypeError("loc_param: Param name and value not specified!" + option_string)

        par = values[0]
        vals = []
        for v in values[1:]:
            vals.append(str(v))
        value = ' '.join(vals)
        dic = getattr(namespace, self.dest)
        if dic is None:
            dic = {}
        dic[par] = value
        setattr(namespace, self.dest, dic)


class ExtParamAction(PeerParamAction):
    pass


class ConfigSourceAction(PeerParamAction):
    pass


class LaunchDepAction(PeerParamAction):
    pass


def path_to_file(string):
    pth = expand_path(string)
    if not os.path.exists(pth):
        msg = "{} -- path not found!".format(pth)
        raise argparse.ArgumentTypeError(msg)
    return pth


def peer_overwrites_pack(args):
    overwrites = _split_into_singular_overwrites(args)
    packed = [peer_args(ov) for ov in overwrites]
    return packed


def _split_into_singular_overwrites(args):
    start_markers = ['-peer', '--peer']
    start_and_nonstart_groups = itertools.groupby(args,
                                                  lambda arg: arg in start_markers)
    for is_start_marker, group in start_and_nonstart_groups:
        if not is_start_marker:
            yield list(group)


def peer_args(vals):
    pcmd = BasePeerCmdParser(add_help=False)
    ovr, other = pcmd.parse_cmd(vals)
    return [ovr, other]


def merge_overwrites_per_peer(overwrites):
    merged_per_peer = {}
    for overwrites_per_type, metadata in overwrites:
        peer_id = metadata['peer_id']
        if peer_id in merged_per_peer:
            currently = merged_per_peer[peer_id][0]
            for type, this_type_overwrites in overwrites_per_type.items():
                currently[type].update(this_type_overwrites)
        else:
            merged_per_peer[peer_id] = [overwrites_per_type, metadata]
    return list(merged_per_peer.values())


def peer_overwrites_cmd(pack):
    args = ['--ovr']
    for [ovr, other] in pack:
        conf = peer_config.PeerConfig(peer_id=other['peer_id'])
        cfg_parser = peer_config_parser.parser('python')
        cfg_parser.parse(ovr, conf)
        args += ['--peer', other['peer_id']]
        ser = peer_config_serializer.PeerConfigSerializerCmd()
        ser.serialize(conf, args)
        if other['config_file']:
            for f in other['config_file']:
                args += ['-f', f]
    return args
