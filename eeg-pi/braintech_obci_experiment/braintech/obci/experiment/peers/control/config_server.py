# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Module providing ConfigServer Peer."""
import configparser
import json
import os
from typing import Union

import zmq

from braintech.obci.experiment.common.obci_control_settings import DEFAULT_SANDBOX_DIR
from braintech.obci.core.broker import messages as messages_core
from braintech.obci.experiment import messages
from braintech.obci.experiment.peer.configured_peer import ConfiguredMixin
from braintech.obci.core.broker.message_handler_mixin import register_message_handler
from braintech.obci.experiment.messages import launcher_msg_types
from braintech.obci.core.broker.peer import Peer, PeerInitUrls

__all__ = ('ConfigServer',)


class ConfigServer(ConfiguredMixin, Peer):
    """
    Peer which stores configuration of all ConfiguredPeers in experiment.

    Provides configuration options from one Peer to another,
    sends configuration changes and helps peers to synchronize
    their start.
    """

    def __init__(self, urls: Union[str, PeerInitUrls], **kwargs):
        """Initalize ConfigServer peer."""
        self._configs = {}
        self._ext_configs = {}
        self._ready_peers = []
        self.__to_all = False
        self.launcher_sock = None
        self.ctx = None
        # additional params
        kwargs, self._params = self._parse_configured_kwargs(**kwargs)
        self.addr = self._params['local_params'].get('launcher_socket_addr', '')
        self.exp_uuid = self._params['local_params'].get('experiment_uuid', '')
        self.log_dir = self._params['local_params'].get('log_dir', None)

        super().__init__(urls, **kwargs)

        self._old_configs = self._stored_config()
        self._restore_peers = self._params['local_params'].get('restore_peers', '').split()

        for peer in self._restore_peers:
            if peer in self._old_configs["local"]:
                self._configs[peer] = dict(self._old_configs["local"][peer])
                self._ready_peers.append(peer)
            if peer in self._old_configs["ext"]:
                self._ext_configs[peer] = dict(self._old_configs["ext"][peer])
                # @log_crash requires logger to work,
                # if I want to see crashes of core Peer I need to initialise logger first

    async def _connections_established(self):
        # mandatory call
        await super()._connections_established()

        # Peers will query the config server for URL and then send messages to config_server

        # send ready to launcher
        if self.addr != '':
            self.ctx = zmq.Context()
            self.launcher_sock = self.ctx.socket(zmq.PUSH)
            try:
                self.launcher_sock.connect(self.addr)
            except Exception:
                self._logger.error("failed to connect to address " +
                                   self.addr + " !!!")
                self.launcher_sock = None
            else:
                self._logger.info("OK: connected to " + self.addr)
                launcher_msg_types.ConfigServerReadyMsg().send(self.launcher_sock)

    def _config_path(self):
        base_config_path = "config_server.ini"
        return os.path.abspath(os.path.join(DEFAULT_SANDBOX_DIR, base_config_path))

    def _stored_config(self):
        parser = configparser.RawConfigParser()
        storedconf = self._config_path()
        if os.path.exists(storedconf):
            with open(storedconf, 'r') as f:
                self._logger.info("found stored config %s", str(storedconf))
                parser.readfp(f)
        else:
            self._logger.info("No config stored %s", str(storedconf))
        if parser.has_option('local_params', 'stored_config'):
            stored = parser.get('local_params', 'stored_config')
        else:
            stored = '{}'
        return json.loads(stored)

    _saving_config_handle = None

    def _save_config(self):
        # Schedule file update at most once per second
        if self._saving_config_handle is None:
            self._saving_config_handle = self._loop.call_later(1.0, self.__save_config)

    def __save_config(self):
        self._saving_config_handle = None
        base_config_path = self._config_path()
        parser = configparser.RawConfigParser()
        # print "CONFIG_SERVER save path", base_config_path
        if os.path.exists(base_config_path):
            with open(base_config_path, 'r') as f:
                parser.readfp(f)
        if not parser.has_section('local_params'):
            parser.add_section('local_params')

        parser.set('local_params', 'stored_config', json.dumps({"local": self._configs, "ext": self._ext_configs}))
        parser.set('local_params', 'launcher_socket_addr', '')
        parser.set('local_params', 'experiment_uuid', '')
        parser.set('local_params', 'restore_peers', '')

        with open(base_config_path, 'w') as f:
            parser.write(f)
        try:
            os.chmod(base_config_path, 0o777)
        except OSError as e:
            self._logger.error("tried to change permissions to" +
                               base_config_path + "to 777 but" + str(e))
        else:
            self._logger.info("changed permissions to " + base_config_path + " to 777")

    def _send_launcher_msg(self, launcher_msg):
        # TODO: helper functions are NOT asyncio, rewrite someday?
        if launcher_msg is not None and self.launcher_sock is not None:
            launcher_msg.send(self.launcher_sock)

    @register_message_handler(messages.ConfigParamsRequest)
    async def _handle_get_config_params(self, msg):
        param_owner = msg.receiver
        names = msg.param_names
        if param_owner == 'config_server':
            params = dict(experiment_uuid=self.exp_uuid)

        elif param_owner not in self._configs:
            return messages.ConfigError(self.peer_id)
        else:
            # TODO error when param_name does not exist?
            params = self._get_params(param_owner, names)
        return messages.ConfigParams(sender=param_owner, params=params)

    def _get_params(self, param_owner, names, params=None):
        params = params or {}
        self._logger.info("looking for %s, param names=%s" % (param_owner, str(names)))
        if param_owner not in self._configs:
            self._logger.info("%s not in %s" % (param_owner, str(self._configs)))
            msg = messages.ConfigError()
            return msg, msg.type, None

        for name in names:
            if name in self._configs[param_owner]:
                params[name] = self._configs[param_owner][name]
            elif name in self._ext_configs[param_owner]:
                owner, name = self._ext_configs[param_owner][name]
                params = self._get_params(owner, [name], params)
        return params

    @register_message_handler(messages.RegisterPeerConfig)
    async def _handle_register_peer_config(self, msg):
        self._logger.debug(str(msg))
        params = msg.params
        ext_params = msg.ext_params
        peer_id = msg.sender

        if peer_id in self._configs:
            msg_reply = messages.ConfigError()
            launcher_msg = None
        else:
            self._configs[peer_id] = params
            self._ext_configs[peer_id] = ext_params
            msg_reply = messages.PeerRegistered(sender=peer_id)
            launcher_msg = launcher_msg_types.ObciPeerRegisteredMsg(
                peer_id=peer_id,
                params=params,
            )
        self._save_config()
        self._send_launcher_msg(launcher_msg)
        return msg_reply

    @register_message_handler(messages.UnregisterPeerConfig)
    async def _handle_unregister_peer_config(self, msg):
        self._configs.pop(msg.sender)

        if msg.sender in self._ready_peers:
            self._ready_peers.remove(msg.sender)
        self._save_config()
        return messages_core.OkMsg()

    @register_message_handler(messages.UpdateParams)
    async def _handle_update_params(self, msg):
        params = msg.params
        param_owner = msg.sender

        if param_owner not in self._configs:
            return messages.ConfigError(error_str="Peer unknown: {0}".format(param_owner))
        updated = {}
        for param in params:
            if param in self._configs[param_owner]:
                self._configs[param_owner][param] = params[param]
                updated[param] = params[param]

        if updated:
            launcher_msg = launcher_msg_types.ObciPeerParamsChangedMsg(
                peer_id=param_owner,
                params=updated,
            )
            self._save_config()
            self._send_launcher_msg(launcher_msg)
            msg_reply = messages.ParamsChanged(sender=param_owner, params=updated)
            self.send_message(msg_reply)
            return msg_reply

    @register_message_handler(messages.PeerReady)
    async def _handle_peer_ready(self, msg: messages.PeerReady):
        peer_id = msg.sender
        if peer_id not in self._configs:
            return messages.ConfigError()
        self._ready_peers.append(peer_id)
        launcher_msg = launcher_msg_types.ObciPeerReadyMsg(peer_id=peer_id)
        self._send_launcher_msg(launcher_msg)
        return messages.PeerReady(sender=peer_id)

    @register_message_handler(messages.PeerReadyQuery)
    async def _handle_peers_ready_query(self, message: messages.PeerReadyQuery):
        peer_id = message.sender
        if peer_id in self._configs:
            green_light = all(dep in self._ready_peers
                              for dep in message.deps)
            return messages.PeerReadyStatus(receiver=peer_id, peers_ready=green_light)
        else:
            return messages.ConfigError(self.peer_id)

    def _crash_extra_tags(self, exception=None):
        return {'obci_part': 'obci'}

    def _cleanup(self):
        """Shut down the Peer."""
        self._logger.debug('Closing launcher sock')
        if self.launcher_sock:
            self.launcher_sock.close()
        self._logger.debug('Destroying launcher zmq context')
        if self.ctx:
            self.ctx.destroy()
        self.__save_config()  # just in case there are pending changes
        super()._cleanup()


# TODO make doctests from this
"""
    srv = ConfigServer(settings.broker_addresses)
    print "REGISTRATION"
    reg = cmsg.fill_msg(types.REGISTER_PEER_CONFIG, sender="ja", receiver="")

    cmsg.dict2params(dict(wr=1, dfg=[1,2,3,4,'zuzanna']), reg)
    srv.handle_register_peer_config(reg)

    reg = cmsg.fill_msg(types.REGISTER_PEER_CONFIG, sender="ty", receiver="")
    cmsg.dict2params(dict(a=1, bb=['ssdfsdf', 'LOL']), reg)
    srv.handle_register_peer_config(reg)

    reg = cmsg.fill_msg(types.REGISTER_PEER_CONFIG, sender="on", receiver="")
    cmsg.dict2params(dict(lll=0), reg)
    srv.handle_register_peer_config(reg)

    print srv._configs

    print "PEER_READY"
    rdy = cmsg.fill_msg(types.PEER_READY, peer_id="on")
    srv.handle_peer_ready(rdy)
    rdy = cmsg.fill_msg(types.PEER_READY, peer_id="ja")
    srv.handle_peer_ready(rdy)
    print srv._ready_peers

    print "PEERS_READY_QUERY"
    rdq = cmsg.fill_msg(types.PEERS_READY_QUERY, sender="ja", deps=["on, ty"])
    print srv.handle_peers_ready_query(rdq)[0]
    rdq = cmsg.fill_msg(types.PEERS_READY_QUERY, sender="ty", deps=["on"])
    print srv.handle_peers_ready_query(rdq)[0]

    print "GET_CONFIG_PARAMS"
    par = cmsg.fill_msg(types.GET_CONFIG_PARAMS, sender="ja", receiver="ty", param_names=['a','b'])
    print srv.handle_get_config_params(par)[0]
    par = cmsg.fill_msg(types.GET_CONFIG_PARAMS, sender="ja", receiver="ty", param_names=['bb'])
    rep = srv.handle_get_config_params(par)[0]
    print rep, "decoded params:\n", cmsg.params2dict(rep)

    print "DEREGISTRATION"
    unr = cmsg.fill_msg(types.UNREGISTER_PEER_CONFIG, peer_id="ja")
    srv.handle_unregister_peer_config(unr)
    print srv._configs
"""
# Temporary?? Fix to launcher, run class defined in PEER_MAIN_CLASS constant
