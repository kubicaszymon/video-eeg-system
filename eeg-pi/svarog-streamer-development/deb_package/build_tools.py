# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
import compileall
import os
import re
import shutil
import sys

DELETE_FILES = [
    r'.*\.pyi',
    r'__pycache__$',
    r'/site-packages\/(?!obci|psychopy).*/(?!__version__\.py$).*\.py$',
    r'/PySide2/(?!Qt).*/.*$',
    r'/site-packages/(mne|pandas|pywt|zmq|tables|(sklern/.*)|pygame|psutil|gevent)/tests$'
    r'pygame/examples$',
    r'python3../idlelib$',
    r'python3../test$',
]


def delete_files(path):
    compileall.compile_dir(path, maxlevels=100, legacy=True, workers=4, quiet=True, ddir='')
    regexp = re.compile("(" + (")|(".join(DELETE_FILES)) + ")")

    for path, dirs, files in os.walk(path, topdown=True):
        if regexp.search(path):
            shutil.rmtree(path)
            dirs[:] = []
            continue
        for f in files:
            full_path = os.path.join(path, f).replace('\\', '/')
            if regexp.search(full_path):
                os.unlink(full_path)


BIN_SCRIPTS = [
    'bci_demo_p300',
    'svarog_streamer',
    'obci_run_peer',
    'obci_init',
]


def print_console_scripts():
    for name in BIN_SCRIPTS:
        print("%s/bin/%s=/usr/bin/" % (sys.prefix, name), end=" ")


if __name__ == '__main__':
    if 'delete_files' in sys.argv:
        delete_files(sys.argv[-1])
    else:
        print_console_scripts()
