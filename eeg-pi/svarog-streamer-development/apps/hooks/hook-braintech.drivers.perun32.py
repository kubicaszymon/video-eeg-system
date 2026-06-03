from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

datas = collect_data_files('braintech.drivers.perun32')
binaries = collect_dynamic_libs('braintech.drivers.perun32')