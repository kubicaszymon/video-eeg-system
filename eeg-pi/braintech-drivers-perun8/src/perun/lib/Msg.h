// Msg base class

class Msg_base
{
protected:
   enum { msg_buf_len = 512 };
   char msg[msg_buf_len];
   unsigned msg_len;
public:
   uint16_t m_rx[msg_rx_ch_num];
public:
   Msg_base() : msg_len(0) {}
//protected:
public:
   int read_byte(Logger & log, FTDI & ftdi, bool fast=false);
};

int Msg_base::read_byte(Logger & log, FTDI & ftdi, bool fast)
{
   unsigned timeout =
#if defined(__linux__) || defined(__APPLE__)
      300;
#else
      2;
#endif

   while(1) {
      uint8_t ch;
#if 0 // test async libusb
      struct ftdi_transfer_control * tc = ftdi_read_data_submit(&ftdi.ftdic, &ch, 1);
      assert(tc != 0);
      int res = ftdi_transfer_data_done(tc);
#else
      int res = ftdi.read(&ch, 1);
#endif
      if (res == 1)
	 return ch;

      if (res < 0) {
	 log.printf("FTDI read error: (%d) %s\n", (unsigned)ftdi, ftdi.status_msg());
	 return -1;
      }

      // res == 0
      if (timeout == 0) {
	 log.printf("Msg read timeout\n");
	 return -1;
      }

      --timeout;
      if (fast) {
	 usleep(100); // 100us
      } else
	 delay(1); // 1ms
   }
}
