"""Stub of ``braintech.utils.install``.

Only the driver ``install.py`` setup scripts import these, and those
scripts are NOT used on the streaming path (we install manually instead).
The no-op stubs exist purely so the modules can be imported without error.
"""


def create_links(*args, **kwargs):
    return None


def install_apt_requirements(*args, **kwargs):
    return None


__all__ = ["create_links", "install_apt_requirements"]
