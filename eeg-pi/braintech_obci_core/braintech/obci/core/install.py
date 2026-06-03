# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
import glob
import os
import shutil
import sys
from pathlib import Path

base = Path(__file__).parent.parent.parent.parent
resources_path = (Path(__file__).parent / "resources").relative_to(base)
LINKS = [
    (resources_path / '99-openbci-cyton.rules', '/etc/udev/rules.d/'),
]


def run():
    from braintech.utils.install import create_links
    create_links(LINKS, base)


def install_all():
    install_all_script = shutil.which('install_all') or sys.executable
    cur_dir = os.path.dirname(install_all_script)
    install_scripts = cur_dir + '/install_*' + (".exe" if os.name == 'nt' else "")
    for f in sorted(glob.glob(install_scripts)):
        if not os.path.basename(f).startswith('install_all'):
            print("Running", f, flush=True)
            os.system(f)
