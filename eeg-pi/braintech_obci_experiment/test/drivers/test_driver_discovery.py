# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.


import json
import pytest

import braintech.obci.experiment.driver_utils.driver_discovery


def test_driver_discovery():
    drivers = braintech.obci.experiment.driver_utils.driver_discovery.find_drivers()
    assert drivers, "At least Random Amplifier Should be available"
    try:
        json.dumps(drivers)
    except Exception:
        pytest.fail("Driver list should be serializable", True)
