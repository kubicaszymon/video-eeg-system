from braintech.drivers.perun32.device import PerunAmp32Device
from braintech.obci.core.drivers.eeg.eeg_amplifier import AmplifierDescription, ChannelDescription
# 0.43 volts per per bits * 1e6 to get microvolts
from braintech.obci.signal_processing.signal.containers import Impedance

PERUNAMP_GAIN = (0.43 / (1 << 24)) * 1e6

DESCRIPTION_TABLE = {

    'old': AmplifierDescription(
        name="Perun32",
        sampling_rates=PerunAmp32Device.SAMPLING_RATES,
        channels=([ChannelDescription(name="ExG_%d" % (i + 1),
                                      gain=PERUNAMP_GAIN,
                                      offset=-30.0,
                                      filters=[],
                                      impedance=Impedance.UNKNOWN,
                                      bit_length=24,
                                      exp=-6,
                                      is_signed=True
                                      ) for i in range(24)] +
                  [ChannelDescription(name="AUX_%d" % (i + 1),
                                      gain=PERUNAMP_GAIN,
                                      offset=-60.0,
                                      filters=[],
                                      impedance=Impedance.UNKNOWN,
                                      bit_length=24,
                                      exp=-6,
                                      is_signed=True
                                      ) for i in range(8)] +

                  [ChannelDescription(name="Events",
                                      impedance=Impedance.NOT_APPLICABLE,
                                      bit_length=5,
                                      exp=1,
                                      is_signed=False,
                                      ),
                   ])
    ),

    'a': AmplifierDescription(
        name="Perun32 A",
        sampling_rates=PerunAmp32Device.SAMPLING_RATES,
        channels=([ChannelDescription(name="ExG_%d" % (i + 1),
                                      gain=PERUNAMP_GAIN,
                                      offset=-30.0,
                                      filters=[],
                                      impedance=Impedance.UNKNOWN,
                                      bit_length=24,
                                      exp=-6,
                                      is_signed=True
                                      ) for i in range(23)] +
                  [ChannelDescription(name="AUX_%d" % (i + 1),
                                      gain=PERUNAMP_GAIN,
                                      offset=-60.0,
                                      filters=[],
                                      impedance=Impedance.UNKNOWN,
                                      bit_length=24,
                                      exp=-6,
                                      is_signed=True
                                      ) for i in range(7)] +
                  [ChannelDescription(name="GSR",
                                      gain=PERUNAMP_GAIN,
                                      offset=-60.0,
                                      filters=[],
                                      impedance=Impedance.NOT_APPLICABLE,
                                      bit_length=24,
                                      exp=-6,
                                      is_signed=True
                                      )] +
                  [ChannelDescription(name="Events",
                                      impedance=Impedance.NOT_APPLICABLE,
                                      bit_length=5,
                                      exp=1,
                                      is_signed=False,
                                      ),
                   ])
    ),

    'b': AmplifierDescription(
        name="Perun32 B",
        sampling_rates=PerunAmp32Device.SAMPLING_RATES,
        channels=([ChannelDescription(name="ExG_%d" % (i + 1),
                                      gain=PERUNAMP_GAIN,
                                      offset=-30.0,
                                      filters=[],
                                      impedance=Impedance.UNKNOWN,
                                      bit_length=24,
                                      exp=-6,
                                      is_signed=True
                                      ) for i in range(24)] +
                  [ChannelDescription(name="AUX_%d" % (i + 1),
                                      gain=PERUNAMP_GAIN,
                                      offset=-60.0,
                                      filters=[],
                                      impedance=Impedance.UNKNOWN,
                                      bit_length=24,
                                      exp=-6,
                                      is_signed=True
                                      ) for i in range(7)] +
                  [ChannelDescription(name="GSR",
                                      gain=PERUNAMP_GAIN,
                                      offset=-60.0,
                                      filters=[],
                                      impedance=Impedance.NOT_APPLICABLE,
                                      bit_length=24,
                                      exp=-6,
                                      is_signed=True
                                      )] +
                  [ChannelDescription(name="Events",
                                      impedance=Impedance.NOT_APPLICABLE,
                                      bit_length=5,
                                      exp=1,
                                      is_signed=False,
                                      ),
                   ])
    ),

    'c': AmplifierDescription(
        name="Perun32 C",
        sampling_rates=PerunAmp32Device.SAMPLING_RATES,
        channels=([ChannelDescription(name="ExG_%d" % (i + 1),
                                      gain=PERUNAMP_GAIN,
                                      offset=-30.0,
                                      filters=[],
                                      impedance=Impedance.UNKNOWN,
                                      bit_length=24,
                                      exp=-6,
                                      is_signed=True
                                      ) for i in range(24)] +
                  [ChannelDescription(name="AUX_%d" % (i + 1),
                                      gain=PERUNAMP_GAIN,
                                      offset=-60.0,
                                      filters=[],
                                      impedance=Impedance.UNKNOWN,
                                      bit_length=24,
                                      exp=-6,
                                      is_signed=True
                                      ) for i in range(8)] +

                  [ChannelDescription(name="Events",
                                      impedance=Impedance.NOT_APPLICABLE,
                                      bit_length=5,
                                      exp=1,
                                      is_signed=False,
                                      ),
                   ])
    ),

    'd': AmplifierDescription(
        name="Perun32 D",
        sampling_rates=PerunAmp32Device.SAMPLING_RATES,
        channels=([ChannelDescription(name="ExG_%d" % (i + 1),
                                      gain=PERUNAMP_GAIN,
                                      offset=-30.0,
                                      filters=[],
                                      impedance=Impedance.UNKNOWN,
                                      bit_length=24,
                                      exp=-6,
                                      is_signed=True
                                      ) for i in range(24)] +
                  [ChannelDescription(name="AUX_%d" % (i + 1),
                                      gain=PERUNAMP_GAIN,
                                      offset=-60.0,
                                      filters=[],
                                      impedance=Impedance.UNKNOWN,
                                      bit_length=24,
                                      exp=-6,
                                      is_signed=True
                                      ) for i in range(8)] +
                  [ChannelDescription(name="Events",
                                      impedance=Impedance.NOT_APPLICABLE,
                                      bit_length=5,
                                      exp=1,
                                      is_signed=False,
                                      ),
                   ])
    )
}
