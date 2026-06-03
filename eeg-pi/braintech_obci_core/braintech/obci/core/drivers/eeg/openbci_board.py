#!/usr/bin/env python3
# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""
Core BCI-Framework object for handling connections and samples from the board.

EXAMPLE USE:

def handle_sample(sample):
    print(sample.channels)

board = OpenBCIBoard()
board.print_register_settings()
board.start(handle_sample)

"""
import atexit
import glob
import logging
import struct
import sys
import threading
import time
import timeit

import serial

from braintech.obci.core.utils.singleton_app import SingleApplicationInstance, SingleInstanceException

SAMPLE_RATE = 250.0  # Hz
START_BYTE = 0xA0  # start of data packet
END_BYTE = 0xC0  # end of data packet
ADS1299_Vref = 4.5  # reference voltage for ADC in ADS1299. set by its hardware
ADS1299_gain = 24.0  # assumed gain setting for ADS1299. set by its Arduino code
scale_fac_uVolts_per_count = ADS1299_Vref / float(2 ** 23 - 1) / ADS1299_gain * 1000000.
scale_fac_accel_G_per_count = 0.002 / 2 ** 4  # assume set to +/4G, so 2 mG

EEG_CHANNELS_PER_SAMPLE = 8  # number of EEG channels per sample *from the board*
AUX_CHANNELS_PER_SAMPLE = 3  # number of AUX channels per sample *from the board*

'''
# Commands for in SDK http://docs.openbci.com/software/01-Open BCI_SDK:
command_stop = "s"
command_startText = "x"
command_startBinary = "b"
command_startBinary_wAux = "n"
command_startBinary_4chan = "v"
command_activateFilters = "F"
command_deactivateFilters = "g"
command_activate_channel = {"q", "w", "e", "r", "t", "y", "u", "i"}
command_activate_leadoffP_channel = {"!", "@", "#", "$", "%", "^", "&", "*"}
command_deactivate_leadoffP_channel = {"Q", "W", "E", "R", "T", "Y", "U", "I"}
command_activate_leadoffN_channel = {"A", "S", "D", "F", "G", "H", "J", "K"}
command_deactivate_leadoffN_channel = {"Z", "X", "C", "V", "B", "N", "M", "<"}
command_biasAuto = "`"
command_biasFixed = "~"
'''


class OpenBciBoard:
    CHANNEL_COMMANDS = [
        [b'1', b'2', b'3', b'4', b'5', b'6', b'7', b'8'],
        [b'!', b'@', b'#', b'$', b'%', b'^', b'&', b'*']
    ]

    def __init__(self, port=None, active_channels=None, baud=115200, filter_data=True,
                 scaled_output=True, log=True, timeout=None):
        """
        Handle a connection to an OpenBCI board.

        Args:
            port: The port to connect to.
            active_channels: Indices of active channels (from 0 to 10, inclusive) or None for all channels
            baud: The baud of the serial connection.
        """
        super().__init__()
        self.logger = logging.getLogger('openbciv3') if log else None
        self.streaming = False
        self.baudrate = baud
        self.timeout = timeout
        if not port:
            port = self.find_ports(baud, timeout, True)[0]
        self.port = port
        if self.logger:
            self.logger.debug("Connecting to V3 at port %s" % port)
        self.ser, self.lock = self.connect(port=port, baudrate=baud, timeout=timeout)
        if log:
            self.logger.debug("Serial established...")

        # Initialize 32-bit board, doesn't affect 8bit board
        self.ser.write(b'v')

        self.streaming = False
        self.filtering_data = filter_data
        self.scaling_output = scaled_output
        self.active_channels = (active_channels if active_channels is not None else
                                range(EEG_CHANNELS_PER_SAMPLE + AUX_CHANNELS_PER_SAMPLE))
        self.read_state = 0
        self.log_packet_count = 0
        self.attempt_reconnect = False
        self.last_reconnect = 0
        self.reconnect_freq = 5
        self.packets_dropped = 0

        # wait for device to be ready
        self.skip_incoming_text()

        # Disconnects from board when terminated
        atexit.register(self.disconnect)

    @staticmethod
    def connect(port, baudrate, timeout):
        lock = SingleApplicationInstance(flavor_id=port, basename='openbci_board')
        ser = serial.Serial(port=port, baudrate=baudrate, timeout=timeout)
        ser.write(b's')
        ser.close()
        time.sleep(0.5)  # ?required, hw bug
        ser = serial.Serial(port=port, baudrate=baudrate, timeout=timeout)
        return ser, lock

    def get_sample_rate(self):
        return SAMPLE_RATE

    @classmethod
    def get_eeg_channels_number(cls):
        return EEG_CHANNELS_PER_SAMPLE

    @classmethod
    def get_aux_channels_number(cls):
        return AUX_CHANNELS_PER_SAMPLE

    def init_streaming(self, lapse=-1):
        """
        Start handling streaming data from the board. Call a provided callback
        for every single sample that is processed.

        Args:
            lapse: ???
        """
        if not self.streaming:
            self.ser.write(b'b')
            self.streaming = True

        start_time = timeit.default_timer()

        # Initialize check connection
        self.check_connection()

        def generator():
            while self.streaming:
                # read current sample
                sample = self._read_serial_binary()
                if self.logger:
                    self.log_packet_count += 1
                yield sample

                if 0 < lapse < timeit.default_timer() - start_time:
                    self.stop()

        return generator()

    def _read_serial_binary(self, max_bytes_to_skip=3000):  # noqa: C901
        """
        PARSER:
        Parses incoming data packet into a tuple (timestamp, data).
        Incoming Packet Structure:
        Start Byte(1)|Sample ID(1)|Channel Data(24)|Aux Data(6)|End Byte(1)
        0xA0|0-255|8, 3-byte signed ints|3 2-byte signed ints|0xC0
        """

        def read(n):
            data = self.ser.read(n)
            if not data:
                self.warn('Device appears to be stalled. Quitting...')
                raise Exception('Device Stalled')
            else:
                return data

        log_bytes_in = ''
        channel_data = []
        aux_data = []
        packet_id = None

        timestamp = time.time()

        for rep in range(max_bytes_to_skip):
            # ---------Start Byte & ID---------
            if self.read_state == 0:
                b = read(1)
                if struct.unpack('B', b)[0] == START_BYTE:
                    if rep != 0:
                        self.warn('Skipped %d bytes before start found' % rep)
                    packet_id = struct.unpack('B', read(1))[0]  # packet id goes from 0-255
                    log_bytes_in = str(packet_id)

                    self.read_state = 1

            # ---------Channel Data---------
            elif self.read_state == 1:
                channel_data = []
                for c in range(EEG_CHANNELS_PER_SAMPLE):

                    # 3 byte ints
                    literal_read = read(3)

                    unpacked = struct.unpack('3B', literal_read)
                    log_bytes_in = log_bytes_in + '|' + str(literal_read)

                    # 3byte int in 2s compliment
                    if unpacked[0] >= 127:
                        pre_fix = bytes(bytearray.fromhex('FF'))
                    else:
                        pre_fix = bytes(bytearray.fromhex('00'))

                    literal_read = pre_fix + literal_read

                    # unpack little endian(>) signed integer(i) (makes unpacking platform independent)
                    my_int = struct.unpack('>i', literal_read)[0]

                    if self.scaling_output:
                        channel_data.append(my_int * scale_fac_uVolts_per_count)
                    else:
                        channel_data.append(my_int)

                self.read_state = 2

            # ---------Accelerometer Data---------
            elif self.read_state == 2:
                aux_data = []
                for a in range(AUX_CHANNELS_PER_SAMPLE):

                    # short = h
                    acc = struct.unpack('>h', read(2))[0]
                    log_bytes_in = log_bytes_in + '|' + str(acc)

                    if self.scaling_output:
                        aux_data.append(acc * scale_fac_accel_G_per_count)
                    else:
                        aux_data.append(acc)

                self.read_state = 3
            # ---------End Byte---------
            elif self.read_state == 3:
                val = struct.unpack('B', read(1))[0]
                log_bytes_in = log_bytes_in + '|' + str(val)
                self.read_state = 0  # read next packet
                if val == END_BYTE:
                    channel_data += aux_data
                    channel_data = [ch_data for i, ch_data in enumerate(channel_data) if i in self.active_channels]
                    sample = (timestamp, channel_data)
                    self.packets_dropped = 0
                    return sample
                else:
                    self.warn("ID:<%d> <Unexpected END_BYTE found <%s> instead of <%s>"
                              % (packet_id, val, END_BYTE))
                    if self.logger:
                        self.logger.debug(log_bytes_in)
                    self.packets_dropped += 1

    """
    Clean Up (atexit)
    """

    def stop(self):
        if self.logger:
            self.logger.debug("Stopping streaming... Wait for buffer to flush...")
        self.streaming = False
        self.ser.write(b's')
        if self.logger:
            self.logger.warning('sent <s>: stopped streaming')

    def disconnect(self):
        if self.streaming:
            self.stop()
        if self.ser.is_open:
            if self.logger:
                self.logger.debug("Closing Serial...")
            self.ser.close()
            if self.logger:
                self.logger.warning('serial closed')

    """
    SETTINGS AND HELPERS
    """

    def warn(self, text):
        if self.logger:
            # log how many packets where sent successfully in between warnings
            if self.log_packet_count:
                self.logger.info('Data packets received:' + str(self.log_packet_count))
                self.log_packet_count = 0
                self.logger.warning(text)

    def skip_incoming_text(self):
        """
        When starting the connection, skip all the debug data until
        we get to a line with the end sequence '$$$'.
        """
        # Wait for device to send data
        line = ''
        # Look for end sequence $$$
        while '$$$' not in line:
            line += self.ser.read().decode('utf-8')

    @classmethod
    def openbci_id(cls, serial_port):
        """
        When automatically detecting port, parse the serial return for the "OpenBCI" ID.
        """
        result = False

        def query_port():
            nonlocal result
            try:
                line = ''
                # Look for end sequence $$$
                while '$$$' not in line:
                    line += serial_port.read().decode('utf-8')
                if "OpenBCI" in line:
                    result = True
            except Exception:
                pass

        # we use a separate thread to use timeout
        thread = threading.Thread(target=query_port)
        thread.start()
        thread.join(serial_port.timeout)
        return result

    def print_register_settings(self):
        self.ser.write(b'?')
        self.skip_incoming_text()

    def check_connection(self, interval=2, max_packets_to_skip=10):
        if not self.streaming:
            return
        # check number of dropped packages and establish connection problem if too large
        if self.packets_dropped > max_packets_to_skip:
            # if error, attempt to reconnect
            self.reconnect()
        # check again again in 2 seconds
        threading.Timer(interval, self.check_connection).start()

    def reconnect(self):
        self.packets_dropped = 0
        self.warn('Reconnecting')
        self.stop()
        time.sleep(0.5)  # ?required, hw bug
        self.ser.write(b'v')
        time.sleep(0.5)  # ?required, hw bug
        self.ser.write(b'b')
        time.sleep(0.5)  # ?required, hw bug
        self.streaming = True
        # self.attempt_reconnect = False

    # Adds a filter at 60hz to cancel out ambient electrical noise
    def enable_filters(self):
        self.ser.write(b'f')
        self.filtering_data = True

    def disable_filters(self):
        self.ser.write(b'g')
        self.filtering_data = False

    def test_signal(self, signal):
        if signal == 0:
            self.ser.write(b'0')
            self.warn("Connecting all pins to ground")
        elif signal == 1:
            self.ser.write(b'p')
            self.warn("Connecting all pins to Vcc")
        elif signal == 2:
            self.ser.write(b'-')
            self.warn("Connecting pins to low frequency 1x amp signal")
        elif signal == 3:
            self.ser.write(b'=')
            self.warn("Connecting pins to high frequency 1x amp signal")
        elif signal == 4:
            self.ser.write(b'[')
            self.warn("Connecting pins to low frequency 2x amp signal")
        elif signal == 5:
            self.ser.write(b']')
            self.warn("Connecting pins to high frequency 2x amp signal")
        else:
            self.warn("%s is not a known test signal. Valid signals go from 0-5" % signal)

    def set_channel(self, channel, toggle_position):
        if 0 <= toggle_position <= 1 <= channel <= 8:
            self.ser.write(self.CHANNEL_COMMANDS[toggle_position][channel - 1])

    @classmethod
    def find_ports(cls, baudrate=115200, timeout=None, raise_exception=False):
        # Finds the serial port names
        if sys.platform.startswith('win'):
            import serial.tools.list_ports
            timeout = 0.5
            ports = [d.device for d in serial.tools.list_ports.comports() if 'Bluetooth' not in d.description]
        elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
            ports = glob.glob('/dev/ttyUSB*')
        elif sys.platform.startswith('darwin'):
            ports = glob.glob('/dev/tty.usbserial*')
        else:
            raise EnvironmentError('Error finding ports on your operating system'
                                   ' (maybe you need to add yourself to the "dialout" group?)')

        openbci_ports = []

        for port in ports:
            try:
                s, lock = cls.connect(port=port, baudrate=baudrate, timeout=timeout)
                try:
                    s.write(b'v')
                    time.sleep(0.5)  # list_amps.py does not work without this sleep
                    openbci_serial = cls.openbci_id(s)
                    if openbci_serial:
                        openbci_ports.append(port)
                finally:
                    s.close()
                    del lock
            except (OSError, serial.SerialException, SingleInstanceException):
                pass

        if raise_exception and not openbci_ports:
            raise OSError('Cannot find OpenBCI port')
        else:
            return openbci_ports


def test():
    logging.getLogger().setLevel('DEBUG')
    port = '/dev/ttyUSB0'
    board = OpenBciBoard(port=port)
    generator = board.init_streaming(5.0)
    for sample in generator:
        print(sample)


if __name__ == '__main__':
    test()
