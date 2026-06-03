# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.
from setuptools import setup, find_namespace_packages

import versioneer


INSTALL_REQUIREMENTS = {
    'setup': [
        'pyqt-distutils>=0.7.3'
    ],
    'install': [
        'janus~=0.3',
        'netifaces~=0.10.4',  # used in obci/utils/net.py
        'numpy~=1.16.1',
        'psutil~=5.2',  # used in obci/utils/filesystem.py
        'pylsl~=1.10.6',
        'pyserial~=3.4.0',  # required by OpenBCI.com V3 amplifier
        'pyzmq>=17.1.2',
        'scikit-learn~=0.21.3',
        'scipy~=1.2.1',
        'braintech-utils~=2.8.0',
        'braintech-obci-signal-processing~=2.8.0'
    ],
}

if __name__ == '__main__':
    setup(
        name='braintech-obci-core',
        version=versioneer.get_version(),
        description='BCI framework for building complete Brain Computer Interfaces '
                    'based on EEG, performing experiments, collecting EEG and other '
                    'biomedical signal data.',
        zip_safe=False,
        author='BrainTech',
        author_email='admin@braintech.pl',
        license='Other/Proprietary License',
        classifiers=[
            'Development Status :: 3 - Alpha',
            'Natural Language :: English',
            'Topic :: Scientific/Engineering',
            'Intended Audience :: Developers',
            'License :: Other/Proprietary License',
            'Programming Language :: Python :: 3',
            'Programming Language :: Python :: 3.5',
            'Operating System :: POSIX :: Linux',
            'Operating System :: Microsoft :: Windows',
            'Operating System :: OS Independent',
            'Environment :: Console',
            'Environment :: Win32 (MS Windows)',
            'Environment :: X11 Applications :: Qt',
        ],
        keywords='bci eeg obci',
        packages=find_namespace_packages(include=['braintech.obci.*']),
        include_package_data=True,
        setup_requires=INSTALL_REQUIREMENTS['setup'],
        install_requires=INSTALL_REQUIREMENTS['install'],
        extras_require=INSTALL_REQUIREMENTS,
        entry_points={
            'console_scripts': [
                'install_obci = braintech.obci.core.install:run',
                'install_all = braintech.obci.core.install:install_all'
            ],
        },
        ext_modules=[],
    )
