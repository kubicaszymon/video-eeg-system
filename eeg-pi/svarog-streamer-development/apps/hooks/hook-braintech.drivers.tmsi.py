from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

datas = collect_data_files('braintech.drivers.tmsi')
datas += collect_data_files('braintech.drivers.tmsi.peers')
binaries = collect_dynamic_libs('braintech.drivers.tmsi')
binaries += collect_dynamic_libs('braintech.drivers.tmsi.peers')
