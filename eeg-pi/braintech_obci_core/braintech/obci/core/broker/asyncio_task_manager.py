# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""
:class:`AsyncioTaskManager` class is used to manage a set of tasks.

Tasks are created using :meth:`create_task` method.

Examples:
    Can be used as context manager::

        with AsyncioTaskManager() as mgr:
            pass

    Or as async context manager::

        async with AsyncioTaskManager() as mgr:
            pass
"""
import asyncio
import concurrent.futures
import functools
import logging
import sys
import threading
from asyncio import CancelledError
from asyncio.tasks import Task
from functools import partial
from typing import Optional, Union, Callable, Any, Awaitable

from . import ObciException, OBCI_DEBUG

SHUTDOWN_TIMEOUT = 10


class MessageLoopRunningException(ObciException):
    """
    Exception raised when function is erroneously called outside of the message loop.

    Raised by :func:`ensure_not_inside_msg_loop` decorator used in
    :class:`AsyncioTaskManager` and its subclasses when function that must be
    called outside of the message loop was called from inside message loop.
    """


class ShuttingDownException(ObciException):
    """Raised when :class:`AsyncioTaskManager` cannot complete request because it is shutting down."""


def wrap_function_or_coroutinefunction(check_func, func):
    """
    Wrap given function in a function object.

    Return function object with ``__code__.co_flags & CO_COROUTINE`` if func is
    coroutine function, otherwise return ordinary function.
    :param check_func: function to be called before this wrap returns, taking AsyncioTaskManager as a single argument
    :param func: function to be wrapped into an object
    """
    if asyncio.iscoroutinefunction(func):
        @functools.wraps(func)
        async def _wrapper(self: 'AsyncioTaskManager', *args, **kwargs):
            check_func(self)
            return await func(self, *args, **kwargs)
    else:
        @functools.wraps(func)
        def _wrapper(self: 'AsyncioTaskManager', *args, **kwargs):
            check_func(self)
            return func(self, *args, **kwargs)
    return _wrapper


def ensure_not_inside_msg_loop(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorate functions/methods which must not be called outside of the message loop.

    Decorator used by :class:`AsyncioTaskManager` and its subclasses to
    annotate methods that must be called outside of the message loop.
    """

    def do_check(self):
        try:
            current_loop = asyncio.get_event_loop()
        except RuntimeError:
            pass
        else:
            if self._loop == current_loop and self._loop.is_running():
                raise MessageLoopRunningException('Function was called inside running message loop. '
                                                  'Probably you wanted to use the async version of called function.')

    return wrap_function_or_coroutinefunction(do_check, func)


class AsyncioTaskManager:
    """Manages a single asyncio loop and allows to create tasks executed by it."""

    @staticmethod
    def new_event_loop() -> asyncio.BaseEventLoop:
        """
        Create a new asyncio loop for :class:`AsyncioTaskManager` to manage.

        When :class:`AsyncioTaskManager` runs with :attr:`~AsyncioTaskManager.owns_asyncio_loop`
        set to ``True`` this function is called to create a new asyncio event loop.

        Default implementation calls :func:`asyncio.new_event_loop`.

        :return: event loop object
        :rtype: asyncio.BaseEventLoop
        """
        loop = asyncio.new_event_loop()
        if OBCI_DEBUG:
            loop.set_debug(True)
        return loop

    _thread_name = 'AsyncioTaskManager'
    _logger_name = 'AsyncioTaskManager'

    def __init__(self,
                 asyncio_loop: Optional[asyncio.BaseEventLoop] = None
                 ) -> None:
        """
        Create new ``AsyncioTaskManager`` object.

        :param asyncio_loop: existing message loop or ``None`` if new message loop should be created
        """
        assert asyncio_loop is None or isinstance(asyncio_loop, asyncio.BaseEventLoop)

        super().__init__()

        self._tasks = set()
        self._shutdown_lock = threading.Lock()
        self._tasks_lock = threading.Lock()
        self._exception = None
        self._finished = threading.Event()
        self._is_shutting_down = False  # type: bool
        if asyncio_loop is not None:
            self._owns_loop = False  # type: bool
            self._loop = asyncio_loop
            self.__thread = None
        else:
            self._owns_loop = True  # type: bool
            self._loop = self.new_event_loop()
            self.__thread = threading.Thread(target=self.__thread_func,
                                             name=self._thread_name)
            self.__thread.daemon = True
        self._logger = self._create_logger()
        if self.__thread:
            self.__thread.start()

    @property
    def is_shutting_down(self) -> bool:
        """bool: True if this :class:`AsyncioTaskManager` is shutting down."""
        return self._is_shutting_down

    @property
    def is_finished(self) -> bool:
        """bool: True if :class:`AsyncioTaskManager` is finished."""
        return self._finished.is_set()

    @property
    def owns_asyncio_loop(self) -> bool:
        """bool: True if owns asyncio message loop. Read-only.

        If this instance owns message loop, it will be closed and destroyed
        on :class:`AsyncioTaskManager`'s shutdown.
        """
        return self._owns_loop

    def _task_done_callback(self, task: asyncio.Task, critical: bool):
        with self._tasks_lock:
            try:
                self._tasks.remove(task)
            except IndexError:
                pass
        try:
            task.result()
        except asyncio.CancelledError:
            self._logger.debug('Coroutine cancelled: {}'.format(task._coro))
        except Exception as e:
            if critical:
                self._exception_in_critical_task(exc=e, coro=task._coro)
            else:
                self._exception_in_coroutine(exc=e, coro=task._coro)

    def _exception_in_coroutine(self, exc, coro):
        self._logger.error('Exception in coroutine: %s \n%s', coro, exc, exc_info=True)

    def _exception_in_critical_task(self, exc, coro):
        self._logger.critical('Exception in CRITICAL coroutine: %s \n%s', coro, exc, exc_info=True)
        self.create_task(self.panic(exc))

    def create_task(self,
                    coro: Awaitable[Any],
                    critical: bool = True,
                    ) -> Union[asyncio.Future, concurrent.futures.Future]:
        """
        Create a new task and return Future object.

        New task will be added to an internal tasks list. When task finishes or
        raises exception or is cancelled it will be automatically removed from
        that list. When :class:`AsyncioTaskManager` is asked to close it will cancel
        all tasks on that list.

        :param coro: awaitable object (e.g. coroutine)
        :param critical: True if created task should be critical - exception should cause PANIC and shutdown
        :rtype: Future

        .. note::
            Can be called from any thread or/and from any coroutine.
        """
        assert self._loop is not None

        if self.is_shutting_down:
            raise ShuttingDownException("is already shutting down")
        else:
            def _add_task(coro):
                task = self._loop.create_task(coro)
                with self._tasks_lock:
                    self._tasks.add(task)
                task_done_callback_crit = partial(self._task_done_callback, critical=critical)
                task.add_done_callback(task_done_callback_crit)
                return task

            try:
                current_loop = asyncio.get_event_loop()
            except RuntimeError:
                current_loop = None

            if current_loop == self._loop:
                return _add_task(coro)
            else:
                async def add_and_run_task(coro):
                    task = _add_task(coro)
                    return await task

                return asyncio.run_coroutine_threadsafe(add_and_run_task(coro), self._loop)

    @ensure_not_inside_msg_loop
    def shutdown(self, timeout: Optional[float] = SHUTDOWN_TIMEOUT, exc: Optional[Exception] = None) -> None:
        """
        Shut down this manager.

        Event loop is destroyed only if it has been created by the same :class:`AsyncioTaskManager` instance.

        Can be called from ANY thread, but NOT from event loop.
        It will block until all pending tasks are finished.
        Can be called multiple times.
        """
        with self._shutdown_lock:
            try:
                if not self.is_shutting_down:
                    self._logger.info("Shutting down %s", self)
                    if exc is not None:
                        coro = self.panic(exc)
                    else:
                        coro = self.async_shutdown()
                    asyncio.run_coroutine_threadsafe(coro, loop=self._loop).result(timeout)
            except (ShuttingDownException, CancelledError):
                pass
            except concurrent.futures.TimeoutError as ex:
                raise TimeoutError() from ex
            self._wait_until_finished(timeout)
        assert len(self._tasks) == 0, repr(self._tasks)

    async def panic(self, exc: Optional[Exception] = None) -> None:
        """
        Shut down this task manager (coroutine version).

        Can be called from coroutine running inside the message loop.
        This method implements human-friendly logging and prevents duplicate calling.
        Actual shutdown is implemented in async_shutdown coroutine, awaited by this method.
        """
        if exc is not None:
            self._exception = exc
            exc_info = sys.exc_info()
            exc_info = exc_info[0], exc, exc_info[2]
            self._logger.fatal('Shutting down with error %s', exc, exc_info=exc_info)
        else:
            self._exception = Exception("Finished by panic")
        await self.async_shutdown()

    def _notify_finished(self):
        if self._exception:
            self._logger.warning("Finished with exception")
        else:
            self._logger.info("Finished")
        self._finished.set()

    async def async_shutdown(self) -> None:
        """
        Shut down this task manager (coroutine version).

        Can be called from coroutine running inside the message loop.
        This method implements human-friendly logging and prevents duplicate calling.
        In order to customize shutdown process, override :meth:`_shutdown` for long tasks and :meth:`_cleanup`
        for final resource cleanup
        """
        if self.is_shutting_down:
            self._logger.warning('Is already shutting down')
        else:
            self._is_shutting_down = True
            assert self._is_shutting_down
            self._logger.debug("Async shutdown of %s", self)

            def _notify(name, ex):
                self._logger.exception(name)
                if self._exception is None:
                    self._exception = ex

            try:
                await self._shutting_down()
            except Exception as ex:
                _notify("Exception while shutting down", ex)
            await self.__cancel_all_tasks()
            try:
                self._cleanup()
                self._logger.debug("Cleanup done for peer %s", self)
            except Exception as ex:
                _notify("Exception during cleanup", ex)
            if self.owns_asyncio_loop:
                self._loop.call_soon_threadsafe(self._loop.stop)
            else:
                self._notify_finished()
            self._logger.debug("Async shutdown of %s finished", self)
            # It is the end of this peer. Doing anything else after async_shutdown is illegal, so stop further execution
            raise CancelledError()

    def _finished_result(self):
        if not self._finished.is_set():
            raise TimeoutError()
        if self._exception:
            raise self._exception
        return True

    @ensure_not_inside_msg_loop
    def _wait_until_finished(self, timeout: Optional[float] = None) -> None:
        """Wait until all owned tasks are finished."""
        self._finished.wait(timeout)
        return self._finished_result()

    async def wait_until_finished_async(self, timeout: Optional[float] = None) -> None:
        """Can be used only from task not owned by this :class:`AsyncioTaskManager`."""
        await self._loop.run_in_executor(None, self._finished.wait, timeout)
        return self._finished_result()

    def _create_logger(self):
        """Can be reimplemented if you want to use custom logger."""
        return logging.getLogger(self._logger_name)

    async def _shutting_down(self):
        """
        Can be reimplemented to perform extra shutting down tasks, which might take long before freeing up resources.

        .. note::
            Always remember to call ``super()._shutting_down()`` when overloading this function.
        """
        pass

    def _cleanup(self) -> None:
        """
        Can be reimplemented to perform extra cleanup - free all the resources.

        .. note::
            Always remember to call ``super()._cleanup()`` when overloading this function.
        """
        pass

    async def __cancel_all_tasks(self) -> None:
        """Cancel all pending tasks and wait for them to finish."""
        try:
            other_tasks = [t for t in self._tasks if t != Task.current_task()]
            for task in other_tasks:
                task.cancel()
            for task in other_tasks:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        finally:
            self._logger.debug('cancel all tasks finished for peer %s', self)

    def __thread_func(self) -> None:
        """
        Entry point of message loop thread.

        Runs new message loop in a new thread when
        :attr:`owns_asyncio_loop` is True.
        """
        assert self._owns_loop and self._loop is not None and self.__thread is not None
        try:
            self._logger.debug("Setting message loop for thread '%s' (%s).", self.__thread.name, self.__thread.ident)
            asyncio.set_event_loop(self._loop)
            self._logger.debug('Starting message loop...')
            self._loop.run_forever()
        except Exception as ex:
            self._logger.exception('Exception in asyncio event loop:')
            self._loop.run_until_complete(asyncio.ensure_future(self.panic(ex)))
        finally:
            self._loop.close()
            self._logger.debug('Message loop closed.')
            self._notify_finished()

    async def run_long_operation(self, operation, *args):
        """
        Run operation in separate thread.

        Wait for operation to finish and return it results.
        """
        return await self._loop.run_in_executor(None, operation, *args)

    def __del__(self):
        """
        Called when the instance is about to be destroyed.

        .. note::
            When running with ``self._owns_loop == True``
            this function requires ``self.__thread.daemon == True``,
            otherwise thread will not end properly when program ends
            and will still hold a reference to this object and this
            function won't be called by Python.

        .. note::
            Python documentation for :meth:`object.__del__` method says that:

                It is not guaranteed that ``__del__()`` methods are called for
                objects that still exist when the interpreter exits.

            See: https://docs.python.org/3/reference/datamodel.html#object.__del__

            To read even more extensive summary about :meth:`object.__del__` method see:
            http://www.andy-pearce.com/blog/posts/2013/Apr/python-destructor-drawbacks/

            To sum up:

            1. ``__del__`` will be called even when ``__init__`` fails (raises an exception),
               so existence of class attributes (``self.*``) is not guaranteed
            2. ``__del__`` can be called for objects that do not exist when the
               interpreter exits
        """
        try:
            self.shutdown()
        except AttributeError:
            pass

    def __enter__(self) -> 'AsyncioTaskManager':
        """Provide this task manager as a context."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Shut down this task manager when the context is left."""
        self.shutdown()

    async def __aenter__(self) -> 'AsyncioTaskManager':
        """Provide this task manager as an asyncio context."""
        assert self._loop is not None
        assert asyncio.get_event_loop() == self._loop
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Shut down this task manager when the asyncio context is left."""
        await self.async_shutdown()


__all__ = (
    'AsyncioTaskManager',
    'ensure_not_inside_msg_loop',
    'MessageLoopRunningException',
    'ShuttingDownException'
)
