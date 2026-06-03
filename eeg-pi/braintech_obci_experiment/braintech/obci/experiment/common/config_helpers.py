# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

CONFIG_SOURCES = 'config_sources'
EXT_PARAMS = 'external_params'
LOCAL_PARAMS = 'local_params'
LAUNCH_DEPENDENCIES = 'launch_dependencies'
CS = '-c'
EP = '-e'
LP = '-p'
LD = '-d'
PEER_CONFIG_SECTIONS = [CONFIG_SOURCES, EXT_PARAMS, LOCAL_PARAMS, LAUNCH_DEPENDENCIES]


def module_id_type_check(module_id):
    _validate_if_string(module_id, debug_name='Module ID')


def param_name_type_check(param_name):
    _validate_if_string(param_name, debug_name='Parameter')


def reference_type_check(reference):
    _validate_if_string(reference, debug_name='Reference')


def _validate_if_string(value, debug_name):
    if not isinstance(value, str):
        raise ValueError('{} can only be strings (got {})'.format(debug_name, repr(value)))


def argument_not_empty_check(p_arg):
    if p_arg == '':
        raise ValueError('empty string')


def reference_split(p_reference):
    reference_type_check(p_reference)
    if '.' not in p_reference:
        raise ValueError("Invalid reference! Should be 'source_name.param_name', "
                         "got {}".format(p_reference))
    return p_reference.split('.', 1)
