# Perun 8 Driver — Raspberry Pi Build

Standalone C++ reader for the BrainTech Perun 8 wireless EEG headset.
Communicates with the FTDI USB dongle, outputs 8-channel EEG samples as CSV to stdout at 500 Hz.

## Prerequisites

```bash
sudo apt update
sudo apt install -y build-essential libftdi1-dev
```

## Build

```bash
make
```

This produces the `perun_reader` binary.

## Usage

```bash
# Default (first dongle found)
./perun_reader

# Specify device index (if multiple dongles)
./perun_reader 0
```

### Output format

CSV on stdout, one line per sample at 500 Hz:

```
P3,Cz,O2,P4,C3,O1,Pz,C4
12.3456,45.6789,...
```

Values are gain-adjusted, in microvolts (uV). Status/errors go to stderr.

Stop with `Ctrl+C` or `SIGTERM`.

## File structure

```
perun_reader.cpp              Main program (init amp, read samples, print CSV)
Makefile                      Build config (g++ -std=c++14 -lftdi1 -lpthread)
src/
  Amplifier.cpp/h             Base amplifier class
  AmplifierDescription.cpp/h  Amplifier metadata
  Logger.cpp/h                Logging
  Utils.cpp/h                 Utilities
  SynchronizedQueue.hpp       Thread-safe queue
  perun/
    PerunAmplifier.cpp/h      Perun 8 driver (FTDI + RF protocol)
    lib/
      FTDI_linux.h            FTDI USB communication (libftdi1)
      Msg_rf.h                RF wireless protocol messages
      ADS1299.h               ADS1299 ADC chip definitions
      uart_cmd.h              UART command protocol
      rf_proto.h              RF protocol spec
      Pkt.h                   Packet handling
      ...                     Other protocol headers
```

## Cross-compile (optional)

To cross-compile from a PC for Raspberry Pi (ARM):

```bash
sudo apt install gcc-arm-linux-gnueabihf g++-arm-linux-gnueabihf
make CXX=arm-linux-gnueabihf-g++
```

Note: you'll need ARM-built `libftdi1` on the target Pi.
