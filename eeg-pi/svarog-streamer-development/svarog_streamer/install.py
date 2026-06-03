# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
from pathlib import Path

APT_REQUIREMENTS = []
base = Path(__file__).parent.parent
resources_path = (Path(__file__).parent / "resources").relative_to(base)
LINKS = [
    (resources_path / 'svarog_streamer.png', '/usr/share/pixmaps/'),
    (resources_path / 'braintech.png', '/usr/share/pixmaps/'),
    (resources_path / 'lsl_stream.desktop', '/usr/share/applications/'),
    (resources_path / 'svarog_streamer.desktop', '/usr/share/applications/'),
]


def run():
    from braintech.utils.install import create_links, install_apt_requirements
    install_apt_requirements(APT_REQUIREMENTS, 'svarog_streamer')
    create_links(LINKS, base)
