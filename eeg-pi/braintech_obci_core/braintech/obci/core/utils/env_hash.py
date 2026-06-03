# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Module defines a single method get_env_hash that returns unique string for current operating system build."""
import getpass
import hashlib
import platform


def get_env_hash():
    """Method returns unique string for current operating system build, version, hostname and username."""
    unique_hash = hashlib.md5()
    for x in platform.uname():
        unique_hash.update(x.encode())
    unique_hash.update(getpass.getuser().encode())
    return unique_hash.hexdigest()[:10]
