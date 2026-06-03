# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Function for to wait for some condition using asyncio."""
import time
import asyncio
import inspect
from typing import Callable, Union, Awaitable

from braintech.obci.core.broker import ObciException


class WaitForConditionTimeout(ObciException):
    """Raised when condition isn't true for too long."""

    pass


async def wait_for_condition(condition_func: Union[Callable[[], Awaitable[bool]],
                                                   Callable[[], bool]],
                             timeout: float,
                             sleep_duration: float,
                             name: str
                             ) -> None:
    """
    Asynchronously wait for some condition.

    :param condition_func: Function or coroutine which returns True or False, describing a condition.
        Has to be non blocking.
    :param timeout: time in seconds - how long do you want to wait for the condition.
    :param sleep_duration: time in seconds - how often you want to check on condition_func.
    :param name: name of the awaited condition.
    :return: None
    :raises: WaitForConditionTimeout when timeout is reached.
    """
    start_time = time.monotonic()
    while True:
        cond = condition_func()
        if inspect.isawaitable(cond):
            if await cond:
                break
        else:
            if cond:
                break
        await asyncio.sleep(sleep_duration)  # required
        if time.monotonic() - start_time > timeout:
            raise WaitForConditionTimeout('{}: timeout reached (={} seconds)'
                                          .format(name, timeout))
