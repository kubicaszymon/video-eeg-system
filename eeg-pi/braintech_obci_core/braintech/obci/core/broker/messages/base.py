# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""
Module defines classes used for serialization and de-serialization of messages.

Serialize predefined message types.

Message types and helper classes for OBCI messaging.
"""
import re
from json import JSONDecodeError
from typing import Optional, Tuple

from . import serializers
from .fields import Field
from .fields import FieldDescriptor
from .fields import UnsetFieldWithoutDefault
from .. import ObciException


class ConflictingMessageType(ObciException):
    pass


class MessageMeta(type):
    """
    Meta class for messages.

    All messages should have this class as meta, to be automatically registered.
    """

    registered_messages = {}

    @property
    def fields(self) -> dict:
        """Dict containing names (strings) of all fields and their descriptions."""
        return self._fields

    @property
    def type(self) -> str:
        """
        Type of this message, string, used in network communications.

        Used by receiving end to resolve Message class. Should be unique for every OBCI message.
        """
        return self.__TYPE__

    def __new__(mcs, name, bases, dct):
        """
        Create Message type classes.

        Creates and registers newly created Message class.
        Converts Field definitions to Field descriptors.
        Imports field descriptors from base classes.
        Fills networking string `__TYPE__` and `_fields` dict.
        """
        if '__TYPE__' not in dct:
            dct['__TYPE__'] = _camel2snake(name)

        fields = {}
        for base in bases:
            try:
                fields.update(base._fields)
            except AttributeError:
                pass

        latest_fields = {i: dct[i] for i in dct if isinstance(dct[i], Field)}
        fields.update(latest_fields)
        dct['_fields'] = fields

        cls = super().__new__(mcs, name, bases, dct)
        for field in latest_fields:
            field_description = getattr(cls, field)
            cls._fields[field] = field_description
            setattr(cls, field, FieldDescriptor(field_description, field))
        type = dct['__TYPE__']
        if type in mcs.registered_messages:
            raise ConflictingMessageType('Cannot have two message classes '
                                         'sharing same message type ({})'
                                         ' message class: {}'
                                         .format(type, cls.__qualname__))
        mcs.registered_messages[type] = cls
        return cls

    @classmethod
    def get_class_from_type(mcs, message_type: str):
        """Return Message class for network-type string."""
        return mcs.registered_messages[message_type]

    @classmethod
    def get_deserializer(mcs, message_type: str):
        """Get deserializer for given network message type."""
        return mcs.get_class_from_type(message_type).deserialize

    @classmethod
    def get_type_sender(cls, msg: Tuple[bytes]):
        try:
            type_id, sender, *_ = msg[0].decode('utf-8').split('^', maxsplit=2)
            return type_id, sender
        except Exception:
            raise ObciException('Invalid message format: invalid type or subtype')

    @classmethod
    def deserialize(mcs, msg: Tuple[bytes]):
        """
        Create `Message` object from ZMQ multipart message.

        :param msg: multipart message received by ZMQ
        :return: Message object
        """
        if len(msg) != 2:
            raise ObciException('Invalid message format')
        type_id, sender = mcs.get_type_sender(msg)
        try:
            deserializer = mcs.get_deserializer(type_id)
        except KeyError:
            raise KeyError('No deserializer for message type {}'.format(type_id))
        return deserializer(msg[1], sender=sender)

    @staticmethod
    def get_filter_bytes(msg_type: str, msg_subtype: Optional[str] = None) -> bytes:
        """Return message header (the first part of ZMQ multipart message) for OBCI."""
        return ((msg_type if msg_subtype is None else msg_type + '^' + msg_subtype) + '^').encode('utf-8')


def _camel2snake(name: str) -> str:
    """Convert CamelCase to snake_case."""
    first_cap_re = re.compile('(.)([A-Z][a-z]+)')
    all_cap_re = re.compile('([a-z0-9])([A-Z])')
    s1 = first_cap_re.sub(r'\1_\2', name)
    return all_cap_re.sub(r'\1_\2', s1).lower()


class BaseMessage(metaclass=MessageMeta):
    """
    Base class for all messages.

    All OBCI messages should inherit this class.
    Defines methods and basic `Field`s for all OBCI messages.
    """

    def __init__(self, sender: str = None, **kwargs):
        """
        Init message object.

        :param sender: ID of the sender of this message
        :param kwargs: you need to provide all non optional fields. (Optional Fields are defined as None)
        :raises TypeError: If not all required fields are set, or trying to set nonexistant fields.
        """
        self._data_dict = {}
        if sender is None:
            sender = ''
        self._sender = sender
        kwargs.update(self._get_defaults_for_unset_fields(kwargs))

        for k, v in kwargs.items():
            if k in self._fields:
                setattr(self, k, v)

    def _get_defaults_for_unset_fields(self, fields_values):
        types_with_defaults = [bool, str, bytes, int, complex, float, dict,
                               list, set, tuple, type(None)]
        unset_fields = set(self._fields.keys()) - set(fields_values.keys())
        result = {}
        for field_name in unset_fields:
            valid_types = self._fields[field_name].valid_types
            first_valid_type = valid_types[0]
            try:
                base_type = next(t for t in types_with_defaults
                                 if issubclass(first_valid_type, t))
            except StopIteration:
                raise UnsetFieldWithoutDefault(
                    "Field {} has type {} which has no default value.".format(field_name, first_valid_type)
                )
            else:
                default_value = base_type()
                result[field_name] = default_value
        return result

    @property
    def fields(self) -> dict:
        """Dict containing names of all fields as keys and their descriptions as values."""
        return self._fields

    @property
    def type(self) -> str:
        """
        Type of this message, string, used in network communications.

        Used by receiving end to resolve Message class. Should be unique for every OBCI message.
        """
        return self.__TYPE__

    def __repr__(self) -> str:
        """String representation."""
        return '<Message object, type_id: {}, sender: {}, payload: {}>'.format(self.type, self.sender, self._data_dict)

    @property
    def sender(self) -> str:
        """ID of the sender of this message."""
        return self._sender

    @sender.setter
    def sender(self, x: str):
        if isinstance(x, str):
            self._sender = x

    @property
    def subtype(self) -> str:
        """ID of the sender of this message."""
        return self.sender

    def serialize_data(self) -> bytes:
        """Serialize data of this message to bytes and return it."""
        return serializers.to_json(self.data_dict)

    def serialize(self) -> Tuple[bytes, bytes]:
        """Serialize this message to tuple of bytes to be sent to ZMQ."""
        data_bytes = self.serialize_data()
        return ('%s^%s^' % (self.type, self.subtype)).encode('utf-8'), data_bytes

    @classmethod
    def deserialize_data(cls, data: bytes) -> dict:
        """
        Deserialize message data from bytes.

        :return: A dictionary which could be unpacked into `__init__` of this message type.
        """
        try:
            return serializers.from_json(data)
        except JSONDecodeError:
            # when receiving Message without Fields
            # empty message should be deserialized to empty dict
            if len(cls._fields) > 0:
                raise
            else:
                return {}

    @classmethod
    def deserialize(cls, data: bytes, sender: str = None):
        """
        Deserialize whole message from data bytes.

        Will be invoked in `MessageMeta` message serializer, which takes care of network
        protocol and invokes this function with sender information and payload bytes.
        :return: Instance of this class.
        """
        data_dict = cls.deserialize_data(data)
        return cls(sender=sender, **data_dict)

    @property
    def data_dict(self) -> dict:
        """Full payload of this message, packed into dictionary."""
        return {i: getattr(self, i) for i in self._fields}

    def __eq__(self, other):
        return all(getattr(self, k) == getattr(other, k)
                   for k in self._fields)

    def send(self, socket):  # TODO: maybe split this to use only in experiment
        from braintech.obci.experiment.common.message import send_msg
        return send_msg(socket, self.serialize())
