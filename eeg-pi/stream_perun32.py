"""Stream an OBCI amplifier (e.g. Perun32) to LSL *with electrode impedance*.

Why this exists
---------------
The stock ``obci_lsl_stream`` command has a ``-i / --send-impedance`` flag,
but on its own it never turns the amplifier's impedance *measurement* on.
So with the stock tool the impedance columns are either absent or empty.

This launcher reuses all of the stock streaming code but flips
``amp.measure_impedance = True`` before sampling starts, and forces the
LSL stream to include the impedance channels. Everything else (channel
selection, sampling rate, stream name) works exactly like
``obci_lsl_stream``.

Usage (identical args to obci_lsl_stream, minus the -i flag which is
implied):

    python stream_perun32.py --list
    python stream_perun32.py -a "Perun32 9" -n Perun32 -s 500
    python stream_perun32.py -a "Perun32 9" -n Perun32 -s 500 -c ExG_1 ExG_2

Each EEG channel gets a matching ``<name>_impedance`` channel (in ohms)
appended after the signal channels. Ctrl-C to stop.
"""

import sys

from braintech.obci.experiment.driver_utils.obci_to_lsl_streamer import (
    AmplifierStreamingApp,
    ObciLslStreamerException,
)
from braintech.obci.experiment.error_reporting import install_sentry


class ImpedanceStreamingApp(AmplifierStreamingApp):
    def _stream_amp(self, amp, channels, sampling_rate, name, send_impedance):
        # Turn impedance measurement ON in the driver itself. Without this
        # the channels stay flagged UNKNOWN and no impedance is produced.
        if hasattr(amp, "measure_impedance"):
            amp.measure_impedance = True
        # Force the LSL stream to actually carry the impedance channels,
        # so the user doesn't have to remember a flag.
        return super()._stream_amp(amp, channels, sampling_rate, name, True)


def main(argv=None):
    install_sentry()
    app = ImpedanceStreamingApp()
    exit_error = ""
    try:
        app.parse_args_and_run_stream(args=argv)
    except ObciLslStreamerException as e:
        exit_error = str(e)
    except KeyboardInterrupt:
        print("\nStopping stream")
    if exit_error:
        print("\nError while starting streaming!", file=sys.stderr)
        print(exit_error, file=sys.stderr)
        sys.exit(151)


if __name__ == "__main__":
    main(sys.argv[1:])
