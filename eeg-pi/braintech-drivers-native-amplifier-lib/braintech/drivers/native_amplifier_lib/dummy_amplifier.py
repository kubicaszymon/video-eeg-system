# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
from typing import List, Optional

from braintech.drivers.native_amplifier_lib.dummy_amp._dummy_amp import PyAmplifierDummy
from braintech.drivers.native_amplifier_lib.native_amplifier_base import CppEEGAmplifier


class DummyCppBaseAmplifier(CppEEGAmplifier):
    name = 'DummyCppBaseAmplifier'

    DUMMY_AMP_ID = 'CPP_DUMMY_BASE'

    @classmethod
    def get_available_amplifiers(cls, device_type: Optional[str] = None) -> List[str]:
        if device_type is None or device_type == 'virtual':
            return [cls.DUMMY_AMP_ID]  # some irrelevant name
        return []

    @classmethod
    def _get_cpp_amplifier_class(cls):
        return PyAmplifierDummy

    @classmethod
    def _id_to_params(cls, id: Optional[str] = None) -> dict:
        return {}