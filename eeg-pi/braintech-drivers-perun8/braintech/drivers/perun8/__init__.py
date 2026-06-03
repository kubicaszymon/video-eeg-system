# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
try:
    from ._perun8 import *
except ImportError:
    import warnings

    warnings.warn("APT DEPENDENCIES might not be installed")
