
#include "ftdi_uart_status.h"
#include "ftdi_cbus_set.h"

bool ftdi_uart(Logger & log, FTDI & ftdi)
{
   if (! ftdi.set_bit_mode(0x00, FT_BITMODE_RESET)) {
      log.printf("set bitmode OFF error: (%d) %s\n", (unsigned)ftdi, ftdi.status_msg());
      return false;
   }

   ftdi_cbus_set(log, ftdi, 0, 0);
   ftdi.set_rts(1);
   ftdi.set_flow_control_RTS_CTS();
   ftdi.set_dtr(0);
   ftdi.set_latency_timer(16);
   ftdi_uart_status(log, ftdi);
   return true;
}
