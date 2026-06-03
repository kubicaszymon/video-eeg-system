import multiprocessing
import os
import signal
import subprocess
import sys
import threading


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
    msg.setWindowTitle("Svarog-Streamer")
    msg.setText(lines[language][0])

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

def start_tray():
    import braintech.obci.experiment.cmd.obci_tray
    braintech.obci.experiment.cmd.obci_tray.run()

def run():
    if '--svarog' in sys.argv:
        run_svarog()
    elif '--tray' in sys.argv:
        check_upgrades()
        multiprocessing.set_start_method('spawn')
        p = multiprocessing.Process(target=start_tray)
        p.start()
        p.join()
    else:
        run_streamer()


def run_svarog():
    this_folder = os.path.dirname(__file__)
    svarog_path = os.path.join(this_folder, 'svarog', 'svarog.sh')

    def svarog_thread_target():
        svarog = subprocess.Popen(['bash', svarog_path])
        svarog.wait()
        os.kill(os.getpid(), signal.SIGTERM)

    svarog_thread = threading.Thread(target=svarog_thread_target, name="svarog_launcher_thread")
    svarog_thread.daemon = True
    svarog_thread.start()
    svarog_thread.join()


def run_streamer():
    from braintech.obci.experiment.cmd.obci_lsl_stream import run_lsl_streaming_app
    run_lsl_streaming_app(sys.argv[1:])
