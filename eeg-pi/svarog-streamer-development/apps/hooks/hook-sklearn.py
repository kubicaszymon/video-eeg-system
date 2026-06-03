from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

datas = collect_data_files('sklearn')
binaries = collect_dynamic_libs('sklearn')
binaries += collect_dynamic_libs('sklearn.utils._cython_blas')
datas += collect_data_files('sklearn.utils._cython_blas')