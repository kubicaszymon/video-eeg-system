#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import sys

from setuptools import setup, Extension,  find_namespace_packages
from setuptools.command.build_ext import build_ext
import versioneer

cpp_debug = False

needs_pytest = {'pytest', 'test', 'ptr'}.intersection(sys.argv)
pytest_runner = ['pytest-runner<4.0'] if needs_pytest else []

extra_opts = ['-g3', '-Og'] if cpp_debug else []  # ['-g0', '-O3']

sources_dummy_amp = [
    'braintech/drivers/native_amplifier_lib/dummy_amp/_dummy_amp.pyx',
    'braintech/drivers/native_amplifier_lib/dummy_amp/src/DummyAmplifier.cpp',
    'braintech/drivers/native_amplifier_lib/native_lib/src/Logger.cpp',
    'braintech/drivers/native_amplifier_lib/native_lib/src/Utils.cpp',
    'braintech/drivers/native_amplifier_lib/native_lib/src/AmplifierDescription.cpp',
    'braintech/drivers/native_amplifier_lib/native_lib/src/Amplifier.cpp',
]


include_dirs_dummy_amp = [
    'braintech/drivers/native_amplifier_lib/dummy_amp/src',
    'braintech/drivers/native_amplifier_lib/dummy_amp',
    'braintech/drivers/native_amplifier_lib/native_lib',
    'braintech/drivers/native_amplifier_lib/native_lib/src',
]


sources_lib = [
    'braintech/drivers/native_amplifier_lib/native_lib/_native_lib.pyx',
    'braintech/drivers/native_amplifier_lib/native_lib/src/Logger.cpp',
    'braintech/drivers/native_amplifier_lib/native_lib/src/Utils.cpp',
    'braintech/drivers/native_amplifier_lib/native_lib/src/AmplifierDescription.cpp',
    'braintech/drivers/native_amplifier_lib/native_lib/src/Amplifier.cpp',
]


include_dirs_lib = [
    'braintech/drivers/native_amplifier_lib/native_lib',
    'braintech/drivers/native_amplifier_lib/native_lib/src',
]

libraries = []
macros = ('BLUETOOTH', 'false')

cpp_amplifiers = Extension(
    name='braintech.drivers.native_amplifier_lib.dummy_amp._dummy_amp',
    sources=sources_dummy_amp,
    language='c++',
    define_macros=[macros],
    undef_macros=['NDEBUG'],
    include_dirs=include_dirs_dummy_amp,
    libraries=libraries,
    extra_compile_args=['-std=c++14'] + extra_opts
)

native_lib = Extension(
    name='braintech.drivers.native_amplifier_lib.native_lib._native_lib',
    sources=sources_lib,
    language='c++',
    define_macros=[macros],
    undef_macros=['NDEBUG'],
    include_dirs=include_dirs_lib,
    libraries=libraries,
    extra_compile_args=['-std=c++14'] + extra_opts
)

INSTALL_REQUIREMENTS = {
    'install': ['braintech-obci-core~=2.8.0', 'numpy'],
    'setup': [
                 # setuptools 19.6 properly handles Cython extensions
                 'setuptools>=19.6',
                 'cython>=0.23.4',
                 'numpy~=1.11',
             ] + pytest_runner,
    'test': ['pytest', 'braintech-obci-experiment~=2.8.0'],
}
cmd_class = versioneer.get_cmdclass()


class NumpyBuildExt(build_ext):
    def run(self):
        import numpy
        self.include_dirs.append(numpy.get_include())
        super(NumpyBuildExt, self).run()


cmd_class['build_ext'] = NumpyBuildExt

if sys.platform.startswith('win'):
    cpp_amplifiers.define_macros = []
    cpp_amplifiers.extra_compile_args = extra_opts

if __name__ == '__main__':
    setup(
        name='braintech-drivers-native-amplifier-lib',
        description='BCI-Framework cpp amplifiers: Dummy ',
        author='BrainTech',
        author_email='admin@braintech.pl',
        keywords='bci eeg obci',
        version=versioneer.get_version(),
        cmdclass=cmd_class,
        packages=find_namespace_packages(include='braintech.drivers.*'),
        include_package_data=True,
        zip_safe=False,
        ext_modules=[cpp_amplifiers, native_lib],
        setup_requires=INSTALL_REQUIREMENTS['setup'],
        tests_require=INSTALL_REQUIREMENTS['test'],
        install_requires=INSTALL_REQUIREMENTS['install'],
        extras_require=INSTALL_REQUIREMENTS,
        entry_points={
            'console_scripts': [
            ]
        }
    )
