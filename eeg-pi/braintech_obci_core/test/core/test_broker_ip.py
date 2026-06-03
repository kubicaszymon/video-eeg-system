# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

from braintech.obci.core.broker.peer import Peer
from braintech.obci.core.broker.broker import Broker

from braintech.obci.core.utils import wait_until_peers_ready


def run_test(broker_ip_address,
             broker_rep,
             broker_xpub,
             broker_xsub):

    broker = Broker(broker_ip_address=broker_ip_address,
                    rep_urls=[broker_rep],
                    xpub_urls=[broker_xpub],
                    xsub_urls=[broker_xsub])

    wait_until_peers_ready([broker])

    peer = Peer(broker_ip_address, '1')

    wait_until_peers_ready([peer])

    peer.shutdown()
    broker.shutdown()


def test_query():
    params = {
        'broker_ip_address': '127.0.0.1:23821',
        'broker_rep': 'tcp://127.0.0.1:20001',
        'broker_xpub': 'tcp://127.0.0.1:20002',
        'broker_xsub': 'tcp://127.0.0.1:20003',
    }
    run_test(**params)
    print('broker ip test finished')
