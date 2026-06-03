#!/usr/bin/env python3
# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import zmq

import braintech.obci.experiment.common.message

SEND = 1000000


class ZMQTester:

    def __init__(self):
        self.ctx = zmq.Context()
        self.pull = self.ctx.socket(zmq.PULL)
        self.pull.bind('tcp://*:16789')
        self.pull.setsockopt(zmq.LINGER, 0)

    def test(self):
        print("zmq client --- start receiving")
        received = 0
        for i in range(SEND):
            msg = braintech.obci.experiment.common.message.recv_msg(self.pull)
            if int(msg):
                # prev = int(msg)
                received += 1
            if received % 10000 == 0:
                print("zmq: received ", received, "messages, last: ", msg)

        if received == SEND:
            print("zmq: OK")
        else:
            print("OHHHH NOOOOOOOOO :( :( :( :( :(", received)
        self.pull.close()

        print("zmq: finished.")


if __name__ == '__main__':
    t = ZMQTester()
    t.test()
