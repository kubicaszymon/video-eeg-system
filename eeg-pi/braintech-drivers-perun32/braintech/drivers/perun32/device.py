# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
import atexit
import logging
import os
import struct
import sys
import threading
import time
from collections import namedtuple
from logging import getLogger
from pathlib import Path
from queue import Queue

import numpy as np

try:
    from braintech.drivers.native_amplifier_lib.native_lib._native_lib import PyAmplifier
    local_clock = PyAmplifier.local_clock
except ImportError:
    # on average it will be the same but instanteniously might be worse
    local_clock = time.time
from braintech.utils.singleton_app import SingleInstanceException, SingleProcessApplication

os.environ['PATH'] = str(Path(__file__).parent / 'bin') + os.pathsep + os.environ['PATH']
import usb1
from usb1 import USBDevice, USBDeviceHandle, USBError
from usb1 import USBTransfer
from usb1 import libusb1

from braintech.drivers.perun32 import ctrl_seq

LOGGER = getLogger(__name__)

USB_IFC_ID = 0  # USB Interface


# VID, PID, bcD
PERUN_VERSION_TABLE = {(0x04b4, 0x8613, 0xEE00): 'old',
                       (0x16D0, 0x0FAB, 0x01A0): 'a',
                       (0x16D0, 0x0FAB, 0x01B0): 'b',
                       (0x16D0, 0x0FAB, 0x01C0): 'c',
                       (0x16D0, 0x0FAB, 0x01D0): 'd',
                       }



class USB_ALT:
    OFF = 0
    CTRL = 1
    ISO_1 = 3
    ISO_2 = 4


class ENDPOINT:
    C_OUT = 0x06  # Ctrl OUT Endpoint (host sends command)
    C_IN = 0x88  # Ctrl IN  Endpoint (host reads response)
    EP_D_IN = 0x82  # Data IN  Endpoint (host reads data)


class PKT_LEN:
    CTRL = 0x200  # Ctrl In/Out
    ISO = 450  # Data In


VC_STATUS = 0xB0  # Get Status


class STATUS:
    VERSION = 0x10  # version code
    READY = 0xA5
    STARTUP = 0x51
    LEN = 9  # VC_STATUS response  length


class PerunAmpException(RuntimeError):
    pass


class SampleData(namedtuple("_SampleData", 'timestamp,receive_timestamp,events,status,ch_data')):
    ADS_CH_NUM = 8
    ADS_NUMBER = 4
    TOTAL_CHANNELS = (1 + ADS_CH_NUM)
    ADS_CH_DATA_LEN = TOTAL_CHANNELS * 3
    PKT_LEN = 4 + ADS_NUMBER * ADS_CH_DATA_LEN

    @classmethod
    def parse_ads_data(cls, data, received_timestamp=None, get_timestamp=None):
        if len(data) % cls.PKT_LEN != 0:
            LOGGER.warning("WRONG SIZE: %d", len(data))
        else:
            packets = len(data) // cls.PKT_LEN
            buffer = np.zeros((packets, cls.ADS_NUMBER, cls.TOTAL_CHANNELS, 4), dtype=np.int8)
            data = np.frombuffer(data, dtype=np.uint8)
            b_23 = (1 << 23)
            b_24 = (1 << 24)
            for i in range(packets):
                chunk = data[i * cls.PKT_LEN:(i + 1) * cls.PKT_LEN]
                result = buffer[i]
                timestamp = struct.unpack('<I', chunk[:4])[0] & 0x00FFFFFF
                event = chunk[3] ^ 0x0F
                chunk = chunk[4:].reshape(cls.ADS_NUMBER, cls.TOTAL_CHANNELS, 3)
                result[:, :, 1:] = chunk
                result = result.view(dtype='>i4').reshape(cls.ADS_NUMBER, cls.TOTAL_CHANNELS)
                status = result[:, 0].reshape(cls.ADS_NUMBER)
                ch_data = result[:, 1:].reshape(cls.ADS_NUMBER * cls.ADS_CH_NUM)
                ch_data[ch_data >= b_23] -= b_24
                if get_timestamp:
                    timestamp = get_timestamp(timestamp)
                if received_timestamp is None:
                    received_timestamp = local_clock()
                yield SampleData(timestamp, received_timestamp, event, status, ch_data)

    @property
    def ch_data_with_events(self):
        return np.concatenate((self.ch_data, [self.events]))

    @property
    def is_rin1_set(self):
        return bool(self.events & PerunAmp32Device.EVENT_RIN1)

    @property
    def is_rin2_set(self):
        return bool(self.events & PerunAmp32Device.EVENT_RIN2)


class PerunAmp32Device:
    VENDOR_ID = 0x04b4
    PRODUCT_ID = 0x8613
    DEFAULT_TIMEOUT = 50
    _context = None
    SAMPLING_RATES = [500, 1000, 2000, 4000, 8000, 16000, ]
    ISO_TRANSFERS = 8
    ISO_BUFFERS = 32
    ISO_TIMEOUT = 100
    EVENT_RIN1 = 1 << 2
    EVENT_RIN2 = 1 << 3
    EVENT_DOUT1 = 1 << 0
    EVENT_DOUT2 = 1 << 1

    @classmethod
    def _get_context(cls):
        if cls._context is None:
            cls._context = usb1.USBContext()
            lib_usb_logger = logging.getLogger(__name__ + '.libusb')
            if lib_usb_logger.level == logging.NOTSET:
                lib_usb_logger.setLevel('INFO')
            log_level = logging.getLevelName(lib_usb_logger.getEffectiveLevel())
            usb_log_level = getattr(libusb1, 'LIBUSB_LOG_LEVEL_' + log_level)
            cls._context.setDebug(usb_log_level)
            atexit.register(cls._context.close)
        return cls._context

    @classmethod
    def find_devices(cls):
        for dev in cls._get_context().getDeviceList(True, True):  # type: USBDevice
            key = (dev.getVendorID(), dev.getProductID(), dev.getbcdDevice())
            if key in PERUN_VERSION_TABLE:
                device = cls(dev, PERUN_VERSION_TABLE[key])
                if device.is_available():
                    yield device

    def __init__(self, usb_device, model):
        self.model = model
        # type: (USBDevice) -> None
        self._device = usb_device
        self._sampling_thread = None
        self._running = False
        self._stopping = False
        self._transfers = []
        self._sampling_rate = 2000
        self._handle = None
        self._received = 0
        self.measure_impedance = False

    def _get_lock(self):
        return SingleProcessApplication('perun32', str(self._device.getDeviceAddress()))

    def is_available(self):
        try:
            lock = self._get_lock()
            lock.release()
            return True
        except SingleInstanceException:
            return False

    @property
    def sampling_rate(self):
        return self._sampling_rate

    @sampling_rate.setter
    def sampling_rate(self, sampling_rate):
        if self._running:
            raise PerunAmpException("Could not set sampling rate when running")
        assert sampling_rate in self.SAMPLING_RATES
        self._sampling_rate = sampling_rate

    def open(self):
        self._lock = self._get_lock()
        self._usb_open_claim_set()
        self._usb_dev_handle()
        LOGGER.info("Device opened")

    def _usb_open_claim_set(self):
        self._handle = self._device.open()  # type: USBDeviceHandle
        try:
            self._handle.detachKernelDriver(USB_IFC_ID)
        except USBError:
            pass
        self._handle.claimInterface(USB_IFC_ID)
        self._set_alt(USB_ALT.OFF)

    def _usb_dev_handle(self):
        while self._get_status() != STATUS.READY:
            time.sleep(0.3)
        self._set_alt(USB_ALT.CTRL)
        self._ctrl_out_in(ctrl_seq.check)

    def _set_alt(self, alt):
        self._handle.setInterfaceAltSetting(USB_IFC_ID, alt)

    def _ctrl_out_in(self, ctrl_seq):
        # type: (CtrlSeq)-> bool
        transferred = self._handle.bulkWrite(ENDPOINT.C_OUT, ctrl_seq.data_out, self.DEFAULT_TIMEOUT)
        if transferred != ctrl_seq.length:
            raise PerunAmpException(
                "Could not transfer whole buffer transferred %d/%d" % (transferred, ctrl_seq.length))
        try:
            response = self._handle.bulkRead(ENDPOINT.C_IN, PKT_LEN.CTRL)
        except usb1.USBErrorTimeout as ex:
            response = ex.received
        if not self._ctrl_check_response(ctrl_seq, response):
            raise PerunAmpException(
                "Wrong response!"
            )
        return response

    def _ctrl_check_response(self, ctrl_seq, response):
        if ctrl_seq.length != len(response):
            raise PerunAmpException("usb_ctrl_check_response: wrong length %d/%d\n" % (len(response), ctrl_seq.length))
        mismatched = 0
        for i, got, exp, mask in zip(range(len(response)), response, ctrl_seq.data_in, ctrl_seq.data_in_mask):
            if got & mask != exp:
                LOGGER.warning("ctrl %d got: %02x, exp: %02x, mask: %02x\n" % (i, got, exp, mask))
                mismatched += 1
            if mismatched > 10:
                break
        return mismatched == 0

    def _get_status(self):
        status = self._handle.controlRead(0xC0, VC_STATUS, 0, 0, 20, self.DEFAULT_TIMEOUT)
        if len(status) != STATUS.LEN:
            raise PerunAmpException("libusb_control_transfer(VC_STATUS): %d\n" % len(status))
        if status[0] != STATUS.VERSION:
            raise PerunAmpException("Wrong version: %s" % list(status))
        if int(status[1]) not in [STATUS.READY, STATUS.STARTUP]:
            raise PerunAmpException("Wrong Status: %s" % status[1:])
        return status[1]

    def _adc_power_on(self):
        for i in range(3):
            self._ctrl_out_in(ctrl_seq.pwr_on)
            time.sleep(0.050)
            try:
                self._ctrl_out_in(ctrl_seq.check)
                break
            except (USBError, PerunAmpException):
                self._set_alt(USB_ALT.OFF)
                self._set_alt(USB_ALT.CTRL)
        else:
            raise PerunAmpException("Could not power on!")
        time.sleep(0.15)

    def stop(self):
        self._running = False
        if self._sampling_thread:
            self._sampling_thread.join()
            self._sampling_thread = None
        LOGGER.info("Stopped")

    def start(self):
        if self._sampling_thread:
            raise PerunAmpException("Already started")
        self._queue = Queue()
        self._running = True
        self._received = 0
        self._sampling_thread = threading.Thread(target=self._receive_samples, name="PerunAmp32SamplingThread",
                                                 daemon=True)
        self._ready_data = []
        self._sampling_thread.start()

    def __del__(self):
        if self._handle:
            self.stop()
            self._device.close()
            self._lock.release()
            self._handle = None

    def _schedule_transfers(self):
        pkt_num = self.ISO_BUFFERS
        pkt_len = PKT_LEN.ISO
        data_buf_size = pkt_num * pkt_len
        transfers = []
        for i in range(self.ISO_TRANSFERS):
            transfer = self._handle.getTransfer(pkt_num)
            transfer.setIsochronous(ENDPOINT.EP_D_IN, data_buf_size, self._data_received, 0, self.ISO_TIMEOUT)
            transfer.submit()
            transfers.append(transfer)
        return transfers

    def _data_received(self, transfer):
        # type: (USBTransfer) -> None
        start_ts = time.perf_counter()
        r_time = local_clock()
        start = 0
        buffers = ''
        try:
            status = transfer.getStatus()
        except Exception:
            status = usb1.TRANSFER_ERROR
        if status == usb1.TRANSFER_COMPLETED:
            all_data = bytearray(transfer.getActualLength())
            for desc, data in zip(transfer.getISOSetupList(), transfer.getISOBufferList()):
                act_len = desc['actual_length']
                if desc['status'] == usb1.TRANSFER_COMPLETED and act_len:
                    all_data[start:start + act_len] = data[:act_len]
                    start += act_len
                    buffers += 'x'
                else:
                    buffers += 'o'
            if start:
                self._queue.put((all_data, r_time))
        if self._running:
            transfer.submit()
        else:
            transfer.close()
            self._transfers.remove(transfer)
        LOGGER.debug("Received transfer (status:%s) with %d bytes, buffers used: %s (callback duration: %s ms)",
                     status,
                     start,
                     buffers,
                     (time.perf_counter() - start_ts) * 1000)

    def _receive_samples(self):
        self._last_timestamp = 0
        self._adc_power_on()
        self._ctrl_out_in(ctrl_seq.init)
        self._ctrl_out_in(ctrl_seq.stop)
        seq_name = 'config_%s%d' % ('imp_' if self.measure_impedance else '', self._sampling_rate)
        self._ctrl_out_in(getattr(ctrl_seq, seq_name))
        self.get_time()
        self._ctrl_out_in(ctrl_seq.start)
        self._set_alt(USB_ALT.ISO_1 if self._sampling_rate == 16000 else USB_ALT.ISO_2)
        self._transfers = self._schedule_transfers()
        context = self._get_context()
        while self._running or self._transfers:
            context.handleEvents()
            LOGGER.debug("HandleEventsFinished")
        self._set_alt(USB_ALT.CTRL)
        self._ctrl_out_in(ctrl_seq.stop)
        self._ctrl_out_in(ctrl_seq.pwr_off)
        LOGGER.info("Receive samples finished")

    def _get_timestamp(self, timestamp):
        if timestamp < self._last_timestamp:
            self._time_diff += (1 << 24) / 1000000
        self._last_timestamp = timestamp
        cur_timestamp = self._time_diff + timestamp / 1000000
        return cur_timestamp

    def get_samples(self, timeout=None):
        # type: (float)->SampleData
        if not self._ready_data:
            self._ready_data = list(SampleData.parse_ads_data(*self._queue.get(timeout=timeout),
                                                              get_timestamp=self._get_timestamp))
        return self._ready_data.pop(0)

    def get_time(self):
        prev_time = local_clock()
        while True:
            start_time = local_clock()
            if start_time != prev_time:
                break
        d1 = time.perf_counter()
        resp = self._ctrl_out_in(ctrl_seq.get_time)
        d2 = time.perf_counter()
        duration = d2 - d1
        timestamp = 0
        for i in range(6):
            timestamp |= (resp[1 + i] & 0xf) << (i * 4)
        self._time_diff = start_time - timestamp / 1000000 + duration / 2

    def __str__(self):
        return "Perun32 %s" % self._device.getDeviceAddress()


if __name__ == '__main__':
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    LOGGER.setLevel('DEBUG')
    # logging.getLogger(__name__+'.libusb').setLevel('INFO')
    d = list(PerunAmp32Device.find_devices())[0]
    d.open()
    d.sampling_rate = int(sys.argv[1])
    d.measure_impedance = 'impedance' in sys.argv
    d.start()
    for s in range(d.sampling_rate * 10):
        samples = d.get_samples()
    d.stop()
