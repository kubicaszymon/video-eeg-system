# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Provides functions :func:`print_threads` and :func:`print_asyncio_tasks` for debugging use only."""

import asyncio
import sys
import threading
import traceback


def print_threads(title=None):
    """Print callstacks for all threads."""
    postfix = '' if title is None else ' - ' + title
    print('Print threads begin{}'.format(postfix))
    for thread in threading.enumerate():
        print(thread)
        traceback.print_stack(sys._current_frames()[thread.ident])
        print('')
    print('Print threads end{}'.format(postfix))


def print_asyncio_tasks(title=None):
    """Print all asyncio tasks for current message loop."""
    postfix = '' if title is None else ' - ' + title
    print('Print asyncio tasks begin{}'.format(postfix))
    for task in asyncio.Task.all_tasks():
        print(task)
        print('')
    print('Print asyncio tasks end{}'.format(postfix))
