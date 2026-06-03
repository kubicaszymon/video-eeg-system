from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

datas = collect_data_files('obci_p300')
binaries = collect_dynamic_libs('obci_p300')