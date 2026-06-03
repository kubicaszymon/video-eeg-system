# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
try:
    from .dummy_amp._dummy_amp import *
    from .native_lib._native_lib import *
except ImportError:
    import warnings

    warnings.warn("APT DEPENDENCIES might not be installed")
