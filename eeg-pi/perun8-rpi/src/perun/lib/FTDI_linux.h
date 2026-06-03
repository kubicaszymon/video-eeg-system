// FTDI class
// © Copyright 2017 Pawel Jewstafjew Pawel<dot>Jewstafjew<at>gmail<dot>com

#ifndef _FTDI_H
#define _FTDI_H

enum { // FTDI Modem Status flags
   FT_MS_CTS = 1<<4, // CTS
   FT_MS_DSR = 1<<5, // DSR
   FT_MS_RI  = 1<<6, // RI
   FT_MS_DCD = 1<<7, // DCD
   FT_MS_DR  = 1<<8,  // Data ready
   FT_MS_OE  = 1<<9,  // Overrun error
   FT_MS_PE  = 1<<10, // Parity error
   FT_MS_FE  = 1<<11, // Framing error
   FT_MS_BI  = 1<<12, // Break interrupt
   FT_MS_TH  = 1<<13, // Transmitter holding register
   FT_MS_TE  = 1<<14, // Transmitter empty
   FT_MS_RF  = 1<<15, // Error in RCVR FIFO
};

#include <assert.h>
#include <stdint.h>
#ifdef __APPLE__
#include <libftdi1/ftdi.h>
#else
#include <ftdi.h>
#endif
enum {
  FT_OK = 0,
  FT_PURGE_RX = 1,
};

enum {
  FT_BITMODE_RESET        = BITMODE_RESET,
  FT_BITMODE_MPSSE        = BITMODE_MPSSE,
  FT_BITMODE_CBUS_BITBANG = BITMODE_CBUS,
};

class FTDI
{
private:
  struct ftdi_context ftdic;
  int status;

public:
  FTDI() : status(0) {
     assert(ftdi_init(&ftdic) >= 0);
  }
  ~FTDI() {
     ftdi_deinit(&ftdic);
  }
  operator bool() const {
     return (status >= 0);
  }
  int open(int index, int vendor, int product) {
     status = ftdi_usb_open_desc_index(&ftdic, vendor, product, NULL, NULL, index);
     return status;
  }
  bool close() {
     status = ftdi_usb_close(&ftdic);
     return status >= 0;
  }
  bool reset_device() {
     return ftdi_usb_reset(&ftdic) >= 0;
  }
  bool set_flow_control_off() {
     return ftdi_setflowctrl(&ftdic, SIO_DISABLE_FLOW_CTRL) == 0;
  }
  bool set_flow_control_RTS_CTS() {
     return ftdi_setflowctrl(&ftdic, SIO_RTS_CTS_HS) == 0;
  }
  bool set_serial(int data_bits, char parity, int stop_bits) {
     enum ftdi_bits_type e_data;
     switch (data_bits) {
        case 7:  e_data = BITS_7; break;
        case 8:  e_data = BITS_8; break;
	default: return false;
     }
     enum ftdi_stopbits_type e_stop;
     switch (stop_bits) {
        case 1:  e_stop = STOP_BIT_1;  break;
        case 15: e_stop = STOP_BIT_15; break; // 1.5 stop bits
        case 2:  e_stop = STOP_BIT_2;  break;
	default: return false;
     }
     enum ftdi_parity_type e_parity;
     switch (parity) {
        case 'N': e_parity = NONE;  break;
        case 'O': e_parity = ODD;   break;
        case 'E': e_parity = EVEN;  break;
        case 'M': e_parity = MARK;  break;
        case 'S': e_parity = SPACE; break;
	default: return false;
     }
     return ftdi_set_line_property2(&ftdic, e_data, e_stop, e_parity, BREAK_OFF) == 0;
  }
  bool set_baud_rate(unsigned baud_rate) {
     return ftdi_set_baudrate(&ftdic, baud_rate) >= 0;
  }
  bool set_bit_mode(uint8_t mask, uint8_t mode) {
     return (ftdi_set_bitmode(&ftdic, mask, mode) == 0);
  }
  inline int read(void * buffer, unsigned len) {
     return ftdi_read_data(&ftdic, (uint8_t *)buffer, len);
  }
  inline int write(const void * buffer, unsigned len) {
     return ftdi_write_data(&ftdic, (uint8_t *)buffer, len);
  }
  inline uint8_t get_bit_mode() {
     uint8_t pins;
     ftdi_read_pins(&ftdic, &pins);
     return pins;
  }
  bool purge(unsigned mode) {
     if (mode && FT_PURGE_RX)
        return ftdi_usb_purge_rx_buffer(&ftdic) >= 0;
     return 0;
  }
  void set_latency_timer(unsigned latency) {
     ftdi_set_latency_timer(&ftdic, latency);
  }
  uint8_t get_latency_timer() {
     uint8_t latency;
     ftdi_get_latency_timer(&ftdic, &latency);
     return latency;
  }
  void set_usb_parameters(unsigned rx_chunksize, unsigned tx_chunksize) {
     ftdi_read_data_set_chunksize(&ftdic, rx_chunksize);
     ftdi_write_data_set_chunksize(&ftdic, tx_chunksize);
  }
  void set_timeouts(unsigned rx, unsigned tx) {
    ftdic.usb_read_timeout = rx;
    ftdic.usb_write_timeout = tx;
  }
  unsigned get_rx_timeout() const {
     return ftdic.usb_read_timeout;
  }
  unsigned get_modem_status() {
     unsigned short status;
     ftdi_poll_modem_status(&ftdic, &status);
     return status;
  }
  bool set_dtr(int state) {
     return (ftdi_setdtr(&ftdic, state) == 0);
  }
  bool set_rts(int state) {
     return (ftdi_setrts(&ftdic, state) == 0);
  }
public:
  const char * status_msg() {
     return ftdi_get_error_string(&ftdic);
  }
};

#endif // _FTDI_H
