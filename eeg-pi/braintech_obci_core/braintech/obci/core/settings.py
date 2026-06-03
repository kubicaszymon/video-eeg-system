# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
import configparser
import importlib
import os
import socket
import warnings


SENTRY_DSN = ''


class OBCISettings:
    INSTALL_DIR = os.path.dirname(__file__)
    ENV_VAR = 'OBCI_SETTINGS'
    LOGGING = {
        'formatters': {
            'console': {
                'format': "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            },

        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'console',
                'level': 'INFO',
            },
        },
        'loggers': {
            'peer': {
                'level': 'INFO'
            },
            'launcher': {
                'level': 'INFO'
            }
        },
        'root': {
            'level': 'DEBUG',
            'handlers': ['console'],
        },
        'disable_existing_loggers': False
    }

    def __init__(self, settings_file):
        self.settings_file = os.path.expanduser(settings_file)
        self._parser = None
        self._extensions = None

    @property
    def parser(self):
        if self._parser is None:
            self._parser = self._load_parser()
            if os.path.exists(self.settings_file):
                self._parser.read([self.settings_file])
                self.save_settings()
            else:
                os.makedirs(os.path.dirname(self.settings_file), exist_ok=True)
                self.save_settings()
        return self._parser

    def _load_parser(self):
        parser = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
        parser.read_dict({
            'sentry': {
                'dsn': SENTRY_DSN,
                'reports_dir': '${logs_dir}/crash_reports',
                'site': '',
                'send_telemetry': '0',
                'gui_init_done': '0',
            },
            'dirs': {
                'home': os.path.dirname(self.settings_file),
                'sandbox': "${home}/sandbox",
                'scenario': "${home}/scenarios",
                'log': "${home}/logs",
                'search_paths': ''
            },

            'server': {
                'port': 54564,
                'pub_port': 34234,
                'rep_port': 12012,
            },
            'broker': {
                'port_range': "30000,60000",
                'peer_log_level': 'debug',
                'addresses': '0.0.0.0:31889',
            },
            'extensions': {
                'import_paths': '\n'.join([
                    'braintech.obci.experiment.peers.drivers.amplifiers',
                    'braintech.drivers.native_amplifier_lib.peers.dummy_amplifier_peer',
                    'braintech.drivers.perun8.peers.perun_amplifier_peer',
                    'braintech.drivers.tmsi.peers.tmsi_amplifier_peer',
                    'braintech.drivers.double_amplifier.double_amplifier_peer',
                    'braintech.drivers.perun32.perun32_peer',

                ])
            }
        })
        return parser

    def _path(self, section, var):
        return os.path.normpath(os.path.expanduser(self.parser.get(section, var)))

    def save_settings(self):
        with open(self.settings_file, 'w') as setting_file:
            self._parser.write(setting_file)


    @property
    def send_telemetry(self):
        return bool(int(self._path('sentry', 'send_telemetry')))

    @send_telemetry.setter
    def send_telemetry(self, telemetry):
        value = str(int(bool(telemetry)))
        self.parser.set('sentry', 'send_telemetry', value)
        self.save_settings()

    @property
    def gui_init_done(self):
        return bool(int(self._path('sentry', 'gui_init_done')))

    @gui_init_done.setter
    def gui_init_done(self, init_done):
        value = str(int(bool(init_done)))
        self.parser.set('sentry', 'gui_init_done', value)
        self.save_settings()

    @property
    def sentry_dsn(self):
        if not self.send_telemetry:
            return ''
        try:
            dsn = os.environ['OBCI_SENTRY_DSN']
            message = ('OBCI_SENTRY_DSN detected in environment variables, ignoring config file, '
                       'enabling SENTRY crash report handling using DSN:\n{}'.format(dsn))
            warnings.warn(message)
            return dsn
        except KeyError:
            pass
        dsn = self.parser.get('sentry', 'dsn', fallback=None)
        return dsn

    @property
    def sandbox_dir(self):
        return self._path('dirs', 'sandbox')

    @property
    def scenario_dir(self):
        return self._path('dirs', 'scenario')

    @property
    def log_dir(self):
        return self._path('dirs', 'log')

    @property
    def home_dir(self):
        return self._path('dirs', 'home')

    @property
    def server_port(self):
        return self.parser.getint('server', 'port')

    @property
    def broker_port_range(self):
        return [int(p) for p in self.parser.get('broker', 'port_range').split(',')]

    @property
    def broker_addresses(self):
        addrs = os.environ.get('BROKER_ADDRESSES', self.parser.get('broker', 'addresses')).split(',')
        return [(addr.split(':')[0], int(addr.split(':')[1])) for addr in addrs]

    @property
    def broker_address(self):
        first = self.broker_addresses[0]
        return "%s:%d" % (socket.gethostbyname(first[0]), first[1])

    @property
    def search_paths(self):
        search_paths_internal = []

        try:
            import braintech.obci.experiment
            path = os.path.abspath(os.path.dirname(braintech.obci.experiment.__file__))
            search_paths_internal.append(path)
        except ImportError:
            pass

        search_paths_external = self.parser.get('dirs', 'search_paths').split(';')
        paths = search_paths_internal + search_paths_external
        return paths

    @property
    def rep_port(self):
        return self.parser.getint('server', 'rep_port')

    @property
    def pub_port(self):
        return self.parser.getint('server', 'pub_port')

    @property
    def logging_config(self):
        try:
            import obci_logging_config
            logging_config = obci_logging_config.LOGGING
            logging_config['file'] = obci_logging_config.__file__
            return logging_config
        except ImportError:
            return self.LOGGING

    @property
    def module_path(self):
        return os.environ.get(self.ENV_VAR, 'braintech.obci.core.settings')

    def load_extensions(self):
        if self._extensions is None:
            import_paths = filter(None, [p.strip() for p in self.parser.get('extensions', 'import_paths').split('\n')])
            self._extensions = []
            for extension_name in import_paths:
                try:
                    module = importlib.import_module(extension_name)
                    self._extensions.append(module)
                except ImportError:
                    warnings.warn("Could not import extension module {} - not installed?".format(extension_name))


settings_class = OBCISettings
