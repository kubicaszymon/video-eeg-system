# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Provides configuration support for peers."""

import abc
import argparse
import asyncio
import codecs
import logging
import os
import sys
import time
import traceback
from concurrent.futures import CancelledError
from typing import List, Tuple, Dict
from typing import Union

from ..common.config_helpers import PEER_CONFIG_SECTIONS
from . import peer_config
from . import peer_config_parser
from .config_defaults import CONFIG_DEFAULTS
from .peer_cmd import PeerCmd
from braintech.obci.core.broker import ObciException
from braintech.obci.core.broker import messages as messages_core
from .. import messages
from braintech.obci.core.broker.base_peer import PeerState
from braintech.obci.core.broker.message_handler_mixin import subscribe_message_handler, register_message_handler
from braintech.obci.core.broker.peer import Peer, PeerInitUrls
from braintech.obci.core.broker.peer import QueryAnswerUnknown
from braintech.obci.core.utils.asyncio import wait_for_condition, WaitForConditionTimeout
from braintech.obci.core.utils.openbci_logging import log_crash
from braintech.obci.core.utils.properties import param_property
from braintech.obci.core.utils.zmq import TimeoutException

CONFIG_FILE_EXT = 'ini'
WAIT_READY_SIGNAL = "wait_ready_signal"
CONFIG_FILE = "config_file"
PEER_ID = "peer_id"
BASE_CONF = "base_config_file"

LOGGER = logging.getLogger("peer_control_default_logger")

QUERY_RETRY_TIME = 2
QUERY_TIMEOUT_TIME = 20


class SignalReceiverMixin(metaclass=abc.ABCMeta):
    """
    Implements receiving of signal messages, optionally restricted to a single source.

    This mixin may be used by any :class:`BasePeer` subclass.
    """

    ALLOW_EMPTY_SOURCE = True

    async def _connections_established(self):
        await super()._connections_established()
        if not self.config.get_param("signal_source") and 'signal_source' in self.config.launch_deps:
            self.config.update_local_param('signal_source', self.config.launch_deps['signal_source'])
            param_property.clear_cache(self, 'signal_source')
        l_signal_source = self.config.get_param("signal_source")
        if not l_signal_source:
            l_signal_source = None
            if not self.ALLOW_EMPTY_SOURCE:
                raise ValueError('empty source not allowed')

        self.subscribe_for_specific_msg_subtype(messages_core.SignalMessage, l_signal_source,
                                                self._signal_message_handler)

    @abc.abstractmethod
    async def _signal_message_handler(self, msg):
        pass


class ConfiguredMixin(metaclass=abc.ABCMeta):
    """
    Implements support for managing and exchanging configuration parameters.

    This mixin may be used by any :class:`Peer` subclass.
    """

    def _parse_configured_kwargs(self, external_config_file=None,
                                 base_config_file=None,
                                 config_file=None,
                                 peer_id=None,
                                 **kwargs):
        self.external_config_file = external_config_file
        self.base_config_path = base_config_file
        self.file_list = ConfiguredMixin._prepare_config_file(config_file)
        self.peer_id = peer_id
        cmd_overrides, _ = ConfiguredMixin._parse_kwargs(kwargs)
        kwargs = ConfiguredMixin._prepare_kwargs(kwargs, peer_id)
        return kwargs, cmd_overrides

    @classmethod
    def create_parser(cls, argv: List[str], add_help=True):
        """Create a ArgumentParser instance for parsing this peer's command line parameters."""
        conf_parser = super().create_parser(argv, add_help=False)
        peer_cmd = PeerCmd(add_help=False)
        parser = argparse.ArgumentParser(add_help=True, parents=[conf_parser, peer_cmd.parser])
        return parser

    @staticmethod
    def _prepare_kwargs(kwargs, peer_id):
        kwargs['peer_id'] = peer_id
        for attr in PEER_CONFIG_SECTIONS:
            if attr in kwargs:
                kwargs.pop(attr)
        return kwargs

    @staticmethod
    def _parse_kwargs(kwargs):
        config_overrides = {attr: {} for attr in PEER_CONFIG_SECTIONS}
        other_params = {}
        for attr, val in kwargs.items():
            if attr in PEER_CONFIG_SECTIONS:
                config_overrides[attr] = val if val is not None else {}
            else:
                other_params[attr] = val
        if 'config_file' not in other_params:
            other_params['config_file'] = []
        else:
            other_params['config_file'] = ConfiguredMixin._prepare_config_file(other_params['config_file'])

        return config_overrides, other_params

    @staticmethod
    def _prepare_config_file(config_file):
        if config_file is not None:
            return [os.path.abspath(cf) for cf in config_file]
        else:
            return []


class ConfiguredPeer(ConfiguredMixin, Peer):
    """Peer subclass with support for setting and exchanging configuration parameters with other peers."""

    MANUAL_READY = False

    @log_crash
    def __init__(self, urls: Union[str, PeerInitUrls], **kwargs):
        """
        Create a new peer.

        Peer parameters will be extracted from the corresponding configuration files
        and passed to superclass constructor.
        Peer will be started automatically, unless parameter "autostart" is set to False.

        :param urls: string or PeerInitUrls with initial bootstrap addresses
        """
        kwargs, self.cmd_overrides = self._parse_configured_kwargs(**kwargs)
        self.config = peer_config.PeerConfig()
        self.peer_validate_params = None
        self._changed_params = {}
        self._load_provided_configs()

        # this would always run previously
        self._initialize_config_locally()
        super().__init__(urls, **kwargs)

    async def _check_for_query(self):
        try:
            self.config_server_rep_urls = (await self.query_async(messages_core.ConfigServerUrlQuery())).url
            return True
        except QueryAnswerUnknown:
            return False

    async def _connections_established(self):
        await super()._connections_established()

        try:
            await wait_for_condition(self._check_for_query, QUERY_TIMEOUT_TIME,
                                     QUERY_RETRY_TIME, 'Connection to config_server')
        except WaitForConditionTimeout as exc:
            await self.panic(exc)
            return

        result, details = await self._initialize_config()

        self._logger = self._create_logger()

        self._logger.info('Initialization results: {} {}'.format(result, details))

        self._logger.info('Registering config')
        await self.register_config()

        if not result:
            self._bad_initialization_result(details)

        # Set autostart and autoshutdown if they have changed.
        autostart = self.config.get_param('autostart')
        if autostart is not None:
            self.autostart = bool(int(autostart))

        autoshutdown = self.config.get_param('autoshutdown')
        if autoshutdown is not None:
            self.autoshutdown = bool(int(autoshutdown))

    async def _initialized(self):
        if not self.MANUAL_READY:
            await self.ready()
        await super(ConfiguredPeer, self)._initialized()

    async def _initialize_config(self):
        await self._request_ext_params()
        return self.config_ready()

    def _initialize_config_locally(self):
        return self.config_ready()

    def _load_provided_configs(self):
        # parse default config file
        self._load_config_base()
        self._load_defaults(CONFIG_DEFAULTS)
        self._load_config_external()
        # parse other config files (names from command line)
        for filename in self.file_list:
            self._load_config_from_file(filename, CONFIG_FILE_EXT, update=True)

        # parse overrides (from command line)
        dictparser = peer_config_parser.parser('python')
        dictparser.parse(self.cmd_overrides, self.config, update=True)

    def _load_defaults(self, globals_):
        for param, val in globals_.items():
            self.config.add_local_param(param, val)

    def _load_config_external(self):
        """Parse the external configuration file, provided by peer."""
        if self.external_config_file is not None:
            config_path = self.external_config_file.rsplit('.', 1)[0]
            config_path = '.'.join([config_path, CONFIG_FILE_EXT])
            self._load_config_from_file(config_path, CONFIG_FILE_EXT)

    def _load_config_base(self):
        """Parse the base configuration file, named the same as peer's implementation file."""
        self._load_config_from_file(self.base_config_path, CONFIG_FILE_EXT)

    def _load_config_from_file(self, p_path, p_type, update=False):
        with codecs.open(p_path, "r", "utf8") as f:
            parser = peer_config_parser.parser(p_type)
            parser.parse(f, self.config)

    @subscribe_message_handler(messages.ParamsChanged)
    def _handle_params_changed(self, msg):
        params = msg.params
        param_owner = msg.sender
        if param_owner == self.peer_id:  # message from self
            return
        self._logger.info("PARAMS CHANGED - %s:%s" % (msg.sender, ','.join(params.keys())))
        try:
            self._update_changed_params(param_owner, params)
        except ObciException as exc:
            self._logger.warning(str(exc))
            pass

    @register_message_handler(messages_core.PeerSetParamQuery)
    def _handle_set_param_query(self, msg: messages_core.PeerSetParamQuery):
        try:
            self.set_param(msg.key, msg.value)
        except (ValueError, KeyError):
            return messages_core.ErrorMsg(details='key_error')
        except Exception:
            return messages_core.ErrorMsg(details=traceback.format_exc())
        return messages_core.OkMsg()

    def _update_changed_params(self, param_owner, params):
        """Update peer's params. Raise ObciException if peer is running."""

        def _check_state():
            if self.is_running:
                raise ObciException("Can't change params of running peer. Peer id = {}".format(self.peer_id))

        old_values = {}
        updated = {}
        if param_owner in self.config.config_sources.values():
            src_params = self.config.params_for_source(param_owner)
            for par_name in [par for par in params if par in src_params]:
                old = self.config.get_param(src_params[par_name])
                new = params[par_name]
                if old != new:
                    _check_state()
                    old_values[par_name] = old
                    updated[par_name] = new
                    self.config.set_param_from_source(param_owner, src_params[par_name], new)
                    param_property.clear_cache(self, src_params[par_name])

        if param_owner == self.peer_id:
            local_params = self.config.local_params
            for par, val in params.items():
                if par not in local_params:
                    # protest?
                    continue
                if val != self.config.get_param(par):
                    _check_state()
                    old_values[par] = self.config.get_param(par)
                    updated[par] = val
                    self.config.update_local_param(par, val)
                    param_property.clear_cache(self, par)

    def config_ready(self) -> Tuple[bool, Dict[str, List[str]]]:
        """
        Return a detailed description of whether the configuration is initialized and ready to be used.

        Returns a tuple, consisting of
        * boolean value, depending of whether the configuration is initialized
        * dictionary (string -> list) with detailed information
        """
        rd, details = self.config.config_ready()
        return rd and self.peer_id is not None, details

    @log_crash
    def has_param(self, p_name):
        """Return True if parameter p_name is available in peer's configuration, False otherwise."""
        return self.config.has_param(p_name)

    @log_crash
    def get_param(self, param_name):
        """
        Return the value of the parameter with a given name.

        If parameter does not exist, raise KeyError.
        """
        return self.config.get_param(param_name)

    def set_param(self, param_name, param_value):
        """
        Set the value of the parameter with a given name.

        :param param_name: parameter name (key)
        :param param_value: value to set
        """
        try:
            old = self.config.get_param(param_name)
        except KeyError:
            # let PeerConfig to handle setting new/non existent params
            pass
        else:
            if old == param_value:
                return
        self._logger.debug('SETTING PARAMS %s, %s', param_name, param_value)
        result = self.config.update_local_param(param_name, param_value)
        param_property.clear_cache(self, param_name)
        self._changed_params[param_name] = param_value
        self.create_task(self._notify_params_changed())
        return result

    async def _notify_params_changed(self):
        # This method is called for every set_param, but with slight delay (next asyncio loop step).
        # On the first call it will send changed params, and next calls will do nothing.
        changed_params = self._changed_params
        self._changed_params = {}
        if changed_params:
            msg = messages.UpdateParams(receiver=None,
                                        params=changed_params,
                                        ext_params=None)
            await self.__query(msg)

    def param_values(self):
        """Return a dictionary of all peer's parameters."""
        return self.config.param_values

    async def register_config(self):
        """Finalize the set of configuration parameters and send them to Broker."""
        sender = self.peer_id
        ext_params = self.config.ext_param_defs
        # register also external param definitions: param_name <---> (peer_id_of_config_source, param_name)
        for par in ext_params:
            ext_def = ext_params[par]
            symname = ext_def[0]
            ext_params[par] = (self.config.config_sources[symname], ext_def[1])

        msg = messages.RegisterPeerConfig(sender=sender,
                                          receiver=None,
                                          params=self.config.local_params,
                                          ext_params=ext_params)
        reply = await self.__query(msg)

        self._logger.debug("Register config response: %s", reply)
        if reply is None:
            self._logger.error('config registration unsuccesful!!!! %s',
                               str(reply))
        elif not isinstance(reply, messages.PeerRegistered):
            self._logger.error('config registration unsuccesful!!!! %s',
                               str(reply))

    async def _request_ext_params(self, retries=400):
        # TODO set timeout and retry count
        self._logger.info("requesting external parameters")
        ready, details = self.config.config_ready()
        while not ready and retries:
            for src in self.config.used_config_sources():
                params = list(self.config.unset_params_for_source(src).keys())
                msg = messages.ConfigParamsRequest(
                    param_names=params,
                    receiver=self.config.config_sources[src],
                )
                reply = await self.__query(msg)
                if isinstance(reply, messages.ConfigError):
                    self._logger.warning("peer {0} has not yet started".format(msg.receiver))

                elif isinstance(reply, messages.ConfigParams):
                    params = reply.params
                    for par, val in params.items():
                        self.config.set_param_from_source(reply.sender, par, val)
                        param_property.clear_cache(self, par)
                else:
                    self._logger.error('Unexcpected reply received: {}'.format(reply))

            time.sleep(0.4)  # required
            ready, details = self.config.config_ready()
            retries -= 1

        if ready:
            self._logger.info("External parameters initialised %s", str(self.config.config_ready()))

        return ready, details

    async def _dependencies_are_ready(self) -> None:
        """
        Run just before ready signal.

        Method which allows peer to do last second configuration of itself after
        its dependencies are ready.
        """
        pass

    async def _send_peer_ready(self):

        await self._synchronize_ready()
        await self._dependencies_are_ready()
        self._logger.info('sending ready signal.')
        msg = messages.PeerReady()
        await self.__query(msg)

    async def _synchronize_ready(self):
        # TODO set timeout and retry count
        others = list(self.config.launch_deps.values())
        msg = messages.PeerReadyQuery(deps=others)
        ready = False
        while not ready:
            reply = await self.__query(msg)
            if reply and isinstance(reply, messages.PeerReadyStatus):
                ready = reply.peers_ready
            if not ready:
                self._logger.debug("Dependencies %s not ready. waiting...",
                                   str(others))
                await asyncio.sleep(2)  # required
        self._logger.info("Dependencies %s are ready, I can start working.",
                          str(others))

    async def __query(self, msg):
        try:
            reply = await self.ask_peer(self.config_server_rep_urls, msg)
        except CancelledError:
            raise
        except TimeoutException:
            raise
        except Exception as e:
            self._logger.exception("Query failed" + str(e))
            reply = None
        return reply

    def _bad_initialization_result(self, details):
        self._logger.critical('config initialisation FAILED: {0}'.format(details))
        sys.exit(1)

    async def ready(self):
        """
        Send READY message to the broker.

        Peer should have been fully initialized when this method is called.
        Initialization, which requires other peers (launch dependencies) is called during this method as
        self._dependencies_are_ready().
        """
        # TODO: Move after _initialize().
        self._logger.info('Sending ready')
        await self._send_peer_ready()
        if self._state == PeerState.connected:
            self._state = PeerState.ready

    def _param_vals(self):
        vals = self.config.param_values
        if 'channels_info' in vals and self.config.peer_id != 'amplifier':
            vals['channels_info'] = '[...truncated...]'
        return vals

    def _crash_extra_description(self, exc):
        """
        Called when the peer crashes, to provide additional peer description to the crash report.

        Return string.
        """
        return "peer '%s' config params: %s" % (self.config.peer_id,
                                                self._param_vals())

    def _crash_extra_data(self, exc=None):
        """
        Called when the peer crashes, to provide additional peer data to the crash report.

        Return a dictionary.
        """
        return {
            "config_params": self._param_vals(),
            "peer_id": self.config.peer_id,
            "experiment_uuid": self.get_param("experiment_uuid")
        }

    def _crash_extra_tags(self, exception=None):
        return {'obci_part': 'obci',
                "experiment_uuid": self.get_param("experiment_uuid")}

    async def _shutting_down(self):
        if self.is_ready:
            msg = messages.UnregisterPeerConfig()
            try:
                await self.__query(msg)
            except TimeoutException:
                self._logger.info('Config server is dead? cannot unregister,\ncontinue with shutdown')
        await super()._shutting_down()
