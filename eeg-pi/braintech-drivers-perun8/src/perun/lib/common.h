
#include <stdio.h>
#include <assert.h>
#ifndef __GNUC__
#define __attribute__(A) /* do nothing */
#endif
#if defined(__linux__) || defined(__APPLE__)
#include "FTDI_linux.h"
#else
#include "FTDI_win.h"
#endif

#include <stdint.h>

enum { VEN = 0x0403, PROD = 0x6014 }; // FT232H

static bool ftdi_open(Logger & log, FTDI & ftdi, int index, bool verbose=true)
{
   {
      int s;
#if defined(__linux__) || defined(__APPLE__)
      s = ftdi.open(index, VEN, PROD);
#else
      s = ftdi.open(index);
#endif
      if (verbose)
	 log.printf("ftdi open(%d): %d\n", index, (bool)ftdi);
      if (!ftdi) {
	 log.printf("ftdi open error: %d %s\n", s, ftdi.status_msg());
	 return false;
      }
   }
 
   return true;
}

static void ftdi_config(Logger & log, FTDI & ftdi, unsigned baudrate=115200, bool verbose=true)
{
   ftdi.set_timeouts(500, 500);

   // note: required for correct bitrate setting
   if (! ftdi.set_bit_mode(0x00, FT_BITMODE_RESET))
      log.printf("set bitmode OFF error: (%d) %s\n", (unsigned)ftdi, ftdi.status_msg());

   if (! ftdi.set_baud_rate(baudrate))
      log.printf("ftdi baud rate error: (%d) %s\n", (unsigned)ftdi, ftdi.status_msg());
   if (verbose)
      log.printf("FTDI rate: %u\n", baudrate);

   ftdi.set_serial(8, 'N', 1); // 8 data bits, No parity, 1 stop bit
   ftdi.set_flow_control_off();
}

bool ftdi_write_and_check(Logger & log, FTDI & ftdi, const uint8_t * buf, unsigned len)
{
   int res = ftdi.write(buf, len);
   if (res != (int)len) {
      log.printf("FTDI write (%d/%d) error: %s\n", res, len, ftdi.status_msg());
      return false;
   }
   return true;
}

#include "delay.h"

int read_with_timeout(FTDI & ftdi, uint8_t * buf, unsigned len_exp)
{
#ifdef __linux__
   unsigned timeout = ftdi.get_rx_timeout();
   unsigned len = 0;
   while (len < len_exp) {
      int res = ftdi.read(&buf[len], len_exp - len);

      if (res < 0)
	 return res; // read error

      if (res == 0) {
	 if (timeout == 0)
	    return len;
	 --timeout;
	 delay(1); // 1ms
	 continue;
      }
      len += res;
      assert(len <= len_exp);
   }
   return len;
#else
   return ftdi.read(buf, len_exp);
#endif
}

void dump_rx(Logger & log, FTDI & ftdi, unsigned limit = 0x1000)
{
   unsigned total = 0;
   unsigned char t;
   do {
      if (ftdi.read(&t, 1) != 1)
         break;
      log.printf("%02X ", t);
      ++total;
   } while (total < limit);
   if (total)
      log.printf("- %d chars\n", total);
}

static void ftdi_close(Logger & log, FTDI & ftdi)
{
   ftdi.set_bit_mode(0x00, FT_BITMODE_RESET);
   ftdi.set_timeouts(100, 100);
   dump_rx(log, ftdi, 200);
   ftdi.close();
}

void dump_data(Logger & log, const char * name, const uint8_t * data, unsigned length)
{
   log.printf("%s: (len=%u)", name, length);
   for(unsigned i=0; i<length; ++i)
      log.printf(" %02x", data[i]);
   log.printf("\n");
}
