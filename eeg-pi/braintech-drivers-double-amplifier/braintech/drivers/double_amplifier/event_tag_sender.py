# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
import select
import socket
import threading
from collections import OrderedDict

import numpy as np

from braintech.drivers.perun32.device import PerunAmp32Device
from braintech.obci.core.broker.messages import IncompleteTagMsg, TagMsg
from braintech.drivers.perun8._perun8 import PyAmplifierPerun8

HOST = ''
PORT = 9877


class EventTagSender:
    def __init__(self, peer, active_channels):
        self._peer = peer
        self._indexes = OrderedDict()
        self._current_tags = {}
        self._tag_id = 0
        for ch in ['Events', 'Timestamp_0', 'Timestamp_1']:
            try:
                self._indexes[ch] = active_channels.index(ch)
            except ValueError:
                pass
        self._last_samples = np.array([[0] * len(self._indexes)]).T
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(2.0)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((HOST, PORT))
        self._sock.listen(10)
        self._server = threading.Thread(target=self._socket_server, name="SocketListener", daemon=True)
        self._stop = False
        self._server.start()

    def _socket_server(self):
        while not self._stop:
            try:
                conn, addr = self._sock.accept()
            except OSError:
                continue
            except socket.timeout:
                continue
            event_name = conn.recv(1024)
            tag = TagMsg(id='socket_%s' % self._tag_id,
                         name=event_name.decode('utf-8'),
                         start_timestamp=PyAmplifierPerun8.local_clock(),
                         end_timestamp=PyAmplifierPerun8.local_clock() + 0.1)
            self._tag_id += 1
            self._peer.send_message(tag)
            conn.sendall(b"OK")
            conn.close()

    def send_events(self, packet):
        tag_signal = packet.samples[:, list(self._indexes.values())].T
        diff = np.diff(tag_signal, prepend=self._last_samples)
        self._last_samples = tag_signal[:, -1].reshape(-1, 1)
        if 'Events' in self._indexes:
            events_index = list(self._indexes.keys()).index('Events')
            for e_index in np.nonzero(diff[events_index])[0]:
                event = int(tag_signal[events_index, e_index])
                for e_name in ["RIN1", "RIN2"]:
                    if event & getattr(PerunAmp32Device, 'EVENT_' + e_name):
                        if e_name not in self._current_tags:
                            self._create_tag(e_name, packet.ts[e_index])
                    elif e_name in self._current_tags:
                        self._finish_tag(e_name, packet.ts[e_index])
        for ts_name in ['Timestamp_0', 'Timestamp_1']:
            if ts_name in self._indexes:
                ts_index = list(self._indexes.keys()).index(ts_name)
                real_diff = np.diff(diff[ts_index] == 0, prepend=[ts_name in self._current_tags])
                for idx in real_diff.nonzero()[0]:
                    if diff[ts_index, idx] == 0 and ts_name not in self._current_tags:
                        self._create_tag(ts_name, packet.ts[idx])
                    elif diff[ts_index, idx] != 0 and ts_name in self._current_tags:
                        self._finish_tag(ts_name, packet.ts[idx])

    def _create_tag(self, name, ts):
        self._tag_id += 1
        tag = IncompleteTagMsg(id='events_' + str(self._tag_id), start_timestamp=float(ts), name=name)
        self._current_tags[name] = tag
        self._peer.send_message(tag)

    def _finish_tag(self, name, ts):
        incomplete_tag = self._current_tags[name]
        tag = TagMsg(id=incomplete_tag.id,
                     start_timestamp=incomplete_tag.start_timestamp,
                     name=name,
                     end_timestamp=float(ts))
        print(tag)
        del self._current_tags[name]
        self._peer.send_message(tag)

    def stop(self):
        self._stop = True
        self._sock.close()
        self._server.join(10)

    def __del__(self):
        self.stop()
