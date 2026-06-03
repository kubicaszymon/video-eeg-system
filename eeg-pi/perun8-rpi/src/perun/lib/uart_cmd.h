// uart_tx_rx_test()
// uart_cmd()

#include "Logger_C.h"

static bool uart_tx_rx_test(Logger_C & log, FTDI & ftdi, Msg & m, bool verbose=true)
{
   uint8_t tx_buf[msg_rx_ch_num] = { cmd_version, cmd_nop + 0x5, cmd_version, cmd_nop + 0xA };

   // UART Tx
   bool wr_res = ftdi_write_and_check(log, ftdi, tx_buf, sizeof(tx_buf));

   if (!wr_res)
      return false;

   for(unsigned i=0; i<3; ++i) {
      if (m.read(log, ftdi)) {
	 log.enable_stdout(verbose);
	 m.dump(log);
	 log.enable_stdout(true);

	 if (m.parse(log)) {
	    bool match = true;
	    for(unsigned i=0; i<msg_rx_ch_num; ++i)
	       if (m.m_rx[i] != tx_buf[i]) {
		  log.printf("tx/rx mismatch %u: exp: %02x got: %02x\n", i, tx_buf[i], m.m_rx[i]);
		  match = false;
		  break;
	       }
	    if (match)
	       return true;
	 }
      }
   }

   return false;
}

static bool uart_cmd(Logger_C & log, FTDI & ftdi, Msg & m, unsigned char tx_ch, bool verbose = true, bool wait_for_key = false)
{
   log.enable_stdout(verbose);
   log.printf("Tx: %02x\n", tx_ch);
   log.enable_stdout(true);

   if (!ftdi_write_and_check(log, ftdi, &tx_ch, 1))
      return false;

   if (wait_for_key) {
      printf("press return to continue\n");
      char line[40];
      fgets(line, sizeof(line)-4, stdin);
   }

   for(unsigned i=0; i<3; ++i) {
      if (m.read(log, ftdi)) {
	 log.enable_stdout(verbose);
	 m.dump(log);
	 log.enable_stdout(true);

	 if (m.parse(log)) {
	    unsigned rx_ch = m.m_rx[msg_rx_ch_num - 1];

	    if (rx_ch == tx_ch)
	       return true;

	    log.printf("tx/rx mismatch exp: %02x got: %02x\n", tx_ch, rx_ch);
	 } else {
	    if (!verbose)
	       m.dump(log);
	 }
      }
   }

   return false;
}
