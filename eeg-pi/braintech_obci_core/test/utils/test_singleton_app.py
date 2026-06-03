# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import sys
import multiprocessing

from braintech.obci.core.utils.singleton_app import SingleApplicationInstance, SingleInstanceException


def f(name):
    try:
        me2 = SingleApplicationInstance(flavor_id=name)  # noqa
    except SingleInstanceException:
        sys.exit(-1)


def test_1():
    me = SingleApplicationInstance(flavor_id="test-1")
    del me  # now the lock should be removed


def test_2():
    p = multiprocessing.Process(target=f, args=("test-2",))
    p.start()
    p.join()
    # the called function should succeed
    assert p.exitcode == 0, "%s != 0" % p.exitcode


def test_3():
    me = SingleApplicationInstance(flavor_id="test-3")  # noqa -- me should still kept
    p = multiprocessing.Process(target=f, args=("test-3",))
    p.start()
    p.join()
    # the called function should fail because we already have another
    # instance running
    assert p.exitcode != 0, "%s != 0 (2nd execution)" % p.exitcode
    # note, we return -1 but this translates to 255 meanwhile we'll
    # consider that anything different from 0 is good
    p = multiprocessing.Process(target=f, args=("test-3",))
    p.start()
    p.join()
    # the called function should fail because we already have another
    # instance running
    assert p.exitcode != 0, "%s != 0 (3rd execution)" % p.exitcode
