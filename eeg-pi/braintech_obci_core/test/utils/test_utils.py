# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import pytest
from braintech.obci.core.utils.properties import param_property, cached_property


def _test_cached_property(obj):
    with pytest.raises(AttributeError):
        obj.param1
    obj.param = 1
    assert obj._param
    obj.param = 2
    assert obj.param == 2
    obj._param = '3'
    assert obj.param == 2, "Should be cached"
    del obj.param
    obj.param = 3
    assert obj.param == 3, "Should clear cache"


def test_cached_property():
    class TestObj:

        @cached_property
        def param(self):
            return self._param

        @param.setter
        def param(self, value):
            self._param = value
    _test_cached_property(TestObj())


def test_param_property():
    class TestObj:
        param = param_property('_param', int)

        @param.setter
        def param(self, val):
            self._param_setter = True
            TestObj.param.set_param(self, val)

        @param.getter
        def param(self):
            self._param_getter = True
            return TestObj.param.get_param(self)

        @param.deleter
        def param(self):
            self._param_deleter = True
            return TestObj.param.clear(self)

        def set_param(self, param, value):
            setattr(self, param, value)

        def get_param(self, param):
            return getattr(self, param)
    obj = TestObj()
    _test_cached_property(obj)
    assert obj._param == '3', "should be serialized"
    assert obj._param_setter
    assert obj._param_getter
    assert obj._param_deleter
