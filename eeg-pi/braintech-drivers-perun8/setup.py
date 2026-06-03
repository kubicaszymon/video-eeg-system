#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.
import os
import sys

from setuptools import setup, Extension, find_namespace_packages
from setuptools.command.build_ext import build_ext

import versioneer

cpp_debug = False

needs_pytest = {'pytest', 'test', 'ptr'}.intersection(sys.argv)
pytest_runner = ['pytest-runner<4.0'] if needs_pytest else []

extra_opts = ['-g3', '-Og'] if cpp_debug else []  # ['-g0', '-O3']


sources = [
    'braintech/drivers/perun8/_perun8.pyx',
    'src/perun/PerunAmplifier.cpp',
]


include_dirs = [
    'src/perun',
    'src/perun/lib'
]


macros = ('BLUETOOTH', 'false')
libraries = ['ftdi']

perun8_amp = Extension(
    name='braintech.drivers.perun8._perun8',
    sources=sources,
    language='c++',
    define_macros=[macros],
    undef_macros=['NDEBUG'],
    include_dirs=include_dirs,
    libraries=libraries,
    extra_compile_args=['-std=c++14'] + extra_opts
)

INSTALL_REQUIREMENTS = {
    'install': ['braintech-obci-core~=2.8.0', 'numpy', 'braintech-drivers-native-amplifier-lib~=2.8.0'],
    'setup': [
                 # setuptools 19.6 properly handles Cython extensions
                 'setuptools>=19.6',
                 'cython>=0.23.4',
                 'numpy~=1.11',
                 'braintech-drivers-native-amplifier-lib~=2.8.0'
             ] + pytest_runner,
    'test': ['pytest'],
}
cmd_class = versioneer.get_cmdclass()


class NumpyBuildExt(build_ext):
    def run(self):
        import numpy
        self.include_dirs.append(numpy.get_include())
        super(NumpyBuildExt, self).run()


class BraintechNativeLibExt(NumpyBuildExt):
    def run(self):
        from braintech.drivers.native_amplifier_lib.utils import get_includes, get_sources
        self.include_dirs.extend(get_includes(__file__))
        source_list = get_sources(__file__)
        for i in self.extensions:
            i.sources.extend(source_list)
        super().run()


cmd_class['build_ext'] = BraintechNativeLibExt


if sys.platform.startswith('win'):
    perun8_amp.libraries = ['ftd2xx', "Ws2_32"]
    perun8_amp.library_dirs = ['win_libs']
    perun8_amp.define_macros = []
    perun8_amp.extra_compile_args = extra_opts
    perun8_amp.include_dirs.append("win_libs")
if __name__ == '__main__':
    setup(
        name='braintech-drivers-perun8',
        description='BCI-Framework cpp amplifiers: Perun8',
        author='BrainTech',
        author_email='admin@braintech.pl',
        keywords='bci eeg obci',
        version=versioneer.get_version(),
        cmdclass=cmd_class,
        packages=find_namespace_packages(include=['braintech.drivers.*']),
        include_package_data=True,
        zip_safe=False,
        ext_modules=[perun8_amp],
        setup_requires=INSTALL_REQUIREMENTS['setup'],
        tests_require=INSTALL_REQUIREMENTS['test'],
        install_requires=INSTALL_REQUIREMENTS['install'],
        extras_require=INSTALL_REQUIREMENTS,
        entry_points={
            'console_scripts': [
                'install_perun8 = braintech.drivers.perun8.install:run'
            ]
        }
    )
