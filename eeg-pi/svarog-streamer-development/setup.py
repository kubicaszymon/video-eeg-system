# -*- coding: utf-8 -*-
# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

from setuptools import find_packages, setup

import versioneer

INSTALL_REQUIREMENTS = {
    'install': ['braintech-obci-experiment',
                'PySide2',
                ],
    'test': [
        'pytest>=3.0',
        'pytest-runner>=2.9',
        'pytest-cov>=2.3.1',
        'pytest-timeout>=1.0',
        'pytest-catchlog>=1.2.2',
        'flaky>=3.3.0',
        'nose>=1.3.7',
    ],
    'codestyle': ['flake8>=3.0.4', 'flake8_docstrings>=1.0.2'],
    'dev': ['check-manifest>=0.34', 'versioneer==0.17'],
    'build': ['stdeb>=0.8.5', 'wheel>=0.29.0'],
    'docs': ['sphinx>=1.4.8', 'sphinx-rtd-theme>=0.1.9', 'sphinxcontrib-asyncio>=0.2'],
    'setup': ['pyqt-distutils', 'PySide2']

}
if __name__ == '__main__':
    try:
        from devops.setup import get_cmd_class

        cmd_classes = get_cmd_class()
    except ImportError:
        print("devops not installed yet, can't run build_ui.")
        cmd_classes = versioneer.get_cmdclass()

    setup(
        name='svarog-streamer',
        version=versioneer.get_version(),
        cmdclass=cmd_classes,
        zip_safe=False,
        author='BrainTech',
        author_email='admin@braintech.pl',
        description='Applications from Braintech for Perun Amplifiers',
        packages=find_packages(
            exclude=[
                # 'docs',
                'test',
                'scripts',
            ]
        ),
        include_package_data=True,
        exclude_package_data={'': ['.gitignore', '.gitlab-ci.yml']},
        install_requires=INSTALL_REQUIREMENTS['install'],
        tests_require=INSTALL_REQUIREMENTS['test'],
        setup_requires=INSTALL_REQUIREMENTS['setup'],
        extras_require={key: INSTALL_REQUIREMENTS[key] for key in ['dev', 'build', 'codestyle', 'test']},
        entry_points={
            'console_scripts': [
                'svarog_streamer = svarog_streamer.cmd:run',
                'install_svarog_streamer = svarog_streamer.install:run',
            ],
        },
    )
