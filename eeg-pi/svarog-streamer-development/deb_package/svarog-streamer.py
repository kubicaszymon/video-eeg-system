# -*- coding: utf-8 -*-
# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import os
import re
import shutil
import subprocess
from pathlib import Path

from vdist.builder import Builder
from vdist.source import directory

from devops.devpi import current_index

this_dir = Path(__file__).parent.absolute()

# Instantiate the builder while passing it a custom location for
# your profile definitions
profiles_path = os.path.dirname(os.path.abspath(__file__))

builder = Builder(profiles_dir=str(this_dir))
package_data = this_dir / 'data'
app = 'svarog-streamer'
package_dest_path = "/opt/{app}".format(app=app)
builder.build_basedir = str(this_dir.absolute() / 'build')
_devpi_index = current_index()['url']
if 'DEVPI_URL' in os.environ:
    _devpi_index = re.match('^(https?://[^/]+)/?', os.environ['DEVPI_URL']).group(1) + '/' + current_index()['name']
version = subprocess.check_output("python3 setup.py --version",
                                  shell=True, cwd=this_dir.parent.resolve()).decode('utf-8').strip()
builder.add_build(
    # Name of the build
    name=app + ' :: ubuntu build',

    # Name of the app (used for the package name)
    app=app,

    # The version; you might of course get this value from e.g. a file
    # or an environment variable set by your CI environment
    version=version,

    # Base the build on a directory; this would make sense when executing
    # vdist in the context of a CI environment
    source=directory(path=str(package_data)),

    # Use the 'centos7' profile
    profile='ubuntu1804',

    # Do not compile Python during packaging, a custom Python interpreter is
    # already made available on the build machine
    compile_python=False,
    python_version='3.6.6',
    # The location of your custom Python interpreter as installed by an
    # OS package Falseally from a private package repository) on your
    # docker container.
    python_basedir='/opt/braintech-svarog-streamer-python',
    # As python_version is not given, vdist is going to assume your custom
    # package is a Python 2 interpreter, so it will call 'python'. If your
    # package were a Python 3 interpreter then you should include a
    # python_version='3' in this configuration to make sure that vdist looks
    # for a 'python3' executable in 'python_basedir'.

    # Depend on an OS package called "yourcompany-python" which would contain
    # the Python interpreter; these are build dependencies, and are not
    # runtime dependencies. You docker container should be configured to reach
    # your private repository to get "yourcompany-python" package.
    # build_deps=['gcc', 'curl', 'git', 'fpm'],

    # Specify OS packages that should be installed when your application is
    # installed
    build_deps=[],
    runtime_deps=['vlc', ],

    # Some extra arguments for fpm, in this case a postinstall script that
    # will run after your application will be installed (useful for e.g.
    # startup scripts, supervisor configs, etc.)
    pip_args='--index-url="%s"' % (_devpi_index),
    fpm_args="--deb-suggests qttranslations5-l10n " \
             "--description 'Svarog-Streamer - drivers and apps for Perun amplifiers.' " \
             "--vendor BrainTech " \
             "--url http://braintech.pl"
             "".format(package_path=package_dest_path),
    after_install="post_install.sh",
    after_remove="post_remove.sh",
    before_remove="pre_remove.sh"
)
builder.create_build_folder_tree()
# builder._write_build_script(builder.build)
os.mkdir(builder.build.scratch_dir + '/' + package_data.name)
shutil.copy(str(this_dir / 'build_tools.py'), builder.build.scratch_dir)
builder.populate_build_folder_tree()
builder.run_build()
