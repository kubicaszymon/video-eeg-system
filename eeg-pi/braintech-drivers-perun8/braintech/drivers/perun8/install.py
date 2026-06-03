# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
from pathlib import Path

APT_REQUIREMENTS = [
    'libftdi1'
]
base = Path(__file__).parent.parent.parent.parent
resources_path = (Path(__file__).parent / "resources").relative_to(base)
LINKS = [
    (resources_path / '99-perun.rules', '/etc/udev/rules.d/'),
]


def run():
    from braintech.utils.install import create_links, install_apt_requirements
    install_apt_requirements(APT_REQUIREMENTS, 'braintech.drivers.perun8')
    create_links(LINKS, base)
