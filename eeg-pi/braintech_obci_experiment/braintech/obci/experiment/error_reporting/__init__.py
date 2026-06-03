import os
import sys

import sentry_sdk
from braintech.obci.core.conf import settings


class NotFound(Exception):
    pass


def fetch_package_version(dist_name):
    try:
        # Importing pkg_resources can be slow, so only import it
        # if we need it.
        import pkg_resources
    except ImportError:
        # pkg_resource is not available on Google App Engine
        raise NotImplementedError('pkg_resources is not available '
                                  'on this Python install')
    dist = pkg_resources.get_distribution(dist_name)
    return dist.version


def get_svarog_streamer_or_svarog_lab_version():
    if sys.platform == 'win32':
        this_folder = getattr(sys, '_MEIPASS', os.path.dirname(__file__))
        install_dir = os.path.abspath(os.path.join(this_folder, '..'))
        try:
            with open(os.path.join(install_dir, 'version.txt')) as info:
                infos = info.read()
                name, version = infos.strip().split(':')
            return name, version
        except FileNotFoundError:
            raise NotFound
    else:
        try:
            import svarog_lab
            name = 'Svarog Lab'
            version = fetch_package_version('svarog-lab')
            return name, version
        except ImportError:
            pass
        try:
            import svarog_streamer
            name = 'Svarog Streamer'
            version = fetch_package_version('svarog-streamer')
            return name, version
        except ImportError:
            raise NotFound


def get_backup_info():
    version_exp = fetch_package_version('braintech-obci-experiment')
    try:
        import braintech.obci.lab

        version_lab = fetch_package_version('braintech-obci-lab')
        release = '{}+{}'.format(version_exp, version_lab)
        site = "braintech-obci-experiment v:{}, braintech-obci-lab v:{}".format(version_exp, version_lab)

    except ImportError:
        site = "braintech-obci-experiment v:{}".format(version_exp)
        release = version_exp

    return site, release


def get_version_info():
    try:
        name, version = get_svarog_streamer_or_svarog_lab_version()
    except NotFound:
        name, version = get_backup_info()
    return name, version


def install_sentry():
    print()
    if not settings.send_telemetry:
        return
    dsn = settings.sentry_dsn
    if not dsn:
        return

    name, version = get_version_info()

    ignore_errors = [KeyboardInterrupt]
    sentry_sdk.init(dsn=dsn,
                    release=version,
                    environment=name,
                    ignore_errors=ignore_errors
                    )
