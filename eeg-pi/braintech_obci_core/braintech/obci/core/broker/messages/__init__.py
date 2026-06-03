# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

from braintech.obci.core.broker.messages.types import *  # noqa


def deserialize(msg: 'Tuple[bytes]'):
    from . import base
    return base.MessageMeta.deserialize(msg)
