# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Provides a BasePeer, a base class for all peers sending and receiving broker messages."""

import abc
import asyncio
import concurrent.futures
import os.path
import queue
import threading
import uuid
from concurrent.futures import CancelledError
from enum import Enum
from typing import Any, Awaitable, Callable, Optional, Union, Tuple, List

import zmq
import zmq.asyncio

from braintech.obci.core.broker import messages
from braintech.obci.core.broker.messages import base as base_messages
from braintech.obci.core.utils import is_posix
from . import ObciException
from .asyncio_task_manager import ShuttingDownException, wrap_function_or_coroutinefunction
from .message_handler_mixin import (MessageHandlerMixin,
                                    HandlerNotRegisteredException,
                                    NotInitializedException,
                                    ensure_connected,
                                    subscribe_message_handler,
                                    )
from .message_statistics import MsgPerfStats
from .url_utils_mixin import UrlUtilsMixin
from .zmq_asyncio_task_manager import ZmqAsyncioTaskManager
from braintech.obci.core.utils.zmq import TimeoutException

__all__ = (
    'BasePeer',
    # decorator
    'ensure_inside_msg_loop',
    # exceptions
    'HandlerNotRegisteredException',
    'NotInitializedException',
)

SHUTDOWN_SEND_MESSAGES_TIMEOUT = 20  # seconds


class PeerCapabilities:
    """Represents peer capabilities."""

    IPC = b"I"
    INPROC = b"N"

    def __init__(self, capabilities: bytes = b''):
        """
        It creates peer capabilities.

        :param capabilities: encoded capabilities of this peer
        """
        self.capabilities = set(capabilities.split())

    def add(self, cap: bytes):
        """
        Add peer capability.

        :param cap: capability id
        """
        assert len(cap) == 1
        self.capabilities.add(cap)

    def has_ipc(self) -> bool:
        """bool: True if peer can communicate vie IPC."""
        return self.IPC in self.capabilities

    def serialize(self) -> bytes:
        """bytes: serialized version of capabilities ready to be sent by peer."""
        return b''.join(self.capabilities)


class WrongThreadException(ObciException):
    """Raised when function was called from wrong thread (not from asyncio message loop thread)."""


def ensure_inside_msg_loop(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator for methods that must be called from the message loop.

    This decorator is used by :class:`BasePeer` and its subclasses to
    annotate methods must be called from their internal asyncio message loop thread.
    """

    def do_check(self):
        if self._loop != asyncio.get_event_loop():
            raise WrongThreadException('Function was called from wrong thread. '
                                       'This function must be called from asyncio message loop thread.')

    return wrap_function_or_coroutinefunction(do_check, func)


class PeerState(Enum):
    initializing = 1
    connected = 2
    ready = 4 | connected
    running = 8 | ready
    shutting_down = 16
    shutting_down_connected = shutting_down | connected
    finished = 32

    def _is_initializing(self):
        return self.value == self.initializing.value

    def _is_connected(self):
        return (self.value & self.connected.value) == self.connected.value

    def _is_ready(self):
        return (self.value & self.ready.value) == self.ready.value

    def _is_running(self):
        return self.value == self.running.value

    def _is_shutting_down(self):
        return self.value >= self.shutting_down.value

    def _is_finished(self):
        return self.value == self.finished.value


class BasePeer(ZmqAsyncioTaskManager,
               MessageHandlerMixin,
               UrlUtilsMixin,
               metaclass=abc.ABCMeta):
    """
    Base peer superclass.

    Both :class:`~obci.core.peer.Peer` and :class:`obci.core.broker.Broker` derive from this class.
    """

    _VALID_STATE_TRANSITIONS_ = {
        PeerState.initializing: (
            PeerState.connected,
            PeerState.shutting_down
        ),

        PeerState.connected: (
            PeerState.ready,
            PeerState.shutting_down_connected
        ),

        PeerState.ready: (
            PeerState.running,
            PeerState.shutting_down_connected
        ),

        PeerState.running: (
            PeerState.ready,
            PeerState.shutting_down_connected
        ),
        PeerState.shutting_down: (
            PeerState.finished,
        ),
        PeerState.shutting_down_connected: (
            PeerState.finished,
        )
    }

    is_essential = True

    def __init__(self,
                 peer_id: Optional[str] = None,
                 peer_name: Optional[str] = None,
                 asyncio_loop: Optional[zmq.asyncio.ZMQEventLoop] = None,
                 zmq_context: Optional[zmq.asyncio.Context] = None,
                 zmq_io_threads: int = 1,
                 hwm: int = 1000) -> None:
        """
        Create a new peer.

        Peer will be started automatically.

        :param peer_name: human-readable peer name (used for logging and thread name)
        :param peer_id: globally unique identifier
        :param asyncio_loop: existing ZMQ asyncio message loop or ``None`` if loop is requested
        :param zmq_context: existing ZMQ asyncio context or ``None`` if new context is requested
        :param zmq_io_threads: number of ZMQ I/O threads
        :param hwm: ZMQ high water mark
        """
        self._previous_state = None
        self._current_state = PeerState.initializing

        peer_id = str(uuid.uuid4()) if peer_id is None else str(peer_id)
        self._id = peer_id
        if peer_name is None:
            peer_name = '{}.{}'.format(type(self).__qualname__.replace('Peer', ''), peer_id)

        self._thread_name = peer_name
        self._logger_name = 'peer.%s' % peer_name
        # queue of SerializedMessage objects
        # (messages can be unqueued before broker/msgproxy connection is established)
        self._msg_queue = queue.Queue()
        self._msg_queue_lock = threading.RLock()
        self._queuing_counter = 0

        super().__init__(asyncio_loop, zmq_context, zmq_io_threads)
        self._fill_message_handlers()
        self._hwm = hwm

        self._pub = None  # PUB socket for sending messages to broker XSUB
        self._sub = None  # SUB socket for receiving messages from broker's XPUB
        self._rep = None  # synchronous requests from other peers

        # logs verbosity
        self._log_messages = False  # just too much

        # message statistics
        stats_interval = 4.0

        # async send statistics
        self._calc_send_stats = False
        self._send_stats = MsgPerfStats(stats_interval, 'SEND')

        # async receive statistics
        self._calc_recv_stats = False
        self._recv_stats = MsgPerfStats(stats_interval, 'RECV')

        # self._initialize coroutine can start IMMEDIATELY after this call.
        # It is not guaranteed that __init__ function will finish before
        # code from self._initialize is executed.
        self.create_task(self._initialize())

    @property
    def _is_shutting_down(self):
        # override this property from AsyncioTaskManager
        return self._state._is_shutting_down()

    @_is_shutting_down.setter
    def _is_shutting_down(self, value):
        if value is True:
            self._state = PeerState.shutting_down_connected if self.is_connected else PeerState.shutting_down

    def _notify_finished(self):
        self._state = PeerState.finished
        super()._notify_finished()

    @property
    def _state(self) -> PeerState:
        """Return current peer state."""
        return self._current_state

    @_state.setter
    def _state(self, value: PeerState) -> None:
        """Set current peer state.

        Also checks if state transition is a valid one and if value is instance of PeerState.
        In addition identity transitions are valid.
        """
        if self.is_shutting_down and value != PeerState.finished:
            # this can happen when shutdown is before full initialization
            raise CancelledError()
        assert isinstance(value, PeerState)

        err_msg = '{} transition from state: {} to state: {} is not allowed'.format(
            repr(self), self._current_state, value
        )
        assert value in self._VALID_STATE_TRANSITIONS_[self._current_state] + (value,), err_msg
        self._previous_state, self._current_state = self._current_state, value
        if self._previous_state != value:
            self._logger.info("Changed state from %s to %s", self._previous_state, value)

    @property
    def id(self) -> str:
        """
        str: Unique identification string.

        Read only property. Can be set only when creating a new peer instance.
        """
        return self._id

    @property
    def is_initializing(self) -> bool:
        """bool: True if peer is connecting to broker and not yet ready for sending messages"""
        return self._state._is_initializing()

    @property
    def is_connected(self) -> bool:
        """bool: True if peer is connected, and therefore message sending functions can be used."""
        return self._state._is_connected()

    @property
    def is_ready(self) -> bool:
        """bool: True if peer is ready."""
        return self._state._is_ready()

    @property
    def is_running(self) -> bool:
        """bool: True if peer is running."""
        return self._state._is_running()

    @property
    def is_shutting_down(self) -> bool:
        """bool: True if peer is shutting down."""
        return self._state._is_shutting_down()

    @property
    def capabilities(self) -> PeerCapabilities:
        """PeerCapabilities: capabilities of this peer."""
        caps = PeerCapabilities()
        if is_posix():  # ZMQ IPC is available in UNIX based oses
            caps.add(PeerCapabilities.IPC)
        return caps

    async def ask_peer(self, urls: Union[List[str], str],
                       msg: messages.BaseMessage,
                       timeout: float = 5.0) -> messages.BaseMessage:
        """
        Send message to specified peer and return answer.

        :param urls: peer's REP socket URL, or list of REP urls
        :param msg: message object to send, if it doesn't have sender param set, it will be set automatically
        :param timeout: timeout in seconds
        :return: response message
        """
        if self._log_messages:
            self._logger.debug("sending sync message to '{}': type '{}', subtype '{}'"
                               .format(urls, msg.type, msg.subtype))
        req = self._ctx.socket(zmq.REQ)
        req.setsockopt(zmq.RCVTIMEO, int(1000 * timeout))

        if isinstance(urls, str):
            urls = [urls, ]
        for uri in urls:
            req.connect(uri)
        if not msg.sender:
            msg.sender = self.id
        try:
            await req.send_multipart(msg.serialize())
            response = await req.recv_multipart()
        except zmq.Again:
            raise TimeoutException()
        finally:
            req.close(linger=0)

        reply = messages.deserialize(response)
        return reply

    def send_message(self,
                     msg_or_type: Union[messages.BaseMessage, str],
                     msg_data: Any = None) -> None:
        """
        Send broadcast message.

        If ``msg_or_type`` is a string new message object will be constructed using
        ``Message(msg_or_type, self.id, msg_data)`` else it is assumed to be an
        instance of :class:`Message` object.

        Can be used before peer finished initialization, but not after or during peer shutdown.

        :param msg_or_type: message object to send, or message type to create,
          if it doesn't have sender param set, it will be set automatically
        :param msg_data: Data dict to send in message
        :raises ShuttingDownException: when peer is shutting down and cannot enqueue more messages
        """
        if isinstance(msg_or_type, messages.BaseMessage):
            msg = msg_or_type
        else:
            cls = base_messages.MessageMeta.get_class_from_type(msg_or_type)
            msg = cls(**msg_data)

        try:
            inside_own_loop = asyncio.get_event_loop() == self._loop
        except RuntimeError:
            inside_own_loop = False
        if not msg.sender:
            msg.sender = self.id
        serialized = msg.serialize()

        def queue():
            with self._msg_queue_lock:
                if self._msg_queue is None:
                    raise ShuttingDownException('Peer is shutting down cannot enqueue more messages')
                self._msg_queue.put_nowait(serialized)
                self._queuing_counter -= 1

        with self._msg_queue_lock:
            self._queuing_counter += 1
        if inside_own_loop:
            queue()
        else:
            try:
                self._loop.call_soon_threadsafe(queue)
            except RuntimeError as ex:
                raise ShuttingDownException('Peer is shutting down cannot enqueue more messages') from ex

    async def _send_pending_messages(self):
        try:
            while not self._msg_queue.empty():
                await self.__send_message_content(self._msg_queue.get_nowait())
        except AttributeError:
            self._logger.warning("Could not send all messages from the queue - connection closed")

    @abc.abstractmethod
    async def _establish_connections(self):
        """Must be reimplemented to establish required connections."""
        pass

    @ensure_connected
    async def _connections_established(self) -> None:
        """Executed when all message sending mechanisms are available for use."""
        self.create_task(self._receive_sync_messages())
        self.create_task(self._receive_async_messages())
        self.create_task(self._message_sender())
        self.create_task(self._log_mem_growth(), critical=False)
        await super()._connections_established()

    async def _log_mem_growth(self):
        while True:
            await asyncio.sleep(10.0)  # required
            if not os.path.isfile(os.path.join(os.path.expanduser('~'),
                                               '.obci',
                                               'log_mem_growth')):
                continue
            try:
                import io
                import objgraph
                with io.StringIO() as output:
                    objgraph.show_growth(file=output)
                    msg = output.getvalue()
                    msg = "---\nMemory growth for '{}' '{}'\n{}\n---" \
                        .format(self._logger_name, self._thread_name, msg)
                    print(msg)
                    self._logger.info(msg)
            except Exception as ex:
                self._logger.info('_log_mem_growth error: {}'.format(ex))

    @ensure_connected
    async def _message_sender(self):
        with self._msg_queue_lock:
            aio_msg_queue = asyncio.Queue(loop=self._loop)
            try:
                while True:
                    aio_msg_queue.put_nowait(self._msg_queue.get_nowait())
            except queue.Empty:
                pass
            finally:
                self._msg_queue = aio_msg_queue
        try:
            while True:
                serialized = await self._msg_queue.get()
                try:
                    await self.__send_message_content(serialized)
                except Exception:
                    self._logger.error('_message_sender: Exception while sending message', exc_info=True)
                finally:
                    self._msg_queue.task_done()
        except CancelledError:
            await self._send_pending_messages()
            self._msg_queue = None

    @ensure_connected
    async def _receive_async_messages(self) -> None:
        async def async_handler(msg):
            if self._calc_recv_stats:
                self._recv_stats.msg(msg)

            msg = messages.deserialize(msg)

            if self._log_messages:
                self._log_message(msg, 'async')
            response = await self.handle_message(msg)
            if response is not None:
                self.send_message(response)

        await self._receive_messages_helper(self._sub, async_handler)

    @ensure_connected
    async def _receive_sync_messages(self) -> None:
        async def sync_handler(msg):
            response = None
            try:

                msg = messages.deserialize(msg)

                if self._log_messages:
                    self._log_message(msg, 'sync')
                response_msg = await self.handle_message(msg)
                if not isinstance(response_msg, messages.BaseMessage):
                    raise ObciException("Message handler was expected to return 'BaseMessage' object. "
                                        "Got '{}' instead.".format(type(response_msg)))
                response = response_msg.serialize()
            except Exception as ex:
                response = messages.InternalError(sender=self.id,
                                                  data=str(ex)).serialize()
                raise
            finally:
                if response is None:
                    response = messages.InternalError(
                        sender=self.id,
                        data='_receive_sync_messages: Internal integrity error.',
                    ).serialize()
                await self._rep.send_multipart(response)

        await self._receive_messages_helper(self._rep, sync_handler)

    @ensure_connected
    @subscribe_message_handler(messages.PanicMsg)
    async def _handle_panic(self, msg: messages.PanicMsg):
        self._logger.warning('%s is panicking, got PANIC message: %s', msg.sender, msg.data)

    @ensure_connected
    async def _receive_messages_helper(self,
                                       socket: zmq.asyncio.Socket,
                                       handler: Callable[[], Awaitable[None]]
                                       ) -> None:
        """
        Utility coroutine for receiving ZMQ messages in message loop.

        This coroutine is used in two concurrent polling loops are run (for SUB and REP)
        to avoid one message type processing blocking another.
        """
        socket.setsockopt(zmq.RCVTIMEO, 100)
        while True:
            try:
                msg = await socket.recv_multipart()
                if msg:
                    await handler(msg)
            except ShuttingDownException:
                break
            except concurrent.futures.CancelledError:
                break
            except zmq.Again:
                continue
            except Exception as ex:
                self._logger.exception("Uncaught exception in message handler in peer '%s'", self.id)
                if self._handle_message_handler_exception(ex):
                    await self.panic(ex)
                    break

    def _handle_message_handler_exception(self, ex: Exception) -> bool:
        """
        Called when exception in message handler occurred.

        :param ex: exception from message handler
        :return: True if peer should shutdown, False if continue
        """
        return True

    @ensure_connected
    async def _send_message(self, msg: messages.BaseMessage):
        """
        Serialize and send message immediately, skipping the message queue.

        Should be used only after communication has been established.
        :param msg: Message to send
        """
        if self._log_messages:
            self._logger.debug("sending async message: type '{}', subtype '{}'"
                               .format(msg.type, msg.subtype))
        if not msg.sender:
            msg.sender = self.id
        content = msg.serialize()
        await self.__send_message_content(content)

    async def __send_message_content(self, content: Tuple[bytes, bytes]):
        """
        Send a serialized message content immediately, skipping the message queue.

        Should be used ony after communication is established
        :param content: (bytes, bytes) tuple to send
        """
        if self._calc_send_stats:
            self._send_stats.msg(content)
        await self._pub.send_multipart(content, copy=False)

    def _cleanup(self) -> None:
        """
        Close ZMQ sockets.

        .. note::
            Always remember to call ``super()._cleanup()`` when overloading this function.
        """
        for socket in [self._pub, self._sub, self._rep]:
            if socket is None:
                continue
            socket.close(linger=0)
            try:
                self._loop._selector._zmq_poller.unregister(socket)
            except (KeyError, AttributeError):
                pass
        self._pub = None
        self._sub = None
        self._rep = None
        self._logger.debug("Sockets closed for peer %s", self)
        super()._cleanup()

    async def send_panic(self, msg: Optional[str] = None):
        """Send PANIC message(everything is on fire and should stop working)."""
        msg = messages.PanicMsg(data=msg, was_essential=self.is_essential)
        await self._send_message(msg)

    async def _initialize(self) -> None:
        try:
            self._logger.debug("Peer '%s': creating sockets... ", self.id)
            self._pub = self._ctx.socket(zmq.PUB)
            self._sub = self._ctx.socket(zmq.SUB)
            self._rep = self._ctx.socket(zmq.REP)
            for socket in [self._pub, self._sub, self._rep]:
                socket.set_hwm(self._hwm)
                socket.set(zmq.LINGER, 0)

            self._logger.debug("Peer '%s': running _initialize_connections... ", self.id)
            await self._establish_connections()
            self._state = PeerState.connected

            self._logger.debug("Peer '%s': running _connections_established... ", self.id)
            await self._connections_established()
            await self._initialized()
            self._logger.debug("Peer '%s': initialization finished", self.id)
        except (ShuttingDownException, CancelledError):
            raise
        except Exception as exc:
            msg = 'Peers initialization failed. ({})'.format(self.id)
            self._logger.exception(msg)
            await self.panic(exc)

    async def panic(self, exc: Optional[Exception] = None):
        """Change self state to panic and then shutdown with error message.

        Also send panic message to other peers if fully initialized.
        """
        if self.is_connected:
            await self.send_panic(str(exc))
        await super().panic(exc)

    async def _initialized(self):
        self._state = PeerState.ready

    def _log_message(self, msg: messages.BaseMessage, name: str):
        if msg.type != 'log_msg':
            self._logger.debug("received message: {}, version: {}'"
                               .format(msg, name))

    def __str__(self):
        """Human-readable peer description, consisting of its class, id and object ID."""
        return "{}-{}({})".format(type(self).__name__, self.id, id(self))

    def __repr__(self):
        """Return <Peer class, id and object id>."""
        return "<%s>" % self
