# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

from typing import Any, Iterable

from .. import ObciException


class FieldNotInitiated(ObciException):
    pass


class UnsetFieldWithoutDefault(ObciException):
    pass


class WrongParamType(TypeError):
    def __init__(self, actual_type, expected_types):
        self.actual_type = actual_type
        self.expected_types = expected_types


class Field:
    """
    Class representing Fields of serializable message.

    Gives basic type validation. Instances can be called to get and set value
    instead of using getter and setter.
    """

    def __init__(self, accepted_types, *args):
        """
        Create a field.

        Accepts list of acceptable types, one type or many types as arguments.
        None is converted to NoneType.
        """
        if not isinstance(accepted_types, list):
            accepted_types = [accepted_types, ]
        if args:
            accepted_types.extend(args)
        accepted_types = [i if i is not None else type(i) for i in accepted_types]
        self._accepted_types = accepted_types

    @property
    def valid_types(self) -> Iterable:
        """Return types accepted by this field."""
        return self._accepted_types.copy()

    def validate(self, value: Any):
        """Return True if value can be written to this field."""
        if not isinstance(value, tuple(self._accepted_types)):
            raise WrongParamType(type(value), self.valid_types)

    def __repr__(self):
        """String representation."""
        return "<Field description, accepted types: {}>".format(self._accepted_types)


class FieldDescriptor:
    """Protocol descriptor to get and set Field values onto some class."""

    def __init__(self, desc: Field, name: str):
        """
        Init Field Descriptor.

        :param desc: `Field` class instance, which is used for validation.
        :param
        """
        self._field_descr = desc
        self._name = name

    def __get__(self, instance, owner):
        """Get value of the field from message."""
        try:
            return instance._data_dict[self._name]
        except IndexError:
            raise FieldNotInitiated('Value not set yet')

    def __set__(self, instance, value):
        """Set the value of the field."""
        try:
            self._field_descr.validate(value)
        except WrongParamType as ex:
            raise TypeError('Expected types for field <{}>'
                            ' of msg type <{}>: {}, got {}'
                            .format(self._name, instance.type,
                                    ex.expected_types,
                                    ex.actual_type)) from ex
        except TypeError as ex:
            raise TypeError("Value invalid for field <{}> of msg type <{}>:{}"
                            .format(self._name, instance.type, ex)) from ex

        instance._data_dict[self._name] = value
