# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import random
import time

import pytest
import zmq
from braintech.obci.core.broker import messages
from braintech.obci.core.broker.peer import Peer, PeerInitUrls
from braintech.obci.core.broker.broker import Broker
from braintech.obci.core.utils import wait_until_peers_ready, wait_for_condition


class _TestMsg(messages.BaseMessage):
    pass


class _TestResponseMsg(messages.BaseMessage):
    pass


class _A(messages.BaseMessage):
    pass


class _B(messages.BaseMessage):
    pass


class PeerWithMsgHistory(Peer):

    def __init__(self, urls, peer_id, **kwargs):
        super().__init__(urls, peer_id, **kwargs)
        self.received_messages = []
        self.register_message_handler(_TestMsg, self.handle_test_msg)

    async def handle_test_msg(self, msg):
        self.received_messages.append(msg)
        if isinstance(msg, _TestMsg):
            return _TestResponseMsg(sender=self._id)
        else:
            return messages.InvalidRequest(sender=self._id, data='message type not recognized')


class SingleMessageSenderTestPeer(Peer):

    def __init__(self, urls, peer_id, msg_to_send, messages_count=1, **kwargs):
        super().__init__(urls, peer_id, **kwargs)
        self.msg_to_send = msg_to_send(self.id)
        self.messages_count = messages_count
        self.sent_messages_count = 0

    async def send_messages(self):
        for _ in range(self.messages_count):
            self.send_message(self.msg_to_send)
            print("SEND_MESSAGES", self.id)
            self.sent_messages_count += 1


class SingleMessageReceiverTestPeer(Peer):

    def __init__(self, urls, peer_id, msg_to_receive, **kwargs):
        super().__init__(urls, peer_id, **kwargs)
        self.msg_to_receive = msg_to_receive
        self.received_messages_count = 0
        self.register_message_handler(msg_to_receive, self.handle_test_message)

    async def _connections_established(self):
        self.subscribe(self.msg_to_receive)
        await super()._connections_established()

    async def handle_test_message(self, msg):
        if isinstance(msg, self.msg_to_receive):
            self.received_messages_count += 1


@pytest.mark.timeout(30)
def run_connection_test(broker_rep,
                        broker_xpub,
                        broker_xsub,
                        peer_pub,
                        peer_rep):
    broker = Broker(None, [broker_rep], [broker_xpub], [broker_xsub])

    urls = PeerInitUrls(pub_urls=[peer_pub],
                        rep_urls=[peer_rep],
                        broker_rep_url=broker_rep)
    peer = Peer(urls, 1)

    wait_until_peers_ready([broker, peer])

    peer.shutdown()
    broker.shutdown()


@pytest.mark.timeout(30)
def run_connection_test_2(broker_rep,
                          broker_xpub,
                          broker_xsub,
                          peer_pub,
                          peer_rep):
    broker = Broker(None, [broker_rep], [broker_xpub], [broker_xsub])

    urls = PeerInitUrls(pub_urls=[peer_pub],
                        rep_urls=[peer_rep],
                        broker_rep_url=broker_rep)
    peer1 = Peer(urls, '1')
    peer2 = Peer(urls, '2')

    wait_until_peers_ready([broker, peer1, peer2])

    peer1.shutdown()
    peer2.shutdown()
    broker.shutdown()


def test_connection_with_specified_port():
    params = {
        'broker_rep': 'tcp://127.0.0.1:20001',
        'broker_xpub': 'tcp://127.0.0.1:20002',
        'broker_xsub': 'tcp://127.0.0.1:20003',
        'peer_pub': 'tcp://127.0.0.1:20004',
        'peer_rep': 'tcp://127.0.0.1:20005'
    }
    run_connection_test(**params)


def test_connection_with_any_port():
    params = {
        'broker_rep': 'tcp://127.0.0.1:20001',
        'broker_xpub': 'tcp://127.0.0.1:20002',
        'broker_xsub': 'tcp://127.0.0.1:20003',
        'peer_pub': 'tcp://127.0.0.1:*',
        'peer_rep': 'tcp://127.0.0.1:*'
    }
    run_connection_test(**params)


def test_connection_with_two_peers():
    params = {
        'broker_rep': 'tcp://127.0.0.1:20001',
        'broker_xpub': 'tcp://127.0.0.1:20002',
        'broker_xsub': 'tcp://127.0.0.1:20003',
        'peer_pub': 'tcp://127.0.0.1:*',
        'peer_rep': 'tcp://127.0.0.1:*'
    }
    run_connection_test_2(**params)


def test_message_receiving():
    broker_rep = 'tcp://127.0.0.1:20001'
    broker_xpub = 'tcp://127.0.0.1:20002'
    broker_xsub = 'tcp://127.0.0.1:20003'

    peer_pub_urls = [
        'tcp://127.0.0.1:20100', 'tcp://127.0.0.1:20101',
        'tcp://127.0.0.1:20102', 'tcp://127.0.0.1:20103'
    ]
    peer_rep_urls = [
        'tcp://127.0.0.1:20200', 'tcp://127.0.0.1:30201',
        'tcp://127.0.0.1:20202', 'tcp://127.0.0.1:30203'
    ]

    broker = Broker(None, [broker_rep], [broker_xpub], [broker_xsub])

    urls = PeerInitUrls(pub_urls=peer_pub_urls,
                        rep_urls=peer_rep_urls,
                        broker_rep_url=broker_rep)
    peer = PeerWithMsgHistory(urls, '1')
    peer._heartbeat_enabled = False

    wait_until_peers_ready([broker, peer])

    ctx = zmq.Context()

    sub_sockets = [ctx.socket(zmq.SUB) for _ in range(len(peer_pub_urls))]
    req_sockets = [ctx.socket(zmq.REQ) for _ in range(len(peer_rep_urls))]

    # test async

    for url, sub in zip(peer_pub_urls, sub_sockets):
        sub.connect(url)
        sub.subscribe(b'')

    async def send_test_messages():
        print('Sending test message')
        peer.send_message(_TestMsg(sender='1'))

    time.sleep(0.1)

    peer.create_task(send_test_messages())

    time.sleep(0.5)

    for url, sub in zip(peer_pub_urls, sub_sockets):
        msg = sub.recv_multipart()
        msg = messages.deserialize(msg)
        assert isinstance(msg, _TestMsg)
        assert msg.sender == '1'
        sub.disconnect(url)

    # test sync

    for url, req in zip(peer_rep_urls, req_sockets):
        req.connect(url)
        req.send_multipart(_TestMsg(sender='1').serialize())
        replay = req.recv_multipart()
        msg = messages.deserialize(replay)
        assert isinstance(msg, _TestResponseMsg)
        req.disconnect(url)

    # shutdown

    for sub in sub_sockets:
        sub.close(linger=0)
    for req in req_sockets:
        req.close(linger=0)
    ctx.destroy()

    peer.shutdown()
    broker.shutdown()


def test_many_peers():
    broker_rep = 'tcp://127.0.0.1:20001'
    broker_xpub = 'tcp://127.0.0.1:20002'
    broker_xsub = 'tcp://127.0.0.1:20003'

    peer_pub = 'tcp://127.0.0.1:*'
    peer_rep = 'tcp://127.0.0.1:*'

    msgs_count_a = 5
    msgs_count_b = 5

    broker = Broker(None, [broker_rep], [broker_xpub], [broker_xsub])

    msg_to_send = msgs_count_a * [_A] + msgs_count_b * [_B]
    random.shuffle(msg_to_send)

    id_counter = 1

    urls = PeerInitUrls(pub_urls=[peer_pub],
                        rep_urls=[peer_rep],
                        broker_rep_url=broker_rep)

    peers_receive_a = []
    for _ in range(msgs_count_a):
        peers_receive_a.append(SingleMessageReceiverTestPeer(urls, "receive_a_%d" % id_counter, msg_to_receive=_A))
        id_counter += 1

    peers_receive_b = []
    for _ in range(msgs_count_b):
        peers_receive_b.append(SingleMessageReceiverTestPeer(urls, "receive_b_%d" % id_counter, msg_to_receive=_B))
        id_counter += 1

    peers_senders = []
    for msg in msg_to_send:
        peers_senders.append(SingleMessageSenderTestPeer(
            urls, "sender_%s_%d" % (msg.__TYPE__, id_counter), msg_to_send=msg))
        id_counter += 1

    all_peers = tuple(peers_receive_a + peers_receive_b + peers_senders)

    wait_until_peers_ready([broker] + list(all_peers))

    for peer in peers_senders:
        peer.create_task(peer.send_messages())

    wait_for_condition(lambda: peers_receive_b[-1].received_messages_count == msgs_count_b,
                       timeout=5)
    wait_for_condition(lambda: peers_receive_a[-1].received_messages_count == msgs_count_a,
                       timeout=5)

    for peer in all_peers:
        peer.shutdown()

    broker.shutdown()

    for peer in peers_senders:
        assert peer.sent_messages_count == 1

    for peer in peers_receive_a:
        assert peer.received_messages_count == msgs_count_a

    for peer in peers_receive_b:
        assert peer.received_messages_count == msgs_count_b


def test_autostart_autoshutdown_peer(broker):  # noqa: F811

    peer = Peer(broker.broker_ip, autostart=False, autoshutdown=False)
    peer._heartbeat_enabled = False

    wait_until_peers_ready([broker, peer])
    assert peer.is_ready
    print("READY")
    broker.send_message(messages.PeerControlMessage(peer_id=peer.id, action='start'))
    wait_for_condition(condition_func=lambda: peer.is_running, sleep_duration=0.05)
    broker.send_message(messages.PeerControlMessage(peer_id=peer.id, action='stop'))
    wait_for_condition(condition_func=lambda: peer.is_ready, sleep_duration=0.05)
    peer.shutdown()
