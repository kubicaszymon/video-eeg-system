import os

import PySide2
from PySide2.QtWidgets import QApplication, QMessageBox
try:
    from braintech.obci.lab.conf import settings
except ImportError:
    from braintech.obci.core.conf import settings
import sys

import gettext
t = gettext.translation('init_settings_app', os.path.join(os.path.dirname(__file__), '..', 'translations'), fallback=True)
_ = t.gettext


def _settings_init(headless_telemetry_answer):
    if headless_telemetry_answer is not None:
        answer = headless_telemetry_answer
    else:
        answer_type = QMessageBox.question(None,
                                           _("Telemetry"),
                                           _("Do you agree to send anonymized "
                                             "telemetry when an error occures?\n\n"
                                             "This will help Braintech to fix issues "
                                             "in the software you "
                                             "might encounter."),
                                           )
        answer = answer_type == PySide2.QtWidgets.QMessageBox.StandardButton.Yes
    settings.send_telemetry = answer
    settings.gui_init_done = True


def settings_init(forced_reinit=True, headless_telemetry_answer=None):
    if forced_reinit:
        _settings_init(headless_telemetry_answer)
        return
    if not settings.gui_init_done:
        _settings_init(headless_telemetry_answer)
        return


def run_settings_init():
    if 'headless' in sys.argv:
        settings_init(True, False)
    else:
        app = QApplication([])
        settings_init()
