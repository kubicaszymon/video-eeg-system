# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Module with filesystem utility functions."""
import os
import os.path
from typing import Union

import psutil


def is_exe(fpath: str) -> bool:
    """Return if path exists and is executable."""
    return os.path.exists(fpath) and os.access(fpath, os.X_OK)


def which(program: str) -> Union[str, bool]:
    """Return path to a program in PATH, if available, else return False."""

    def ext_candidates(fpath):
        yield fpath
        for ext in os.environ.get('PATHEXT', '').split(os.pathsep):
            yield fpath + ext

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            exe_file = os.path.join(path, program)
            for candidate in ext_candidates(exe_file):
                if is_exe(candidate):
                    return candidate
    return False


def checkpidfile(file: str) -> bool:
    """
    Create lockfile named file.

    Legacy - when writing a new app use `SingleApplicationInstance` class.

    :return: True if file exists and used by another process,
        False - when this process is first to create the lock

    """
    lockfile = getpidfile(file)

    if os.access(os.path.expanduser(lockfile), os.F_OK):
        pidfile = open(os.path.expanduser(lockfile), "r")
        pidfile.seek(0)
        try:
            old_pd = int(pidfile.readline())
        except Exception:  # assumed error in pidfile
            pidfile.close()
            os.remove(os.path.expanduser(lockfile))
        else:
            if psutil.pid_exists(old_pd) == 1:
                print("You already have an instance of the program running")
                print("It is running as process %s," % str(old_pd))
                return True
            else:
                pidfile.close()
                os.remove(os.path.expanduser(lockfile))

    with open(os.path.expanduser(lockfile), 'w') as pidfile:
        pidfile.write("%s" % os.getpid())

    return False


def getpidfile(file):
    """Utility function to find standard lockfile location."""
    obci_home_dir = os.path.join(os.path.expanduser('~'), '.obci')
    lockfile = os.path.join(obci_home_dir, file)

    try:
        if not os.path.isdir(obci_home_dir):
            os.makedirs(obci_home_dir)
    except Exception:
        pass

    return lockfile


def removepidfile(file):
    """Remove the lock file - realease the lock."""
    lockfile = getpidfile(file)
    try:
        os.remove(lockfile)
    except OSError:
        print("Attempted to remove pid file: " + lockfile + " but couldn't find the file. Ignore!")
