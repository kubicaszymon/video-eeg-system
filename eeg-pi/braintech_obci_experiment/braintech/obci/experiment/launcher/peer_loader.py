# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
import importlib
import importlib.util
import inspect
import sys
import traceback
from pathlib import Path

from .launcher_tools import expand_path
from .system_config import OBCISystemConfigError
from braintech.obci.core.broker.peer import Peer


def _load_peer_from_module(module):
    # get list of runnable peers in module
    try:
        peers = [getattr(module, i) for i in module.__all__
                 if issubclass(getattr(module, i), Peer)]
    except AttributeError:
        message = ('Peer file ({}) must have defined __all__ variable with runnable Peer class name'
                   .format(module.__name__))
        raise OBCISystemConfigError(message)
    if len(peers) != 1:
        raise OBCISystemConfigError('Peer must have defined only one runnable peer in __all__')
    cls = peers[0]
    return cls


def _peer_file_path_loader(peer_module_path):
    peer_module_full_path = expand_path(peer_module_path)
    peer_module_name = 'braintech.obci.experiment.' + peer_module_path.replace('.py', '').replace('/', '.')
    try:
        spec = importlib.util.spec_from_file_location(peer_module_name, peer_module_full_path)

        if spec is None:
            raise ImportError('No module in provided path {}'.format(peer_module_path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except FileNotFoundError as e:
        raise ImportError from e
    return _load_peer_from_module(module)


def _peer_import_path_loader(peer_module_path):
    if '.' in peer_module_path:
        module_name, klass_name = peer_module_path.rsplit('.', 1)
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            parent_package_available = '.' in module_name and module_name.rsplit('.', 1)[0] in sys.modules
            if parent_package_available:
                # containing package is imported, so module path is probably valid
                # raise error to see details of ImportError (might me in dependencies)
                raise
        else:
            peer_klass = getattr(module, klass_name, None)
            if peer_klass and issubclass(peer_klass, Peer):
                return peer_klass
            # klass_name is actually a submodule name. Import peer from submodule
    return _load_peer_from_module(importlib.import_module(peer_module_path))


PEER_LOADERS = [_peer_import_path_loader, _peer_file_path_loader]


def get_peer_class(peer_module_path):
    import_errors = []
    for peer_loader in PEER_LOADERS:
        try:
            return peer_loader(peer_module_path)
        except ImportError:
            import_errors.append(traceback.format_exc())
    formatted_errors = '\n'.join(import_errors)
    raise ImportError('Could not import peer module in path {}, errors:\n'
                      '{}'.format(peer_module_path, formatted_errors))


def validate_path(peer_module_path):
    return get_peer_class(peer_module_path) is not None


def normalize_path(peer_path):
    try:
        peer_class = get_peer_class(peer_path)
    except AttributeError:
        raise OBCISystemConfigError("Path to peer executable not found! Path defined: " +
                                    peer_path + "   full path:  " + peer_path)
    else:
        return full_class_name(peer_class)


def full_class_name(klass):
    return klass.__module__ + '.' + klass.__qualname__


def default_config_path(peer_program_path):
    path = Path(expand_path(peer_program_path)).with_suffix('.ini')
    if path.exists():
        return str(path)
    try:
        peer_klass = _peer_import_path_loader(peer_program_path)
        path = Path(inspect.getfile(peer_klass)).with_suffix('.ini')
        if path.exists():
            return str(path)
    except ImportError:
        return ''
