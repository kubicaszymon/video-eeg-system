# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""This module implements some Mixin classes for common message handling interface."""
import asyncio
import concurrent.futures
import inspect
import threading
from typing import Any, Optional, Callable, Union, Awaitable, Iterable

from braintech.obci.core.broker import messages
from . import ObciException
from .asyncio_task_manager import wrap_function_or_coroutinefunction

__all__ = (
    'MessageHandlerMixin',
    # decorators
    'ensure_connected',
    'register_message_handler',
    'subscribe_message_handler',
    # exceptions
    'NotInitializedException',
    'NotRegisteredException',
    'AlreadyRegisteredException',
    'HandlerNotRegisteredException',
    'AlreadyRegisteredException',
)

HandlerType = Union[Callable[['BasePeer', messages.BaseMessage], Optional[messages.BaseMessage]],
                    Callable[['BasePeer', messages.BaseMessage], Awaitable[Optional[messages.BaseMessage]]]]
"""Message handler: returns :class:`~obci.core.messages.Message` or ``None``."""

QueryHandler = Union[Callable[[messages.BaseMessage], messages.BaseMessage],
                     Callable[[messages.BaseMessage], Awaitable[messages.BaseMessage]]]
"""Query handler: always returns :class:`~obci.core.messages.Message`."""

QueryDataType = Union[dict, str, int, float, type(None), Iterable['QueryDataType']]
"""JOSN serializable data type."""


def ensure_connected(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator for methods that must be called after the connections have been established.

    This decorator is used by :class:`Peer` and its subclasses to annotate methods
    requiring established connection.
    """

    def do_check(self):
        if not self.is_connected:
            raise NotInitializedException('Peer is not connected yet.')

    return wrap_function_or_coroutinefunction(do_check, func)


def _normalise_register_args(args):
    norm = []
    for arg in args:
        if isinstance(arg, str):
            norm.append(arg)
        else:
            norm.append(arg.type)
    return norm


def register_message_handler(*args):
    """
    Decorator used to mark a method to register.

    :param args: list of messages to register (BaseMessage class or string - network identifier)
    :return: A wrapper function to register
    """

    def register_handler(f):
        f.__registered__ = True
        f.__message_type__ = set(_normalise_register_args(args))
        return f

    return register_handler


def subscribe_message_handler(*args):
    """
    Decorator used to mark a method to subscribe.

    :param args: list of message classes to subscribe
    :return: A wrapper function to subscribe.
    """

    def subscribe_handler(f):
        f.__subscribed__ = True
        f.__message_type__ = set(_normalise_register_args(args))
        return f

    return subscribe_handler


class NotInitializedException(ObciException):
    """Raised when function requires peer to be in initialized state."""


class NotRegisteredException(ObciException):
    """Exception raised when message type is not register."""

    def __int__(self,
                msg_type: str,
                registered_handlers: Iterable[str],
                extra_msg: Optional[str] = None,
                **kwargs) -> None:
        """
        Exception raised for not registered messages.

        :param msg_type: message type
        :param registered_handlers: a list of currently registered handlers
        """
        msg = ("No handler was registered for message type '{}'. Registered handlers: [{}].{}"
               .format(msg_type,
                       ', '.join(registered_handlers),
                       '' if extra_msg is None else '\n Additional information: {}'.format(extra_msg)))
        super().__init__(msg, **kwargs)


class HandlerNotRegisteredException(ObciException):
    """Raised by :meth:`BasePeer.subscribe` when no message handler is registered for specified message type."""


class AlreadyRegisteredException(ObciException):
    """Exception raised when message type is already registered."""

    pass


class MessageHandlerMixin:
    """An implementation of common message handling interface used by Peer and Broker classes."""

    def __init__(self) -> None:
        """When Peer and Broker will be merged this will be in BasicPeer."""
        self._message_handlers = {}  # type: Dict[str, HandlerType]
        self._message_handlers_lock = threading.RLock()
        super().__init__()

    def _get_message_handlers(self):
        handlers = []
        for field_name in dir(self.__class__):
            try:
                field = getattr(self.__class__, field_name)
            except Exception:
                continue
            if hasattr(field, '__message_type__'):
                handlers.append(getattr(self, field_name))
        return handlers

    def _fill_message_handlers(self):

        for handler in self._get_message_handlers():
            if hasattr(handler, '__registered__'):
                for message_type in handler.__message_type__:
                    with self._message_handlers_lock:
                        if message_type in self._message_handlers:
                            raise AlreadyRegisteredException("Handler for message type '{}' is already registered."
                                                             .format(message_type))
                        else:

                            self._message_handlers[message_type] = handler
                            self._logger.debug('register_message_handler for %s', message_type)

    @ensure_connected
    async def _connections_established(self) -> None:
        """Executed when all message sending mechanisms are available for use."""
        self._subscribe_message_handlers()

    @ensure_connected
    def _subscribe_message_handlers(self):

        for handler in self._get_message_handlers():
            if hasattr(handler, '__subscribed__'):
                for message_type in handler.__message_type__:
                    self.register_message_handler(message_type, handler)
                    self.subscribe(message_type)
                    self._logger.debug('%s subscribes for message %s' % (self, message_type))

    def register_message_handler(self, msg_type: Union[str, messages.BaseMessage],
                                 handler: HandlerType) -> None:
        """
        Register ``handler`` function to be called when message with ``msg_type`` arrives.

        :param msg_type: Message type string or class
        :param handler: Function called when new message arrives.
        :raises AlreadyRegisteredException: if handler for ``msg_type`` is already registered
        """
        if not isinstance(msg_type, str):
            msg_type = msg_type.type
        self._logger.debug('register_message_handler for %s', msg_type)
        with self._message_handlers_lock:
            if msg_type in self._message_handlers:
                raise AlreadyRegisteredException("Handler for message type '{}' is already registered."
                                                 .format(msg_type))
            self._message_handlers[msg_type] = handler

    @ensure_connected
    def subscribe_for_all_msg_subtype(self, msg_type: Union[str, messages.BaseMessage], handler: QueryHandler) -> None:
        """
        Register and subscribe messages with ``msg_type`` message type for all ``msg_subtype``.

        :param msg_type:
        :param handler:
        """
        self.register_message_handler(msg_type, handler)
        self.subscribe(msg_type)

    @ensure_connected
    def subscribe_for_specific_msg_subtype(self: str, msg_type, msg_subtype: str, handler: QueryHandler) -> None:
        """
        Register and subscribe messages with ``msg_type`` message type just for specified ``msg_subtype``.

        :param msg_type:
        :param msg_subtype:
        :param handler:
        """
        self.register_message_handler(msg_type, handler)
        self.subscribe(msg_type, msg_subtype)

    @ensure_connected
    def subscribe(self, msg_type: Union[str, messages.BaseMessage], msg_subtype: Optional[str] = None) -> None:
        """
        Subscribe for messages with ``msg_type`` message type.

        Peer must be initialized to use this function.

        :param msg_type:
        :param msg_subtype:
        """
        if not isinstance(msg_type, str):
            msg_type = msg_type.type

        def subscribe_impl(fut=None):
            try:
                with self._message_handlers_lock:
                    if msg_type not in self._message_handlers:
                        raise HandlerNotRegisteredException("Message handler for '{}' is not registered"
                                                            .format(msg_type))
                if self._sub is not None:
                    self._sub.subscribe(messages.BaseMessage.get_filter_bytes(msg_type, msg_subtype))
            except Exception as ex:
                if fut is not None:
                    fut.set_exception(ex)
            else:
                if fut is not None:
                    fut.set_result(None)

        if asyncio.get_event_loop() == self._loop:
            subscribe_impl()
        else:
            future = concurrent.futures.Future()
            self._loop.call_soon_threadsafe(subscribe_impl, future)
            future.result()

    def unregister_message_handler(self, msg_type: Union[str, messages.BaseMessage]) -> None:
        """
        Unregister previously registered message handler.

        :param msg_type: Message type
        :raises NotRegisteredException: if handler for ``msg_type`` was not registered
        """
        if not isinstance(msg_type, str):
            msg_type = msg_type.type
        self._logger.debug('unregister_message_handler for %s', msg_type)
        with self._message_handlers_lock:
            if msg_type not in self._message_handlers:
                raise NotRegisteredException(msg_type, self._message_handlers.keys())
            del self._message_handlers[msg_type]

    def unsubscribe_message_handler(self, msg_type: Union[str, messages.BaseMessage]) -> None:
        """
        Unsubscribe from message and unregister previously registered message handler.

        :param msg_type: Message type
        :raises NotRegisteredException: if handler for ``msg_type`` was not registered
        """
        self.unsubscribe(msg_type)
        self.unregister_message_handler(msg_type)

    @ensure_connected
    def unsubscribe(self, msg_type: Union[str, messages.BaseMessage], msg_subtype: Optional[str] = None) -> None:
        """
        Unsubscribe for messages with ``msg_type`` message type.

        Peer must be initialized to use this function.

        :param msg_type:
        :param msg_subtype:
        """
        if not isinstance(msg_type, str):
            msg_type = msg_type.type

        def unsubscribe_impl(fut=None):
            try:
                if self._sub is not None:
                    self._sub.unsubscribe(messages.BaseMessage.get_filter_bytes(msg_type, msg_subtype))
            except Exception as ex:
                if fut is not None:
                    fut.set_exception(ex)
            else:
                if fut is not None:
                    fut.set_result(None)

        if asyncio.get_event_loop() == self._loop:
            unsubscribe_impl()
        else:
            future = concurrent.futures.Future()
            self._loop.call_soon_threadsafe(unsubscribe_impl, future)
            future.result()

    async def handle_message(self, msg: messages.BaseMessage) -> Optional[messages.BaseMessage]:
        """
        Called by message dispatching loop when new message arrives.

        :param msg: message to handle
        :return: response message or ``None``
        :raises NotRegisteredException: if handler for ``msg_type`` is not registered
        """
        handler = None
        with self._message_handlers_lock:
            if msg.type not in self._message_handlers:
                extra_info = 'Message subtype: {}'.format(msg.subtype)
                raise NotRegisteredException(msg.type,
                                             self._message_handlers.keys(),
                                             extra_info)
            handler = self._message_handlers[msg.type]

        if handler is not None:
            response = handler(msg)
            if inspect.isawaitable(response):
                return await response
            else:
                return response
