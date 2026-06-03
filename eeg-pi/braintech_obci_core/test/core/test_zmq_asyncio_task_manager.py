# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import asyncio
import threading
import time

import pytest

from braintech.obci.core.broker.zmq_asyncio_task_manager import ZmqAsyncioTaskManager
from braintech.obci.core.broker.asyncio_task_manager import AsyncioTaskManager

WAIT_FOR_TASKS_DELAY = 0.5  # seconds
UNDER_TIMEOUT_DELAY = 0.1  # seconds
OVER_TIMEOUT_DELAY = 10.0  # seconds


class ZmqAsyncioTaskManagerWithName(ZmqAsyncioTaskManager):

    def __init__(self, *args, thread_name, **kwargs):
        self._thread_name = thread_name
        super().__init__(*args, **kwargs)


async def task1():
    thread = threading.current_thread()
    print("task 1 - '{}' ({})".format(thread.name, thread.ident))
    return 1


async def task2(event):
    global UNDER_TIMEOUT_DELAY
    await asyncio.sleep(UNDER_TIMEOUT_DELAY)
    event.set()
    thread = threading.current_thread()
    print("task 2 - '{}' ({})".format(thread.name, thread.ident))
    return 2


async def task3():
    global OVER_TIMEOUT_DELAY
    await asyncio.sleep(OVER_TIMEOUT_DELAY)
    thread = threading.current_thread()
    print("task 3 - '{}' ({})".format(thread.name, thread.ident))
    print('task3', time.time())
    return 3


def all_mgr_threads_finished():
    return not any('Mgr_' in t.name for t in threading.enumerate())


def context_mgr_helper(iterations, force_shutdown_times):
    global WAIT_FOR_TASKS_DELAY
    for i in range(iterations):
        with ZmqAsyncioTaskManagerWithName(thread_name='Mgr_{}'.format(i)) as mgr:
            event = threading.Event()
            future1 = mgr.create_task(task1())
            future2 = mgr.create_task(task2(event))
            future3 = mgr.create_task(task3())
            event.wait(3)
            for _ in range(force_shutdown_times):
                mgr.shutdown()
                assert len(mgr._tasks) == 0
        assert future1.result() is 1
        assert future2.result() is 2
        with pytest.raises(asyncio.CancelledError):
            future3.result()
        assert all_mgr_threads_finished()


def test_context_manager():
    context_mgr_helper(iterations=1, force_shutdown_times=0)
    context_mgr_helper(iterations=1, force_shutdown_times=0)
    context_mgr_helper(iterations=5, force_shutdown_times=1)
    context_mgr_helper(iterations=5, force_shutdown_times=1)
    context_mgr_helper(iterations=1, force_shutdown_times=10)
    context_mgr_helper(iterations=1, force_shutdown_times=10)
    context_mgr_helper(iterations=5, force_shutdown_times=10)
    context_mgr_helper(iterations=5, force_shutdown_times=10)


def shutdown_helper(force_shutdown_times):
    global WAIT_FOR_TASKS_DELAY

    mgr = ZmqAsyncioTaskManagerWithName(thread_name='Mgr_X')
    event = threading.Event()
    future1 = mgr.create_task(task1())
    future2 = mgr.create_task(task2(event))
    future3 = mgr.create_task(task3())
    event.wait(2)
    for _ in range(force_shutdown_times):
        mgr.shutdown()
        assert len(mgr._tasks) == 0
        assert all_mgr_threads_finished()

    assert future1.result() is 1
    assert future2.result() is 2
    with pytest.raises(asyncio.CancelledError):
        future3.result()


def test_shutdown():
    shutdown_helper(force_shutdown_times=1)
    shutdown_helper(force_shutdown_times=1)
    shutdown_helper(force_shutdown_times=2)
    shutdown_helper(force_shutdown_times=2)
    shutdown_helper(force_shutdown_times=10)
    shutdown_helper(force_shutdown_times=10)


def test_same_asyncio_loop():
    astm1 = AsyncioTaskManager()
    counters = {'astm1': 0, 'astm2': 0}
    done = threading.Event()

    async def inc_counter(counter):
        while True:
            counters[counter] += 1
            await asyncio.sleep(0)
            if sum(counters.values()) > 30:
                done.set()
    astm2 = AsyncioTaskManager(asyncio_loop=astm1._loop)
    assert astm1._loop == astm2._loop
    astm1.create_task(inc_counter('astm1'))
    astm2.create_task(inc_counter('astm2'))
    assert done.wait(1)
    astm2.shutdown(None)
    del astm2
    assert counters['astm1'] > 10 and counters['astm2'] > 10
    assert astm1._loop.is_running(), "loop should be running"
    counters['astm2'] = counters['astm1'] = 0
    done.clear()
    assert done.wait(1)
    astm1.shutdown(None)
    assert not astm1._loop.is_running()
    del astm1
