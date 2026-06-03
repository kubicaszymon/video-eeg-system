
#ifndef FTDI_UART_STATUS_H
#define FTDI_UART_STATUS_H

unsigned ftdi_uart_status(Logger & log, FTDI & ftdi)
{
   unsigned status = ftdi.get_modem_status();

   log.printf("FTDI Stat: %x CTS:%x DSR:%x DCD:%x RI:%x",
	 status,
	 (status & FT_MS_CTS) ? 1 : 0,
	 (status & FT_MS_DSR) ? 1 : 0,
	 (status & FT_MS_DCD) ? 1 : 0,
	 (status & FT_MS_RI)  ? 1 : 0);
   if (status & FT_MS_DR)
      log.printf(" DataRdy");
   if (status & FT_MS_OE)
      log.printf(" OvrErr");
   if (status & FT_MS_PE)
      log.printf(" PrtErr");
   if (status & FT_MS_FE)
      log.printf(" FrmErr");
   if (status & FT_MS_BI)
      log.printf(" Brk");
   if (status & FT_MS_TH)
      log.printf(" TxHR");
   if (status & FT_MS_TE)
      log.printf(" TxEmpt");
   if (status & FT_MS_RF)
      log.printf(" RFErr");
   log.printf("\n");

   return status;
}

#endif // FTDI_UART_STATUS_H
