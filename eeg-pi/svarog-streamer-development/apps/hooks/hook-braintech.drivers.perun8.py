from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

datas = collect_data_files('braintech.drivers.perun8')
datas += collect_data_files('braintech.drivers.perun8.peers')
binaries = collect_dynamic_libs('braintech.drivers.perun8')
binaries += collect_dynamic_libs('braintech.drivers.perun8.peers')
