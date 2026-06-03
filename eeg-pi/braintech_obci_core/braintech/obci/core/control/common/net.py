# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import logging
import os
import socket
import threading
import time

from braintech.obci.core.conf import settings

LOCAL_IP = '127.0.0.1'

logger = logging.getLogger(__name__)


def is_net_address(addr):
    return (not addr.startswith('ipc')
            and not addr.startswith('inproc'))


def is_local(address):
    return (address.startswith('tcp://localhost')
            or address.startswith('tcp://0.0.0.0')
            or address.startswith('tcp://127.0.0.1'))


def filter_local(addrs, ip=False):
    result = []
    if not ip:
        result = [a for a in addrs
                  if a.startswith('ipc://')]
    if not result:
        result += [a for a in addrs
                   if is_local(a)]
    return result


def filter_not_local(addresses):
    result = [a for a in addresses
              if a.startswith('tcp://')
              and not a.startswith('tcp://' + LOCAL_IP)
              and not a.startswith('tcp://localhost')]
    return result


def choose_addr(addr_list):
    not_local = filter_not_local(addr_list)
    if not_local:
        return not_local[0]
    else:
        local = filter_local(addr_list)
        if local:
            return local[0]
        else:
            return None


def get_external_ip(peer_ip=None):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    peer_ip = peer_ip or 'google.com'
    try:
        s.connect((peer_ip, 9))
        client_ip = s.getsockname()[0]
    except socket.error as e:
        logger.error('get_external_ip(peer_ip: {0}):  {1}'.format(peer_ip, e))
        client_ip = LOCAL_IP
    del s
    return client_ip


def server_address(sock_type='rep', local=False, peer_ip=None):
    if sock_type == 'rep':
        # this should not be changed
        # we can make obci server subnets by changing broadcast port
        port = server_rep_port()
    else:
        port = server_pub_port()
    if local:
        ip = LOCAL_IP
    else:
        ip = get_external_ip(peer_ip=peer_ip)
    return 'tcp://' + ip + ':' + str(port)


def port(addr_string):
    parts = addr_string.rsplit(':', 1)
    if len(parts) < 2:
        return None
    maybe_port = parts[-1]
    try:
        port = int(maybe_port)
    except ValueError:
        return None
    else:
        return port


def is_ip(addr_string):
    parts = addr_string.rsplit(':', 1)
    if len(parts) < 2:
        return False
    nums = parts[0].split('.')
    start = nums[0]
    ind = nums[0].find('://')
    if ind > -1:
        start = start[ind + 3:]
        nums[0] = start
    if len(nums) < 4:
        return False
    for p in nums:
        try:
            int(p)
        except Exception:
            return False
    return True


def server_pub_port() -> str:
    """
    :return: pub port of OBCI server, string
    """
    return str(settings.pub_port)


def server_rep_port() -> str:
    """
    :return: rep port of OBCI server, string
    """
    return str(settings.rep_port)


def gethostname():
    return os.environ.get('OBCI_HOSTNAME', socket.gethostname())


def is_addr_connectable(addr, machine):
    return machine == gethostname() or (is_ip(addr) and not is_local(addr))


class DNS:
    def __init__(self, allowed_silence_time=45, logger=None):
        self.__lock = threading.RLock()
        self.__servers = {}
        self.logger = logger or logging.getLogger('dns')
        self.allowed_silence = allowed_silence_time

    def tcp_rep_addr(self, hostname=None, ip=None, uuid=None):
        srv = self._match_srv(hostname, ip, uuid)
        return 'tcp://' + srv.ip + ':' + str(srv.rep_port)

    def _match_srv(self, hostname=None, ip=None, uuid=None):
        matches = []
        if hostname is not None:
            matches = self.__query('hostname', hostname)
        elif ip is not None:
            matches = self.__query('ip')
        elif uuid is not None:
            with self.__lock:
                matches = [self.__servers[uuid]]
        if not matches:
            raise Exception('Match not found')
        if len(matches) > 1:
            raise Exception('More than one match for given params: hostname: {0}, ip: {1}, '
                            ' uuid: {2} --- {3}'.format(hostname, ip, uuid, matches))
        return matches.pop()

    def __query(self, attribute, value):
        matches = []
        with self.__lock:
            for srv in self.__servers.values():
                if getattr(srv, 'hostname') == value:
                    matches.append(srv)
        return matches

    def http_addr(self, hostname=None, ip=None, uuid=None):
        srv = self._match_srv(hostname, ip, uuid)
        return srv.ip + ':' + srv.http_port

    def hostname(self, ip=None, uuid=None):
        srv = self._match_srv(ip=ip, uuid=uuid)
        return srv.hostname

    def ip(self, hostname=None, uuid=None):
        srv = self._match_srv(hostname=hostname, uuid=uuid)
        return srv.ip

    def this_addr_local(self):
        return gethostname()

    def this_addr_network(self):
        try:
            srv = self._match_srv(hostname=gethostname())
        except Exception:
            return gethostname()
        else:
            return srv.ip

    def is_this_machine(self, address):
        addr = address
        if address.startswith('tcp://'):
            addr = addr[6:]
        parts = addr.split(':')
        if len(parts) > 0:
            addr = parts[0]
        return (addr == self.this_addr_network()
                or addr == self.this_addr_local())

    def update(self, ip, hostname, uuid, rep_port, pub_port, http_port=None):
        with self.__lock:
            old = self.__servers.get(uuid, None)
            new = self.__servers[uuid] = PeerNetworkDescriptor(
                ip,
                hostname,
                uuid,
                rep_port,
                pub_port,
                http_port,
            )
        changed = old is None
        if not changed:
            changed = old.ip != new.ip or old.hostname != new.hostname
        return changed

    def mass_update(self, server_dict):
        with self.__lock:
            self.__servers = {}
            for uid in server_dict:
                self.__servers[uid] = PeerNetworkDescriptor(**server_dict[uid])

    def clean_silent(self):
        changed = False
        with self.__lock:
            check_time = time.time()
            for uid in list(self.__servers.keys()):
                srv = self.__servers[uid]
                if srv.timestamp + self.allowed_silence < check_time:
                    changed = True
                    self.logger.warning('obci_server on ' + str(srv.ip) + '   '
                                        + srv.hostname + ' is most probably down.')
                    del self.__servers[uid]
        return changed

    def snapshot(self):
        snapshot = {}
        with self.__lock:
            for uid in self.__servers.keys():
                snapshot[uid] = self.__servers[uid]._copy()
        return snapshot

    def dict_snapshot(self):
        snapshot = {}
        with self.__lock:
            for uid in self.__servers.keys():
                snapshot[uid] = self.__servers[uid].as_dict()
        return snapshot

    def copy(self):
        new = DNS()
        new.allowed_silence = self.allowed_silence
        new.mass_update(self.dict_snapshot())
        return new


class PeerNetworkDescriptor:
    def __init__(self, ip, hostname, uuid, rep_port,
                 pub_port, http_port=None, timestamp=None):
        self.ip = ip
        self.hostname = hostname
        self.uuid = uuid
        self.rep_port = rep_port
        self.pub_port = pub_port
        self.http_port = http_port
        self.timestamp = timestamp if timestamp is not None else time.time()

    def __str__(self):
        return str(self.as_dict())

    def _copy(self):
        desc = PeerNetworkDescriptor(
            self.ip,
            self.hostname,
            self.uuid,
            self.rep_port,
            self.pub_port,
            self.http_port,
            self.timestamp,
        )
        return desc

    def as_dict(self):
        # dumb
        return dict(vars(self))
