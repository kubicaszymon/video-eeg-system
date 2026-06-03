#!/usr/bin/env bash
uname -r | grep "Microsoft"
is_wsl=$?
if [ $is_wsl -eq 1 ]; then
    service udev restart
else
    echo "WSL - not restarting udev"
fi
