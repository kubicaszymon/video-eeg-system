# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Module providing useful property to config handling for ConfiguredPeer."""
import os


def join_strings(j_string):
    """Join strings. Helper function for param_property."""
    return ';'.join(map(str, j_string))


def split_string(s_string):
    """Split strings. Helper function for param_property."""
    if len(s_string) == 0:
        return []
    return s_string.split(';')


def split_floats(s_float):
    """Split floats. Helper function for param_property."""
    return [float(j) for j in split_string(s_float)]


def extract_path(path):
    """Extract path from string (home directory). Helper function for param_property."""
    return os.path.join(os.path.expanduser(path))


def split_ints(s_int):
    """Split ints. Helper function for param_property."""
    return [int(j) for j in split_string(s_int)]


def string_to_dict(s_dict):
    """
    Extract keys and values from multi-line string. Helper function for param_property.

    example (tabulator at the beginning of the line:
    param =
        key1:value1
        key2:value2
    """
    dictionary = dict()
    for line in s_dict.splitlines():
        if line:
            [key, value] = line.split(':', 1)
            dictionary[key] = extract_path(value)
    return dictionary


def one_line_string_to_dict(s_dict):
    """
    Extract keys and values from one-line string. Helper function for param_property.

    example:
    param=key1:value1;key2:value2
    """
    dictionary = dict()
    for line in s_dict.split(';'):
        if line:
            [key, value] = line.split(':', 1)
            value = value.strip()
            dictionary[key.strip()] = float(value) if value.isdigit() else value
    return dictionary


class cached_property(property):
    """
    Decorator.

    Caches given property - minimising usage of __get__ methods.
    """

    def __init__(self, *args, **kwargs):
        """It calls getter method only once. Clears cache when new value is set or property is deleted."""
        super().__init__(*args, **kwargs)
        self._cached_name = '_' + self.fget.__name__ + '_cached'

    def __get__(self, obj, cls):
        """Get cached attribute."""
        if obj is None:
            return self
        if not hasattr(obj, self._cached_name):
            setattr(obj, self._cached_name, super().__get__(obj, cls))
        return getattr(obj, self._cached_name)

    def clear(self, obj):
        """Delete attribute/propery cache."""
        try:
            delattr(obj, self._cached_name)
        except AttributeError:
            pass

    def __set__(self, obj, value):
        """Clear cache and set attribute."""
        self.clear(obj)
        return super().__set__(obj, value)

    def __delete__(self, obj):
        """Delete attribute."""
        self.clear(obj)
        try:
            super().__delete__(obj)
        except AttributeError:
            pass


def noop(value):
    """Do nothing."""
    return value


class param_property(cached_property):
    """Cached property which uses ConfiguredPeers config."""

    @staticmethod
    def cached_name(param_name):
        """Provide name of cached attribute, which stores param_property."""
        return '_' + param_name + '_cached'

    @staticmethod
    def clear_cache(obj, param):
        """Clear cache on cached param on object."""
        try:
            delattr(obj, param_property.cached_name(param))
        except AttributeError:
            pass

    def __init__(self, param_name, deserializer=noop, serializer=str, fget=None, fset=None, fdel=None, doc=None):
        """
        Property that automatically calls set_param and get_param on self, and does serialization and deserialization.

        Useful in  :class:`~obci.core.configured_peer.ConfiguredPeer` subclasses to use with params.

        :param param_name: name of param
        :param serializer: one argument function that serializes data
        :param deserializer: one argument function that deserializes data
        """
        super().__init__(fget or self.get_param, fset or self.set_param, fdel, doc)
        self.param_name = param_name
        self.serializer = serializer
        self.deserializer = deserializer
        self._cached_name = self.cached_name(param_name)

    def set_param(self, instance, value):
        """Set param to cache, to peer config."""
        return instance.set_param(self.param_name, self.serializer(value))

    def get_param(self, instance):
        """Get param from config."""
        if instance.get_param(self.param_name):
            return self.deserializer(instance.get_param(self.param_name))
        else:
            return None

    def getter(self, fget):
        """
        Create getter for cached config param property.

        More info: https://docs.python.org/3.5/howto/descriptor.html
        """
        return type(self)(self.param_name, self.deserializer, self.serializer, fget, self.fset, self.fdel, self.__doc__)

    def setter(self, fset):
        """
        Create getter for cached config param property.

        More info: https://docs.python.org/3.5/howto/descriptor.html
        """
        return type(self)(self.param_name, self.deserializer, self.serializer, self.fget, fset, self.fdel, self.__doc__)

    def deleter(self, fdel):
        """
        Create getter for cached config param property.

        More info: https://docs.python.org/3.5/howto/descriptor.html
        """
        return type(self)(self.param_name, self.deserializer, self.serializer, self.fget, self.fset, fdel, self.__doc__)


class raw_param_property(param_property):
    """Cached property which uses ConfiguredPeers config.

    Doesn't return None for empty config strings - tries to deserialize them instead.
    """
    def get_param(self, instance):
        """Get param from config."""
        return self.deserializer(instance.get_param(self.param_name))


class bool_property(raw_param_property):
    def _deserializer(self, string):
        return bool(int(string))

    def _serializer(self, val):
        return str(int(val))

    def __init__(self, name):
        super(bool_property, self).__init__(name, self._deserializer, self._serializer)
