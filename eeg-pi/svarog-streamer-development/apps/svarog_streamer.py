import sys
import os
import signal
import subprocess
import multiprocessing
import threading

from PySide2.QtWidgets import QHBoxLayout, QApplication, QPushButton, QMainWindow, QWidget, QMessageBox

if sys.platform == 'win32':
    import win32process
    import win32gui
    import win32con


def hide_my_windows():
    if sys.platform == 'win32':
        pid = os.getpid()

        def callback(hwnd, hwnds):
            if win32gui.IsWindowVisible(hwnd) and win32gui.IsWindowEnabled(hwnd):
                _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
                if found_pid == pid:
                    hwnds.append(hwnd)
            return True

        hwnds = []
        win32gui.EnumWindows(callback, hwnds)
        for i in hwnds:
            win32gui.ShowWindow(i, win32con.SW_HIDE)


class MacLauncherWindow(QMainWindow):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app

        self.setWindowTitle("Svarog Streamer Launcher")
        button_svarog = QPushButton("Svarog")
        button_svarog.clicked.connect(self.launch_svarog)

        button_p300 = QPushButton("P300 Demo")
        button_p300.clicked.connect(self.launch_p300)

        button_lsl_stream = QPushButton("LSL streaming app")
        button_lsl_stream.clicked.connect(self.mac_lsl_streamer)

        button_unload_drivers = QPushButton("Unload interfering USB drivers")
        button_unload_drivers.setToolTip(
            "Unloads FTDI drivers which interfere with BrainAmp dongle. Valid until restart."
        )
        button_unload_drivers.clicked.connect(self.unload_drivers)

        button_lsl_stream = QPushButton("LSL streaming app")
        button_lsl_stream.clicked.connect(self.mac_lsl_streamer)

        layout = QHBoxLayout()
        layout.addWidget(button_svarog)
        layout.addWidget(button_p300)
        layout.addWidget(button_lsl_stream)
        layout.addWidget(button_unload_drivers)

        widget = QWidget()
        widget.setLayout(layout)

        self.setCentralWidget(widget)

    def launch_svarog(self):
        this_folder = getattr(sys, '_MEIPASS', os.path.dirname(__file__))

        out = open("/tmp/stdout.txt", "wb")
        err = open("/tmp/stderr.txt", "wb")
        script = '{}/svarog_streamer svarog'.format(this_folder).split()
        subprocess.Popen(script, stderr=err, stdout=out)
        self.close()

    def mac_lsl_streamer(self, *args):
        this_folder = getattr(sys, '_MEIPASS', os.path.dirname(__file__))
        self.close()
        QMessageBox.information(None,
                                "LSL streaming help",
                                "Terminal window will open. Type './svarog_streamer stream' command to use LSL streaming"
                                )
        subprocess.check_call(['open', '-a', 'Terminal', this_folder])

    def launch_p300(self):

        this_folder = getattr(sys, '_MEIPASS', os.path.dirname(__file__))

        out = open("/tmp/stdout.txt", "wb")
        err = open("/tmp/stderr.txt", "wb")
        script = '{}/svarog_streamer p300'.format(this_folder).split()
        subprocess.Popen(script, stderr=err, stdout=out)
        self.close()

    def unload_drivers(self):
        scripts = ["kextunload -bundle com.FTDI.driver.FTDIUSBSerialDriver",
                   "kextunload -bundle com.apple.driver.AppleUSBFTDI"
                   ]
        for script in scripts:
            command = [
                "osascript",
                "-e",
                'do shell script "{}" with administrator privileges'.format(script)
            ]
            try:
                subprocess.check_call(command)
            except subprocess.CalledProcessError:
                pass  # can fail, sometimes there is no driver loaded


def show_selection_screen_mac():
    app = QApplication([])
    window = MacLauncherWindow(app)
    window.show()
    app.exec_()


def launch_svarog(*args):
    print("Launching, please wait")
    this_folder = getattr(sys, '_MEIPASS', os.path.dirname(__file__))
    if sys.platform.startswith('darwin'):
        javapath = os.path.join(this_folder, '..', 'jre', 'bin', 'java')
        svarog_path = [javapath, '-jar', os.path.join(this_folder, '..', 'svarog', 'svarog-standalone.jar')]
    else:
        svarog_path = (os.path.join(this_folder, '..', 'svarog', 'svarog.exe'),)

    def svarog_thread_target():
        svarog = subprocess.Popen(svarog_path)
        svarog.wait()
        os.kill(os.getpid(), signal.SIGTERM)

    svarog_thread = threading.Thread(target=svarog_thread_target, name="svarog_launcher_thread")
    svarog_thread.daemon = True
    svarog_thread.start()
    hide_my_windows()
    svarog_thread.join()


def check_upgrades():
    # this file was suposed to be self contained, but now it's overgrowing.... need to refactor and merge with linux launcher maybe?
    from braintech.obci.experiment.error_reporting import get_svarog_streamer_or_svarog_lab_version
    import urllib3
    import os
    from PySide2.QtWidgets import QApplication, QMessageBox

    name, version = get_svarog_streamer_or_svarog_lab_version()
    version = version.replace('-', '.').replace('+', '.')
    http = urllib3.PoolManager()
    try:
        r = http.request('GET', 'https://braintech.pl/pliki/svarog/svarog-streamer/version.txt')
    except:
        return
    version_remote = r.data.decode().replace('-', '.').replace('+', '.').strip()
    annoyance_check_file = os.path.expanduser(os.path.join('~', '.obci', 'svaog-streamer-version-remote.txt'))

    if version_remote == version:
        return

    if os.path.exists(annoyance_check_file):
        with open(annoyance_check_file) as f:
            if f.read().strip() == version_remote:
                return

    app = QApplication([])

    language = os.environ.get('LANGUAGE', 'en').lower()
    if not language:
        language = 'en'
    lines = {'pl': ['Dostępna jest nowa wersja {} oprogramowania Svarog-streamer. Bieżąca wersja {}\n'
                    'Czy chcesz zainstalować nową wersję?'.format(version_remote, version),
                    'Tak',
                    'Nie',
                    'Nie dla tej wersji',
                    'Proszę zamknąć Svaroga przed instalacją nowej wersji'],
             'en': ['A new  version of Svarog streamer is available: {}. Current version {}\n'
                    'Do you want to upgrade?'.format(version_remote, version),
                    'Yes',
                    'No',
                    'Skip this version',
                    'Please close Svarog before upgrading']
             }
    msg = QMessageBox()
    msg.setText(lines[language][0])
    msg.setWindowTitle("Svarog-Streamer")

    msg.addButton(lines[language][1], QMessageBox.YesRole)
    msg.addButton(lines[language][2], QMessageBox.NoRole)
    msg.addButton(lines[language][3], QMessageBox.RejectRole)

    msg.exec_()
    clicked = msg.clickedButton().text()

    if clicked == lines[language][3]:
        f = open(annoyance_check_file, 'w')
        f.write(version_remote)
        f.close()
        return
    elif clicked == lines[language][2]:
        return
    elif clicked == lines[language][1]:
        QMessageBox.warning(None, 'Info', lines[language][4])
        import webbrowser
        webbrowser.open('braintech.pl/software/svarog-streamer')
        sys.exit()


def init_obci_settings_path():
    if getattr(sys, 'frozen', False) and sys.platform == 'win32' or True:
        this_folder = getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(__file__)))
        import winreg
        import win32gui
        import win32con
        import pywintypes
        root_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment', 0, winreg.KEY_READ)
        [path, regtype] = (winreg.QueryValueEx(root_key, "Path"))
        winreg.CloseKey(root_key)
        print(path)
        this_folder_in_path = (this_folder in path.split(';'))
        print("This folder in path?", this_folder_in_path)
        if not this_folder_in_path:
            root_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                      r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment', 0,
                                      winreg.KEY_WRITE)
            new_path = '{};{}'.format(path.strip(';'), this_folder)
            print("New system path:", new_path)
            winreg.SetValueEx(root_key, "Path", 0, winreg.REG_SZ, new_path)
            winreg.CloseKey(root_key)
            
            # notify the system about the changes
            print("Notifying system about env change")
            SMTO_NOTIMEOUTIFNOTHUNG = 8
            TIMEOUT = 100  # ms
            try:
                win32gui.SendMessageTimeout(win32con.HWND_BROADCAST, win32con.WM_SETTINGCHANGE, 0,
                                            'Environment', SMTO_NOTIMEOUTIFNOTHUNG, TIMEOUT)
            except pywintypes.error:
                pass # one of the windows was taking too long to respond to the env update message, but it's ok

            print("Done")

        from braintech.obci.experiment.apps.init_settings.init_settings_app import run_settings_init
        run_settings_init()

def start_tray():
    hide_my_windows()
    from braintech.obci.experiment.apps.obci_tray.obci_tray_app import run_obci_tray
    run_obci_tray()

def launch_p300(*args):
    print("Launching, please wait")
    from obci_demo.entrypoint import run
    hide_my_windows()
    run()
    sys.exit()


if __name__ == '__main__':
    # Some hackery required for pyInstaller
    if getattr(sys, 'frozen', False) and sys.platform == 'darwin':
        os.environ['QTWEBENGINEPROCESS_PATH'] = os.path.normpath(os.path.join(
            sys._MEIPASS, 'PySide2', 'Qt', 'lib',
            'QtWebEngineCore.framework', 'Helpers', 'QtWebEngineProcess.app',
            'Contents', 'MacOS', 'QtWebEngineProcess'
        ))
    multiprocessing.freeze_support()
    if len(sys.argv) < 2:
        print("Available subcomands: --tray - simple obci server for svarog,\n"
              "svarog - running svarog, p300 - runs p300 binary communicator.")
        if sys.platform == 'darwin':
            show_selection_screen_mac()
        sys.exit()
    elif sys.argv[0] == 'obci_run_peer':
        hide_my_windows()
        from braintech.obci.experiment.cmd import obci_run_peer
        obci_run_peer.run()
        sys.exit()
    elif sys.argv[1] == 'svarog':
        launch_svarog()

    elif sys.argv[1] == 'init':
        hide_my_windows()
        init_obci_settings_path()

    elif sys.argv[1] == 'p300':
        launch_p300()

    elif sys.argv[1] == '--tray':
        hide_my_windows()
        check_upgrades()
        p = multiprocessing.Process(target=start_tray)
        p.start()
        p.join()

    else:
        sys.argv.pop(0)
        from braintech.obci.experiment.cmd.obci_lsl_stream import run_lsl_streaming_app
        run_lsl_streaming_app(sys.argv)



