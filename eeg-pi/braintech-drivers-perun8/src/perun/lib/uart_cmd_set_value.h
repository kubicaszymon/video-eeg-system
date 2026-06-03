
static bool uart_cmd_set_value(Logger_C & log, FTDI & ftdi, Msg & m, unsigned value, bool verbose=true)
{
   log.enable_stdout(verbose);
   log.printf("Set value: 0x%x %u\n", value, value);
   assert(value < (1<<16));
   log.enable_stdout(true);

   if (!uart_cmd(log, ftdi, m, cmd_set_v0 | ((value >> 0) & cmd_arg_mask), false))
      return false;

   if (value & 0xf0) {
      if (!m.check_resp_value(log, value & 0xf, verbose))
	 return false;

      if (!uart_cmd(log, ftdi, m, cmd_set_v1 | ((value >> 4) & cmd_arg_mask), false))
	 return false;
   }

   if (value & 0xf00) {
      if (!m.check_resp_value(log, value & 0xff, verbose))
	 return false;

      if (!uart_cmd(log, ftdi, m, cmd_set_v2 | ((value >> 8) & cmd_arg_mask), false))
	 return false;
   }

   if (value & 0xf000) {
      if (!m.check_resp_value(log, value & 0xfff, verbose))
	 return false;

      if (!uart_cmd(log, ftdi, m, cmd_set_v3 | ((value >> 12) & cmd_arg_mask), false))
	 return false;
   }

   return m.check_resp_value(log, value, verbose);
}
