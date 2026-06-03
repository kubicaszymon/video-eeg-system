import os
from functools import partial

import PySide2
from braintech.obci.experiment.apps.init_settings.init_settings_app import settings_init

from PySide2.QtCore import QTimer, QTranslator, QLocale
from PySide2.QtGui import QIcon
from PySide2.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox
import multiprocessing

from braintech.obci.core.control.common import net
from braintech.obci.experiment.error_reporting import install_sentry
from braintech.obci.experiment.launcher.simple_obci_client import SimpleOBCIClient, EmptyResponse
from braintech.utils.singleton_app import SingleInstanceException
from braintech.utils.singleton_app import SingleApplicationInstance

import gettext
t = gettext.translation('obci_tray_app', os.path.join(os.path.dirname(__file__), '..', 'translations'), fallback=True)
_ = t.gettext


def run_prefered_obci_server():
    try:
        from braintech.obci.lab.control.launcher.obci_server import run_obci_server
        srv_rep_port = net.server_rep_port()
        srv_pub_port = net.server_pub_port()
        rep_addrs = ['tcp://*:' + srv_rep_port]
        pub_addrs = ['tcp://*:' + srv_pub_port]
        args = ['--rep-addresses'] + rep_addrs + ['--pub-addresses'] + pub_addrs
        run_func = partial(run_obci_server, args)
    except ImportError:
        from braintech.obci.experiment.launcher.simple_obci_server import run
        run_func = run
    run_func()


class ObciTrayApp(QSystemTrayIcon):

    def __init__(self):
        super().__init__(None)
        this_folder = os.path.dirname(__file__)
        icon = QIcon(os.path.join(this_folder, 'icons', 'svarog.ico'))
        self.setIcon(icon)

        self._bubble_name = self._get_bubble_name()

        menu = QMenu(None)
        self.reinit_settings_option = menu.addAction(_("Telemetry agreement"))
        self.reinit_settings_option.triggered.connect(self.reinit_settings)
        self.shut_down_option = menu.addAction(_("Shut down EEG acquisition server"))
        self.shut_down_option.triggered.connect(self.shut_down_server)

        self.reinit_settings_option.setDisabled(True)
        self.shut_down_option.setDisabled(True)
        self.setContextMenu(menu)

        self.show()

        msg = _("Launching EEG acquisition server")
        self.notify(msg)
        self.setToolTip(msg)
        self.obci_server_process = multiprocessing.Process(target=run_prefered_obci_server)
        self.obci_server_process.start()
        self.obci_client = SimpleOBCIClient()
        QTimer.singleShot(500, self.check_server)

    def notify(self, msg):
        self.showMessage(self._bubble_name, msg, self.icon())

    def check_server(self):
        resp = self.obci_client.ping_server(100)
        if isinstance(resp, EmptyResponse):
            QTimer.singleShot(500, self.check_server)
        else:
            self.self_server_started()

    def self_server_started(self):
        self.notify(_("EEG acquisition server started"))
        self.setToolTip(_("EEG acquisition server"))
        self.reinit_settings_option.setDisabled(False)
        self.shut_down_option.setDisabled(False)

    def reinit_settings(self):
        settings_init(forced_reinit=True)
        self.notify(_('Changes will be acknowledged after system restart.'))

    def shut_down_server(self):
        reply = QMessageBox.question(None,
                                     _("Shutdown acquisition server"),
                                     _("All amplifiers will be switched off when the program is closed.  Shutdown?"),
                                     )
        if (reply == PySide2.QtWidgets.QMessageBox.StandardButton.No):
            return
        msg = _("Shutting down EEG acquisition server")
        self.notify(msg)
        self.setToolTip(msg)
        self.shut_down_option.setDisabled(True)
        self.reinit_settings_option.setDisabled(True)
        self.obci_client.srv_kill()
        QTimer.singleShot(500, self.check_server_shut_down)

    def check_server_shut_down(self):
        resp = self.obci_client.ping_server(100)
        if isinstance(resp, EmptyResponse):
            self.obci_server_process.join()
            self.notify(_("Server shut down"))
            QApplication.quit()
        else:
            QTimer.singleShot(500, self.check_server_shut_down)

    def _get_bubble_name(self):
        try:
            from braintech.obci.lab.control.launcher.obci_server import run_obci_server
            return "Svarog-Lab"
        except ImportError:
            from braintech.obci.experiment.launcher.simple_obci_server import run
            return "Svarog-Streamer"

def run_obci_tray():
    install_sentry()
    QLocale.setDefault('pl')
    app = QApplication()
    try:
        singleton_app = SingleApplicationInstance('obci_tray')
    except SingleInstanceException:
        QMessageBox.information(None, "EEG", _("EEG acquisition server already running!"))
        exit()

    translations_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'translations'))
    print(translations_path)
    translator = QTranslator()
    translator.load('obci_tray', translations_path)
    app.installTranslator(translator)

    translator = QTranslator()
    translator.load('init_settings_app', translations_path)
    app.installTranslator(translator)

    # only in case of new user or lost settings
    settings_init(forced_reinit=False)
    tray_app = ObciTrayApp()
    app.setQuitOnLastWindowClosed(False)
    app.exec_()