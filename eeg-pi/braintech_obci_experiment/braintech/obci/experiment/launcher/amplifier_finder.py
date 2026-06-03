# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
import logging

import zmq

from braintech.obci.core.control.common import net
from braintech.obci.experiment import messages
from ..driver_utils.driver_discovery import find_drivers, find_bluetooth_amps, find_usb_amps, find_virtual_amps


def find_new_experiments_and_push_results(ctx, rq_message):
    LOGGER = logging.getLogger("eeg_AMPLIFIER_finder")

    if not rq_message.amplifier_types:
        driv = find_drivers()
    else:
        driv = []
        for amptype in rq_message.amplifier_types:
            if amptype == 'bt' or amptype == 'bluetooth':
                driv += find_bluetooth_amps()
            elif amptype == 'usb':
                driv += find_usb_amps()
            elif amptype == 'virtual':
                driv += find_virtual_amps()

    to_client = ctx.socket(zmq.PUSH)
    to_client.connect(rq_message.client_push_address)

    messages.EegAmplifiersMsg(
        sender_ip=net.gethostname(),
        amplifier_list=driv,
    ).send(to_client)
    to_client.close(-1)
    LOGGER.info("sent amplifier data for amps:%s %s", rq_message.amplifier_types,
                [d['amplifier_params']['additional_params']['amplifier_id'] for d in driv])
