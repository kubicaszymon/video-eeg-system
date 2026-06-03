# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
import socket

import numpy as np

from braintech.drivers.perun32.device import PerunAmp32Device
from braintech.drivers.double_amplifier.event_tag_sender import EventTagSender, PORT
from braintech.obci.signal_processing.signal.containers import SamplePacket


def test_event_tag_sender(mocker):
    peer = mocker.Mock()
    tag_sender = EventTagSender(peer, ['Events', 'Timestamp_0', 'Timestamp_1'])
    try:
        ts = 0

        def _create_packet(samples):
            nonlocal ts

            packet = SamplePacket(ts=np.array([ts + i for i in range(len(samples))]),
                                  samples=np.array(samples))
            ts += len(samples)
            return packet

        events = 0
        ts1 = 1
        ts2 = 1
        tag_sender.send_events(_create_packet([[0, ts1, ts1], [0, ts1 + 1, ts2 + 1]]))
        ts1 += 1
        ts2 += 1
        peer.send_message.assert_not_called()
        events = PerunAmp32Device.EVENT_RIN1
        tag_sender.send_events(_create_packet([[events, ts1, ts2], [events, ts1, ts2]]))
        assert peer.send_message.call_count == 3
        tag_sender.send_events(_create_packet([[events, ts1, ts2], [events, ts1, ts2]]))
        assert peer.send_message.call_count == 3
        ts1 += 1
        ts2 += 1
        tag_sender.send_events(_create_packet([[events, ts1, ts2]]))
        assert peer.send_message.call_count == 5
        ts1 += 1
        ts2 += 1
        events |= PerunAmp32Device.EVENT_RIN2
        tag_sender.send_events(_create_packet([[events, ts1, ts2]]))
        assert peer.send_message.call_count == 6
        ts1 += 1
        ts2 += 1
        events = 0
        tag_sender.send_events(_create_packet([[events, ts1, ts2]]))
        assert peer.send_message.call_count == 8
    finally:
        tag_sender.stop()


def test_socket(mocker):
    peer = mocker.Mock()
    tag_sender = EventTagSender(peer, ['Events', 'Timestamp_0', 'Timestamp_1'])
    try:
        for i in range(50):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect(("127.0.0.1", PORT))
                s.sendall(b"hello")
                data = s.recv(1024)
            assert data == b'OK'

        assert peer.send_message.call_count == 50
    finally:
        tag_sender.stop()
