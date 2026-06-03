import platform
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

datas = []
dlls_temp = collect_dynamic_libs('pylsl')
binaries = []

def mac_check(name):
    if sys.platform.startswith('darwin'):
        if ".dylib" in name:
            return True
        else:
            return False
    else:
        return True

if platform.architecture()[0] == '32bit':
    for i in dlls_temp:
        if ('64' not in i[0]) and mac_check(i[0]):
            binaries.append(i)
else:
    for i in dlls_temp:
        if ('32' not in i[0]) and mac_check(i[0]):
            binaries.append(i)
