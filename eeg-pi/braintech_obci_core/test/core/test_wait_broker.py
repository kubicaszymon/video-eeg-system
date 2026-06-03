# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import time

import pytest

from braintech.obci.core.broker.peer import Peer
from braintech.obci.core.broker.broker import Broker
from braintech.obci.core.broker.peer import PeerInitUrls
from braintech.obci.core.utils import wait_until_peers_ready


@pytest.mark.timeout(30)
def run_connection_test(broker_rep,
                        broker_xpub,
                        broker_xsub,
                        peer_pub,
                        peer_rep):

    urls = PeerInitUrls(pub_urls=[peer_pub],
                        rep_urls=[peer_rep],
                        broker_rep_url=broker_rep)
    peer = Peer(urls, '1')

    time.sleep(2.0)

    broker = Broker(None, [broker_rep], [broker_xpub], [broker_xsub])

    wait_until_peers_ready([broker, peer])

    peer.shutdown()
    broker.shutdown()


def test_wait_for_broker():
    params = {
        'broker_rep': 'tcp://127.0.0.1:20001',
        'broker_xpub': 'tcp://127.0.0.1:20002',
        'broker_xsub': 'tcp://127.0.0.1:20003',
        'peer_pub': 'tcp://127.0.0.1:*',
        'peer_rep': 'tcp://127.0.0.1:*'
    }
    run_connection_test(**params)
    print('test finished')
