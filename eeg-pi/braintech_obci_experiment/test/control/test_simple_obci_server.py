# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved

from braintech.obci.experiment import messages


def test_obci_server_capabilities(simple_obci_server):
    msg = messages.OBCIServerCapabilitiesReq()
    response, details = simple_obci_server.server_req(msg)
    assert isinstance(response, messages.OBCIServerCapabilities)
    assert response.capabilities == ['online_amplifiers']
