# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

from .launcher_tools import NOT_READY, READY_TO_LAUNCH, LAUNCHING, FAILED_LAUNCH, RUNNING, STOPPING, FINISHED, FAILED, \
    TERMINATED

STATUS_COLORS = {
    NOT_READY: 'dimgrey',
    READY_TO_LAUNCH: 'bisque',
    LAUNCHING: 'lightseagreen',
    FAILED_LAUNCH: 'red',
    RUNNING: 'lightgreen',
    STOPPING: 'yellow',
    FINISHED: 'lightblue',
    FAILED: 'red',
    TERMINATED: 'khaki'
}
