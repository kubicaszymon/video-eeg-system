# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

from typing import Optional, List

import numpy

from braintech.obci.core.drivers.eeg import openbci_board
from braintech.obci.core.drivers.eeg.eeg_amplifier import (
    AmplifierDescription, ChannelDescription, EEGAmplifier, NoSamplesException
)
from braintech.obci.signal_processing.signal.data_generic_write_proxy import Impedance, SamplePacket


class OpenBciAmplifier(EEGAmplifier):
    name = "OpenBCIAmplifier"
    _eeg_channels_descriptions = [
        ChannelDescription(
            name='Ex' + str(idx + 1),
            gain=1.0,
            offset=0.0,
            type='EEG',
            impedance=Impedance.UNKNOWN,
        ) for idx in range(openbci_board.EEG_CHANNELS_PER_SAMPLE)
    ]
    _standard_channels_descriptions = [
        ChannelDescription(
            name='Ax' + str(idx + 1),
            gain=1.0,
            offset=0.0,
            type='AUX',
            impedance=Impedance.NOT_APPLICABLE,
        ) for idx in range(openbci_board.AUX_CHANNELS_PER_SAMPLE)
    ]
    _description = AmplifierDescription(
        name=name,
        sampling_rates=[openbci_board.SAMPLE_RATE],
        channels=_eeg_channels_descriptions + _standard_channels_descriptions,
    )

    @classmethod
    def get_available_amplifiers(cls, device_type: Optional[str] = None) -> List[str]:
        if device_type is None or device_type == 'usb':
            try:
                return openbci_board.OpenBciBoard.find_ports(timeout=1.0)
            except OSError:
                pass
        return []

    def __init__(self, id: Optional[str] = None):
        super().__init__(id)
        self.board = openbci_board.OpenBciBoard(port=id, timeout=2.0)
        self.stream = self.board.init_streaming()

    def _get_samples(self, samples_per_packet) -> SamplePacket:
        try:
            samples = None
            ts = numpy.zeros(samples_per_packet)
            for i in range(samples_per_packet):
                timestamp, array = next(self.stream)
                if samples is None:
                    samples = numpy.zeros([samples_per_packet, len(array)])
                ts[i] = timestamp
                samples[i] = array
            samples = self._reindex_samples(samples)
            impedance = Impedance(
                ids=self._impedance_flags,
                data=Impedance.create_empty_data(samples.shape[1])
            )
            return SamplePacket(samples=samples, ts=ts, impedance=impedance)
        except StopIteration:
            raise NoSamplesException()
