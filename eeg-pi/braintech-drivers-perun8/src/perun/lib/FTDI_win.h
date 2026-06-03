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

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include "FTD2XX.h"

class FTDI
{
private:
  FT_HANDLE handle;
  FT_STATUS status;

public:
  FTDI() : handle(NULL), status(FT_OK) {}

  FT_STATUS open(int index) {
     status = FT_Open(index, &handle);
     return status;
  }
  FT_STATUS close() {
     status = FT_Close(handle);
     handle = NULL;
     return status;
  }
  inline int read(void * buffer, unsigned length) {
     DWORD done_w;
     status = FT_Read(handle, buffer, length, &done_w);
     if (status == FT_OK)
        return done_w;
     return -1;
  }
  inline int write(const void * buffer, unsigned length) {
     DWORD done_w;
     status = FT_Write(handle, (void *)buffer, length, &done_w);
     if (status == FT_OK)
        return done_w;
     return -1;
  }
  FT_STATUS purge(ULONG mode) {
     status = FT_Purge(handle, mode);
     return status;
  }
  bool set_bit_mode(UCHAR mask, UCHAR mode) {
     status = FT_SetBitMode(handle, mask, mode);
     return (status == FT_OK);
  }
  FT_STATUS set_timeouts(ULONG rx, ULONG tx) {
     status = FT_SetTimeouts(handle, rx, tx);
     return status;
  }
  bool set_baud_rate(unsigned long baud_rate) {
     status = FT_SetBaudRate(handle, baud_rate);
     return (status == FT_OK);
  }
  FT_STATUS set_latency_timer(UCHAR latency) {
     status = FT_SetLatencyTimer(handle, latency);
     return status;
  }
  bool set_flow_control_off() {
     status = FT_SetFlowControl(handle, FT_FLOW_NONE, 0, 0);
     return (status == FT_OK);
  }
  bool set_flow_control_RTS_CTS() {
     status = FT_SetFlowControl(handle, FT_FLOW_RTS_CTS, 0, 0);
     return (status == FT_OK);
  }
  bool set_serial(int data_bits, char parity, int stop_bits) {
     UCHAR e_data;
     switch (data_bits) {
        case 7:  e_data = FT_BITS_7; break;
        case 8:  e_data = FT_BITS_8; break;
	default: return false;
     }
     UCHAR e_stop;
     switch (stop_bits) {
        case 1:  e_stop = FT_STOP_BITS_1;  break;
        case 2:  e_stop = FT_STOP_BITS_2;  break;
	default: return false;
     }
     UCHAR e_parity;
     switch (parity) {
        case 'N': e_parity = FT_PARITY_NONE;  break;
        case 'O': e_parity = FT_PARITY_ODD;   break;
        case 'E': e_parity = FT_PARITY_EVEN;  break;
        case 'M': e_parity = FT_PARITY_MARK;  break;
        case 'S': e_parity = FT_PARITY_SPACE; break;
	default: return false;
     }
     status = FT_SetDataCharacteristics(handle, e_data, e_stop, e_parity);
     return (status == FT_OK);
  }
  unsigned  get_modem_status() {
     DWORD ModemStatus;
     status = FT_GetModemStatus(handle, &ModemStatus);
     return ModemStatus;
  }
  bool set_dtr(bool on) {
     if (on)
	status = FT_SetDtr(handle);
     else
	status = FT_ClrDtr(handle);
     return (status == FT_OK);
  }
  bool set_rts(bool on) {
     if (on)
	status = FT_SetRts(handle);
     else
	status = FT_ClrRts(handle);
     return (status == FT_OK);
  }

  operator bool() const { return (status == FT_OK); }
  const char * status_msg() const
  {
     static const char * mesg = "";
     return mesg;
  }
};
#endif