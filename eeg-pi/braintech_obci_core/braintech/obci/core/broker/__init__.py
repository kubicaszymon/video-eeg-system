# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""
Core modules for BCI-Framework.

This module contains core modules for BCI-Framework such as
:mod:`obci.core.broker`, :mod:`obci.core.peer` and
:mod:`obci.core.messages`.
"""

import os

OBCI_DEBUG = 'OBCI_DEBUG' in os.environ  # type: bool
"""
bool: Automatically set to ``True`` if ``OBCI_DEBUG`` environment variable
is defined.

If enabled sets root logger level to :const:`logging.DEBUG` and enables all warnings
generated using :mod:`warnings` module.
"""

# Uncomment to force debug.
# OBCI_DEBUG = True  # noqa

if OBCI_DEBUG:
    import logging
    logging.basicConfig(level=logging.DEBUG)
    import warnings
    warnings.simplefilter('default')


TCP_MAGIC_BYTES_OBCI = b'OBCI'  # type: bytes
"""bytes: Byte sequence used by Broker's TCP/IP server to detect proper request from BCI-Framework peer."""

BROKER_TCP_IP_DEFAULT_PORT = 23821  # type: int
"""int: Default port for Broker's TCP/IP server."""

DEFAULT_HEARTBEAT_DELAY = 0.05  # type: float
"""float: Default delay between successive ``HEARTBEAT`` messages (50 ms)."""

HEARTBEAT_ERROR_INTERVAL = 5.0  # type: float
"""
float: Heartbeat error threshold

Heartbeat error is generated for peer from which we hadn't received ``HEARTBEAT`` message in given interval.
Default: 500 ms
"""

HEARTBEAT_WARNING_INTERVAL = 0.2  # type: float
"""
float: Heartbeat warning threshold

Heartbeat warning is generated for peer from which we hadn't received ``HEARTBEAT`` message in given interval.
Default: 200 ms
"""

HEARTBEAT_JITTER_WARNING = 0.15 * DEFAULT_HEARTBEAT_DELAY  # type: float
"""
float: Heartbeat jitter warning threshold

Heartbeat jitter warning is generated for peer with jitter exceeding given threshold.
Default: 15% * :attr:`DEFAULT_HEARTBEAT_DELAY` = 7.5 ms
"""


class ObciException(Exception):
    """Common base class for all exceptions raised from BCI-Framework code."""


__all__ = (
    'OBCI_DEBUG',
    'ObciException',
    'TCP_MAGIC_BYTES_OBCI',
    'BROKER_TCP_IP_DEFAULT_PORT',
)
