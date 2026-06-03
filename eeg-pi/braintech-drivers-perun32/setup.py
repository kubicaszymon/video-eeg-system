#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

from setuptools import setup, find_namespace_packages

INSTALL_REQUIREMENTS = {
    'install': ['braintech-obci-core~=2.8.0',
                'braintech-drivers-perun8~=2.8.0',
                'numpy',
                'libusb1',
                ],
    'setup': [
        'setuptools_scm',
    ]
}

if __name__ == '__main__':
    setup(
        name='braintech-drivers-perun32',
        description='Brain Amplifier 32',
        author='BrainTech',
        author_email='admin@braintech.pl',
        keywords='bci eeg obci',
        use_scm_version={'root': '..', 'relative_to': __file__},
        packages=find_namespace_packages(include=['braintech.drivers.*']),
        package_data={'braintech.drivers.perun32': ['bin/*.*', '*.ini']},
        setup_requires=INSTALL_REQUIREMENTS['setup'],
        install_requires=INSTALL_REQUIREMENTS['install'],
        extras_require=INSTALL_REQUIREMENTS,
        entry_points={
            'console_scripts': [
                'install_perun32 = braintech.drivers.perun32.install:run'
            ]
        }
    )
