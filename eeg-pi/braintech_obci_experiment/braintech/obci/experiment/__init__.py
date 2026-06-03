# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.
try:
    from ._version import get_versions  # noqa

    versions = get_versions()
    __version__ = versions['version']
    __revision__ = versions['full-revisionid']
    del get_versions
except ImportError:
    __version__ = 'development'
    raise
