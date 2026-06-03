from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

datas = collect_data_files('braintech.drivers.native_amplifier_lib')
datas += collect_data_files('braintech.drivers.native_amplifier_lib.peers')
binaries = collect_dynamic_libs('braintech.drivers.native_amplifier_lib')
binaries += collect_dynamic_libs('braintech.drivers.native_amplifier_lib.peers')
