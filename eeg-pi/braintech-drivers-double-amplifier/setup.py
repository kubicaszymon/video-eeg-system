#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

from setuptools import setup, find_namespace_packages
import versioneer

INSTALL_REQUIREMENTS = {
    'install': ['braintech-obci-core~=2.8.0',
                'numpy~=1.16',
                'braintech-drivers-perun32~=2.8.0',
                'braintech-drivers-perun8~=2.8.0',
                ],
    'setup': [
        'setuptools_scm',
    ]
}

if __name__ == '__main__':
    setup(
        name='braintech-drivers-double-amplifier',
        description='Double Amplifier Implementation',
        author='BrainTech',
        author_email='admin@braintech.pl',
        keywords='bci eeg obci',
        version=versioneer.get_version(),
        use_scm_version={'root': '..', 'relative_to': __file__},
        packages=find_namespace_packages(include=['braintech.drivers.*']),
        package_data={'double_amplifier': ['*.ini']},
        include_package_data=True,
        zip_safe=False,
        setup_requires=INSTALL_REQUIREMENTS['setup'],
        install_requires=INSTALL_REQUIREMENTS['install'],
        extras_require=INSTALL_REQUIREMENTS,
        entry_points={
            'console_scripts': [
            ]
        }
    )
