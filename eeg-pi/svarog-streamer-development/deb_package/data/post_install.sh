#!/usr/bin/env bash
uname -r | grep "Microsoft"
is_wsl=$?
if [ $is_wsl -eq 1 ]; then
    service udev restart
else
    echo "WSL - not restarting udev"
fi
#Ubuntu 18.04 has different python and we can't steal tkinter like that, need to bundle it?
# without tkinter matlplotib doesn't work, WebBCIControll panel required some workarounds, to ignore tkinter import errors
ln -sfn /usr/lib/python3.6/lib-dynload/_tkinter.cpython-36m-x86_64-linux-gnu.so /opt/braintech-svarog-streamer-python/lib/python3.6/lib-dynload/
