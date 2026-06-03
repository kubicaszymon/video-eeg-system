# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Package providing OBCI configured peer config utility messages messages."""
from braintech.obci.core.broker.messages import BaseMessage
from braintech.obci.core.broker.messages.fields import Field


class Param(BaseMessage):
    name = Field(str)
    value = Field(str)


class ConfigParamsRequest(BaseMessage):
    receiver = Field(str)
    param_names = Field(list, None)  # List[str]
    ext_params = Field(dict, None)  # Dict[str, str]


class ConfigParams(BaseMessage):
    receiver = Field(str, None)
    params = Field(dict, None)  # Dict[str, str]
    ext_params = Field(dict, None)  # Dict[str, str]


class RegisterPeerConfig(ConfigParams):
    pass


class UpdateParams(ConfigParams):
    pass


class ParamsChanged(ConfigParams):
    pass


class PeerIdentity(BaseMessage):
    pass


class PeerReady(PeerIdentity):
    pass


class PeerReadySignal(PeerIdentity):
    pass


class UnregisterPeerConfig(PeerIdentity):
    pass


class PeerRegistered(PeerIdentity):
    pass


class PeerReadyQuery(PeerIdentity):
    deps = Field(list, None)  # List[str]


class PeerReadyStatus(BaseMessage):
    receiver = Field(str)
    peers_ready = Field(bool)


class ConfigError(BaseMessage):
    rq_type = Field(str, None)
    error_str = Field(str, None)
    errno = Field(str, None)


class LauncherCommand(BaseMessage):
    serialized_msg = Field(str)  # serialized to json, templates in launcher_messages.py
