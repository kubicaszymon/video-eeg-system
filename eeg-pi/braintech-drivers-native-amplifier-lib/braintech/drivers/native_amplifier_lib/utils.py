import os
import shutil

import braintech.drivers.native_amplifier_lib.native_lib as nl


def get_includes(copy_relative_to_filepath):
    return [os.path.join(os.path.dirname(copy_relative_to_filepath), 'native_lib_src')]


def get_sources(copy_relative_to_filepath):
    native_lib_path = os.path.join(os.path.dirname(nl.__file__), 'src')
    dirlisting = os.listdir(native_lib_path)
    all_files = [os.path.join(native_lib_path, i) for i in dirlisting]
    target_dir = os.path.join(os.path.dirname(copy_relative_to_filepath), 'native_lib_src')
    target_dir_rel = os.path.relpath(target_dir, os.path.dirname(copy_relative_to_filepath))
    os.makedirs(target_dir, exist_ok=True)

    sources = []
    for file in all_files:
        filename = os.path.basename(file)
        shutil.copy(file, os.path.join(target_dir, filename))
        if file.endswith('.cpp'):
            sources.append(os.path.join(target_dir_rel, filename))
    return sources
