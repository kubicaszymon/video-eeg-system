
#include "uart_msg.h"

#include "Msg.h"
#include "Pkt.h"

#include "Utils.h"
typedef double timestamp_t;

// get current time
inline static void get_timestamp(timestamp_t & now)
{
	now = get_high_resolution_clock();
}


class Msg : public Msg_base
{
private:
   enum { pre_buf_len = 256 };
   unsigned pre_len;
   unsigned resp_len;
public:
   union resp_data_t resp;
   uint8_t pre[pre_buf_len];
public:
   Msg() : Msg_base() {}
private:
   inline
   bool read_pkt(Logger & log, FTDI & ftdi, Pkt & pkt, uint8_t ch);
public:
   bool read(Logger & log, FTDI & ftdi);
   bool read_any(Logger & log, FTDI & ftdi, Pkt & pkt, timestamp_t * ts = 0);
   bool got_msg() const { return msg_len > 0; }
   bool parse(Logger & log);
   void dump(Logger & log) const {
      if (pre_len > 0) {
	 log.printf("P:");
	 for(unsigned i=0; i<pre_len; ++i)
	    log.printf(" %02x", pre[i]);
	 log.printf(" (%d)\n", pre_len);
      }
      if (msg_len > 0) {
	 log.printf("M: ");
	 for(unsigned i=0; i<msg_len; ++i) {
	    uint8_t ch = msg[i];
	    if ((ch >= 0x20) && (ch < 0x7F))
	       log.printf("%c", ch);
	    else
	       log.printf("[%02x]", ch);
	 }
	 log.printf(" (%d)\n", msg_len);
      }
   }
   bool check_resp_hw_id(Logger & log) const;
   bool check_resp_hw_stat(Logger & log) const;
   bool check_resp_value(Logger & log, unsigned value_exp, bool verbose) const;
   bool check_resp_rf_config(Logger & log, bool verbose) const;
   bool check_resp_rf_rx(Logger & log, bool verbose) const;
   bool check_resp_rf_scanner(Logger & log, bool verbose) const;
   bool check_resp_rf_time_sync(Logger & log, bool verbose) const;
};

inline
bool Msg::read_pkt(Logger & log, FTDI & ftdi, Pkt & pkt, uint8_t ch)
{
   pkt.add_byte(ch);

   // start with min possible length, updated later
   unsigned exp_len = Pkt::PKT_MIN_LEN;
   do {
      int res = read_byte(log, ftdi);
      if (res < 0)
         return false;

      pkt.add_byte(res);

      if (pkt.f_len_available()) {
         // len field received
         exp_len = pkt.total_lenght();
         if (exp_len > Pkt::PKT_BUF_LEN) {
            log.printf("read_pkt: invalid len field: %u\n", pkt.f_len());
            return false;
         }
      }
   } while (pkt.raw_len() < exp_len);

   // end of packet
   if (pre_len > 0)
      log.printf("\n");

   if (pkt.is_valid())
      return true; // pkt OK

   pkt.dump_chk(log);
   return false;
}

bool Msg::read_any(Logger & log, FTDI & ftdi, Pkt & pkt, timestamp_t * ts)
{
   pre_len = 0;
   msg_len = 0;
   pkt.clear();

   while(1) {
      int res = read_byte(log, ftdi);
      if (res < 0)
          return false;

      uint8_t ch = res;

      if (msg_len > 0) {
         msg[msg_len++] = ch;

         if (msg_len <= msg_hdr_len) {
            // header not completed yet
            if (ch == msg_hdr[msg_len-1])
	       continue; // continue msg reception

	    // wrong char, re-start
	    // do not copy the last char - it will be handled below
	    for(unsigned i=0; i<msg_len-1; ++i)
	       if (pre_len < sizeof(pre))
		  pre[pre_len++] = msg[i];
	    msg_len = 0;
	    // fall-through to header detection code
         } else {
            if (ch == '\n')
               return true;
            if (msg_len == sizeof(msg)) {
               log.printf("Msg too long\n");
               return false;
            }
            continue; // continue msg reception
         }
      }

      // no header received yet

      if (ts)
         get_timestamp(*ts); // first byte time stamp

      if (ch == pkt_hdr) { // looks like start of pkt
         return read_pkt(log, ftdi, pkt, ch);
      } else
      if (ch == msg_hdr[0]) { // looks like start of msg
         msg[msg_len++] = ch;
      } else {
         log.printf("[%02x] ", ch);
         if (pre_len < sizeof(pre))
            pre[pre_len++] = ch;
      }
   }
}

bool Msg::read(Logger & log, FTDI & ftdi)
{
   pre_len = 0;
   msg_len = 0;
   unsigned hdr_len = 0;

   while(1) {
      int res = read_byte(log, ftdi);
      if (res < 0)
	 return false;

      uint8_t ch = res;

      msg[msg_len++] = ch;

      if (hdr_len < msg_hdr_len) {
	 // check hdr
	 if (ch == msg_hdr[hdr_len]) {
	    ++hdr_len;
	 } else {
	    if (pre_len < sizeof(pre))
	       pre[pre_len++] = ch;
	    hdr_len = 0;
	    msg_len = 0; 
	    continue;
	 }
      } else if (hdr_len == msg_hdr_len) {
	 if (ch == ' ') {
	    ++hdr_len;
#if 0 // should not happen now
	 } else if (ch == msg_hdr[0]) {
	    hdr_len = 1;
	    msg_len = 1;
	    continue;
#endif
	 } else {
	    if (pre_len == 0)
	       pre[pre_len++] = ch;
	    hdr_len = 0;
	    msg_len = 0;
	    continue;
	 }
      } else {
	 if (ch == '\n')
	    return true;
	 if (msg_len == sizeof(msg)) {
	    log.printf("Msg too long\n");
	    return false;
	 }
      }
   }
}

#include <stdlib.h>

bool Msg::parse(Logger & log)
{
   if (msg_len < (msg_hdr_len + 1 + msg_rx_ch_num*4 + 3)) {
      log.printf("Msg too short: %u\n", msg_len);
      return false;
   }

   // check hdr
   for(unsigned i=0; i < msg_hdr_len; ++i)
      if (msg[i] != msg_hdr[i]) {
	 log.printf("Msg wrong hdr %u: %02x\n", i, msg[i]);
	 return false;
      }

   if (msg[msg_hdr_len] != ' ') {
      log.printf("Msg wrong char after hdr\n");
      return false;
   }

   // check for invalid chars
   for(unsigned i=0; i<msg_len; ++i) {
      uint8_t ch = msg[i];
      if ( (ch >= 0x20) && (ch < 0x7F) )
	 continue;
      if ( (ch == '\n') && (i == (msg_len-1)) )
	 continue;
      log.printf("Msg inv char %u: %02x\n", i, ch);
      return false;
   }

   // check "UART Rx" part
   for(unsigned i=0; i<msg_rx_ch_num; ++i) {
      unsigned pos = msg_hdr_len + 1 + i*4;
      if (msg[pos + 3] != ' ') {
	 log.printf("Msg wrong char at %u\n", pos+3);
	 return false;
      }
      msg[pos + 3] = 0;
      m_rx[i] = strtoul(&msg[pos], NULL, 0x10);
   }

   // check "data" part
   unsigned pos = msg_hdr_len + 1 + msg_rx_ch_num*4;
   resp_len = 0;

   if (msg[pos] == 'V') { // SW version text
      return true;
   }

   // check and convert "hex data" part
   uint8_t * ptr = (uint8_t *)&resp;
   while(1) {
      if ((pos + 2) >= msg_len) {
	 log.printf("Msg unexpected end\n");
	 return false;
      }

      if ( (msg[pos + 2] != ' ') &&
	   (msg[pos + 2] != '\n') ) {
	 log.printf("Msg wrong char at %u\n", pos+2);
	 return false;
      }
      msg[pos + 2] = 0;
      *(ptr++) = strtoul(&msg[pos], NULL, 0x10);
      ++resp_len;

      pos += 3;
      if (pos == msg_len)
	 return true;
   }
}

bool Msg::check_resp_hw_id(Logger & log) const
{
   unsigned exp_len = sizeof(struct resp_hw_id_t);
   if (resp_len != exp_len) {
      log.printf("Msg resp wrong len: %u/%u\n", resp_len, exp_len);
      return false;
   }

   log.printf("HW_ID: Lot: %x, Coor: %x:%x, DEV_ID: %x:%x:%x, UID: %x:%x:%x:%x:%x, Rev: %x\n",
	 resp.hw_id.dev_lot,
	 (resp.hw_id.dev_coor >> 16) & 0xffff,
	 (resp.hw_id.dev_coor >>  0) & 0xffff,
	 (resp.hw_id.dev_id >> 28) & 0xf,
	 (resp.hw_id.dev_id >> 12) & 0xffff,
	 (resp.hw_id.dev_id >>  0) & 0xfff,
	 (resp.hw_id.dev_uid >> 28) & 0xf,
	 (resp.hw_id.dev_uid >> 19) & 0x1ff,
	 (resp.hw_id.dev_uid >> 16) & 0x7,
	 (resp.hw_id.dev_uid >> 12) & 0xf,
	 (resp.hw_id.dev_uid >>  0) & 0xfff,
	 resp.hw_id.dev_rev);
   return true;
}

bool Msg::check_resp_hw_stat(Logger & log) const
{
   unsigned exp_len = sizeof(struct resp_hw_stat_t);
   if (resp_len != exp_len) {
      log.printf("Msg resp wrong len: %u/%u\n", resp_len, exp_len);
      return false;
   }

   log.enable_stdout(false);
   log.printf("HW: DI: %x DO: %x OE: %x HF:%x MF:%x LF:%x\n",
	 resp.hw_stat.din,
	 resp.hw_stat.dout,
	 resp.hw_stat.doe,
	 resp.hw_stat.clk_hf,
	 resp.hw_stat.clk_mf,
	 resp.hw_stat.clk_lf);

   log.enable_stdout(true);
   log.printf("HW1: Vcc: %.3fV Temp: %dC\n",
	 resp.hw_stat.vcc * 0.001 ,
	 resp.hw_stat.temp);
   return true;
}

bool Msg::check_resp_value(Logger & log, unsigned value_exp, bool verbose) const
{
   unsigned exp_len = sizeof(resp.value);
   if (resp_len != exp_len) {
      log.printf("Msg resp wrong len: %u/%u\n", resp_len, exp_len);
      return false;
   }

   unsigned value = resp.value;
   if ((value != value_exp) || verbose)
      log.printf("value: %04x / %04x\n", value, value_exp);

   return (value == value_exp);
}

bool Msg::check_resp_rf_config(Logger & log, bool verbose) const
{
   unsigned exp_len = sizeof(struct resp_rf_config_t);
   if (resp_len != exp_len) {
      log.printf("Msg resp wrong len: %u/%u\n", resp_len, exp_len);
      return false;
   }

   log.enable_stdout(verbose);
   log.printf("RF_CONFIG: freq: %u, BLE channel: %u, whitening: %02x, power: %u, ",
	 resp.rf_config.frequency,
	 resp.rf_config.ble_channel,
	 resp.rf_config.whitening,
	 resp.rf_config.power_idx);
   log.printf("BLE size: %u, pkt num: %u, ADC samples: %u, mode %x, cmd: %x, timeout: %.1f\n",
	 resp.rf_config.ble_data_size,
	 resp.rf_config.pkt_num,
	 resp.rf_config.adc_samples,
	 resp.rf_config.mode,
	 resp.rf_config.scan_req_cmd,
	 resp.rf_config.timeout * 0.1);
   log.enable_stdout(true);

   return true;
}

enum { RF_TICKS_PER_1MS = 4000 };

static void print_event_log(Logger & log, const rf_event_log_t * event_log, unsigned event_cnt, unsigned event_num)
{
   log.enable_stdout(false);
   log.printf("  event_cnt: %u\n", event_cnt);

   if (event_num > event_cnt)
      event_num = event_cnt;

   for(unsigned i=0; i < event_num; ++i) {
      log.printf("  %.3fms", event_log[i].time * 1.0 / RF_TICKS_PER_1MS);
      log.printf(" %x", event_log[i].event);
      log.printf("\n");
   }
   log.enable_stdout(true);
}

bool Msg::check_resp_rf_rx(Logger & log, bool verbose) const
{
   unsigned exp_len = sizeof(struct resp_rf_dongle_t);
   if (resp_len != exp_len) {
      log.printf("Msg resp wrong len: %u/%u\n", resp_len, exp_len);
      return false;
   }

   log.enable_stdout(verbose);
   log.printf("RF_RX: ok_cnt:%u loop time: %.3fms\n"
	      "  RF time %.3fms (noRF: %.3f) UART time %.3fms\n",
	 resp.rf_dongle.cmd_status_ok,
	 resp.rf_dongle.loop_time * 1.0 / RF_TICKS_PER_1MS,
	 resp.rf_dongle.rf_time * 1.0 / RF_TICKS_PER_1MS,
	 (resp.rf_dongle.loop_time - resp.rf_dongle.rf_time) * 1.0 / RF_TICKS_PER_1MS,
	 resp.rf_dongle.uart_time * 1.0 / RF_TICKS_PER_1MS);
   log.printf("  cmd st: %04x, time: %.3fms, max_rx_buf: %u\n",
	 resp.rf_dongle.cmd_status,
	 resp.rf_dongle.cmd_time * 1.0 / RF_TICKS_PER_1MS,
	 resp.rf_dongle.max_rx_buf);
   log.printf("  Tx:%u Acked:%u Retrans:%u TxDone:%u Rx:%u RxErr: %u RxIgn:%u RxEmpty:%u\n",
	 resp.rf_dongle.s_tx,
	 resp.rf_dongle.s_tx_acked,
	 resp.rf_dongle.s_tx_retrans,
	 resp.rf_dongle.s_tx_done,
	 resp.rf_dongle.s_rx,
	 resp.rf_dongle.s_rx_err,
	 resp.rf_dongle.s_rx_ign,
	 resp.rf_dongle.s_rx_empty);

   print_event_log(log, resp.rf_dongle.event_log, resp.rf_dongle.event_cnt, resp_rf_dongle_event_num);

   return true;
}

bool Msg::check_resp_rf_scanner(Logger & log, bool verbose) const
{
   unsigned exp_len = sizeof(struct resp_rf_scanner_t);
   if (resp_len != exp_len) {
      log.printf("Msg resp wrong len: %u/%u\n", resp_len, exp_len);
      return false;
   }

   log.enable_stdout(verbose);
   log.printf("RF_SCANNER: cmd st: %04x, time: %.3fms\n",
	 resp.rf_scanner.cmd_status,
	 resp.rf_scanner.cmd_time * 1.0 / RF_TICKS_PER_1MS);
   log.printf("  Tx:%u Bckd:%u RxAdv:%u Err:%u Ign:%u RxRsp:%u Err: %u Ign:%u\n",
         resp.rf_scanner.s_tx,
         resp.rf_scanner.s_backed,
         resp.rf_scanner.s_rx_adv,
         resp.rf_scanner.s_rx_adv_err,
         resp.rf_scanner.s_rx_adv_ign,
         resp.rf_scanner.s_rx_rsp,
         resp.rf_scanner.s_rx_rsp_err,
         resp.rf_scanner.s_rx_rsp_ign);

   print_event_log(log, resp.rf_scanner.event_log, resp.rf_scanner.event_cnt, resp_rf_scanner_event_num);

   return true;
}

bool Msg::check_resp_rf_time_sync(Logger & log, bool verbose) const
{
   unsigned exp_len = sizeof(struct resp_rf_time_sync_t);
   if (resp_len != exp_len) {
      log.printf("Msg resp wrong len: %u/%u\n", resp_len, exp_len);
      return false;
   }

   log.enable_stdout(verbose);
   log.printf("RF_TIME_SYNC: cmd1 st: %04x, time: %.3fms\n",
	 resp.rf_time_sync.cmd1_status,
	 resp.rf_time_sync.cmd1_time * 1.0 / RF_TICKS_PER_1MS);
   log.printf("              cmd2 st: %04x, time: %.3fms\n",
	 resp.rf_time_sync.cmd2_status,
	 resp.rf_time_sync.cmd2_time * 1.0 / RF_TICKS_PER_1MS);
   log.printf("  UartRx: %u UartTx: %u Seq: %02x Tx:%u Rx:%u Err:%u Ign:%u\n",
         resp.rf_time_sync.uart_rx_time,
         resp.rf_time_sync.uart_tx_time,
         resp.rf_time_sync.tx_seq,
         resp.rf_time_sync.s_tx_adv,
         resp.rf_time_sync.s_rx_adv,
         resp.rf_time_sync.s_rx_adv_err,
         resp.rf_time_sync.s_rx_adv_ign);

   print_event_log(log, resp.rf_time_sync.event_log, resp.rf_time_sync.event_cnt, resp_rf_time_sync_event_num);

   return true;
}
