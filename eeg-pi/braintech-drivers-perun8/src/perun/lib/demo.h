// RF transmission demo
// © Copyright 2017,2018 Pawel Jewstafjew Pawel<dot>Jewstafjew<at>gmail<dot>com
#include <inttypes.h>
#include "common.h"

#include "Msg_rf.h"
#include "uart_cmd.h"
#include "uart_cmd_set_value.h"
#include "Pkt.h"
#ifndef __linux__
extern "C" { FILE __iob_func[3] = { *stdin,*stdout,*stderr }; }
#endif // !__linux__

bool rf_config_set(Logger & log, FTDI & ftdi, Msg & m, uint8_t cmd, unsigned v)
{
   if (! uart_cmd_set_value(log, ftdi, m, v, false))
      return false;
   if (!uart_cmd(log, ftdi, m, cmd, false))
      return false;
   return m.check_resp_rf_config(log, false);
}

enum {
   ble_status_Ignore = 1<<6,
   ble_status_CrcErr = 1<<7
};

struct pkt_stats_t {
   unsigned pkt_num;
   unsigned pkt_err_num;
   unsigned pkt_ign_num;
   int rssi_min;
   int rssi_min_ok;
   int rssi_max;
   int rssi_sum;
   unsigned data_len_sum;
   unsigned time_diff_min;
   unsigned time_diff_max;
   double time_diff_sum;

   void clear() {
      pkt_num = 0;
      pkt_err_num = 0;
      pkt_ign_num = 0;
      rssi_min    =  1000;
      rssi_min_ok =  1000;
      rssi_max    = -1000;
      rssi_sum = 0;
      data_len_sum = 0;
      time_diff_min = ~0;
      time_diff_max = 0;
      time_diff_sum = 0;
   }
   bool add(const Pkt & pkt, unsigned time_diff) {
      assert(pkt.is_valid());
      ++pkt_num;

      int8_t rssi = pkt.f_rssi();
      if (rssi_min > rssi)
	 rssi_min = rssi;
      if (rssi_max < rssi)
	 rssi_max = rssi;
      rssi_sum += rssi;

      if (time_diff) {
	 if (time_diff_min > time_diff)
	    time_diff_min = time_diff;
	 if (time_diff_max < time_diff)
	    time_diff_max = time_diff;
         time_diff_sum += time_diff;
      }

      uint8_t status = pkt.f_status();
      if (status & ble_status_CrcErr) {
	 ++pkt_err_num;
	 return false;
      } else {
	 if (rssi_min_ok > rssi)
	    rssi_min_ok = rssi;

	 if (status & ble_status_Ignore) {
	    ++pkt_ign_num;
	    return false;
	 } else {
	    data_len_sum += pkt.f_ble_len();
	    return true;
	 }
      }
   }
   void show(Logger & log) {
      // "first" time_diff was not recorded
      double time_diff_corrected = time_diff_sum * pkt_num / (pkt_num - 1);
      double data_rate = data_len_sum * 1.0 / (time_diff_corrected / RF_TICKS_PER_1MS);
      log.printf("| pkt: %u, err: %u, ign: %u, data: %u, rssi: (%d) %d %.1f %d\n"
                 "| time: %.3fms %.3fms, rate: %.3f bytes/ms\n",
	    pkt_num,
	    pkt_err_num,
	    pkt_ign_num,
	    data_len_sum,
	    rssi_min,
	    rssi_min_ok,
	    rssi_sum * 1.0 / pkt_num,
	    rssi_max,
	    time_diff_min * 1.0 / RF_TICKS_PER_1MS,
	    time_diff_max * 1.0 / RF_TICKS_PER_1MS,
	    data_rate);
   }
   void show_one(Logger & log) {
      log.printf("| pkt: %u, err: %u, ign: %u, data: %u, rssi: (%d) %d %d\n",
	    pkt_num,
	    pkt_err_num,
	    pkt_ign_num,
	    data_len_sum,
	    rssi_min,
	    rssi_min_ok,
	    rssi_max);
   }
} pkt_stats;

#include "u2s_24bit.h"

bool write_data(FILE * f_out, const uint8_t * data, unsigned length)
{
   enum { adc_ch_num = 8 };

   // number of bytes in one ADC sample
   enum { ts_size = 4 };
   enum { adc_data_size = (adc_ch_num+1) * 3 };
   enum { adxl_data_size = 3*2 };

   // check data size
   if ((length % adc_data_size) != (ts_size + adxl_data_size) )
      return false;

   unsigned samples = length / adc_data_size;
   if (samples == 0)
      return false;

   // write timestamp
   fprintf(f_out, "%u\n", *(const uint32_t *)data);

   const uint8_t * adc_data = &data[ts_size];

   // check first ADC word
   for(unsigned s=0; s < samples; ++s) {
      if (adc_data[adc_data_size * s + 0] != 0xc0)
         return false;
      if (adc_data[adc_data_size * s + 1] != 0x00)
         return false;
      if (adc_data[adc_data_size * s + 2] != 0x00)
         return false;
   }

   // write ADC samples/channels
   for(unsigned s=0; s < samples; ++s) {
      // skip first word
      for(unsigned ch=1; ch < adc_ch_num+1; ++ch) {
         unsigned val =
            (adc_data[adc_data_size * s + 3*ch + 0] << 16) |
            (adc_data[adc_data_size * s + 3*ch + 1] <<  8) |
            (adc_data[adc_data_size * s + 3*ch + 2] <<  0);
         signed vs = u2s_24bit(val);
         fprintf(f_out, "%d ", vs);
      }
      fprintf(f_out, "\n");
   }

   // write ADXL data
   const uint8_t * adxl_data = &data[ts_size + adc_data_size * samples];

   for(unsigned ch=0; ch<3; ++ch) {
      int16_t val =
	 (adxl_data[2*ch + 0] << 0) |
	 (adxl_data[2*ch + 1] << 8);
      fprintf(f_out, "%d ", val);
   }
   fprintf(f_out, "\n");

   return true;
}

#include "BLE.h"
#include "rf_proto.h"

void show_pkt_adv(Logger & log, const Pkt & pkt)
{
   log.enable_stdout(false);
   dump_data(log, "Adv addr", pkt.f_ble_data(), BLE_ADDR_LEN);
   const uint8_t * adv_data = &pkt.f_ble_data()[BLE_ADDR_LEN];
   unsigned adv_data_len = pkt.f_ble_len() - BLE_ADDR_LEN;
   dump_data(log, "Adv data", adv_data, adv_data_len);
   log.enable_stdout(true);
}

bool show_pkt_time_sync(Logger & log, const Pkt & pkt)
{
   dump_data(log, "Addr", pkt.f_ble_data(), BLE_ADDR_LEN);
   const uint8_t * adv_data = &pkt.f_ble_data()[BLE_ADDR_LEN];
   unsigned adv_data_len = pkt.f_ble_len() - BLE_ADDR_LEN;
   const struct rf_ts_adv2_data_t * adv2_p = reinterpret_cast<const rf_ts_adv2_data_t *> (adv_data);

   if (adv_data_len != sizeof(*adv2_p)) {
      log.printf("invalid len, got: %u, exp: >%u\n", adv_data_len, sizeof(*adv2_p));
      return false;
   }

   log.printf("d: %u rx: %u seq: %02x rssi: %d\n",
	 pkt.f_time(),
	 adv2_p->rx_time,
	 adv2_p->rx_seq,
	 adv2_p->rx_rssi);

   return true;
}

void show_pkt_rsp(Logger & log, const Pkt & pkt)
{
   dump_data(log, "Rsp addr", pkt.f_ble_data(), BLE_ADDR_LEN);
   const uint8_t * rsp_data = &pkt.f_ble_data()[BLE_ADDR_LEN];
   unsigned rsp_data_len = pkt.f_ble_len() - BLE_ADDR_LEN;

   const struct rf_scan_rsp_data_t * rsp_p = reinterpret_cast<const rf_scan_rsp_data_t *> (rsp_data);
   if (rsp_data_len < sizeof(rsp_p->hdr)) {
      log.printf("invalid len, got: %u, exp: >%u\n", rsp_data_len, sizeof(rsp_p->hdr));
      return;
   }

   log.printf("seq: %02x, cmd: %x ", rsp_p->hdr.seq, rsp_p->hdr.cmd);
   auto cmd = rsp_p->hdr.cmd;
   if (cmd >=SR_CMD_SET_POWER && cmd <=SR_CMD_SET_POWER + 0xF)
        cmd= SR_CMD_SET_POWER;
   switch (cmd) {
      case SR_CMD_SET_POWER:
      case SR_CMD_HW_STAT:
         log.printf("HW_STAT2, Vcc: %.3fV, Temp: %uC, Pwr: %u, Rssi: %d, UpTime: %.3f\n",
               get_u16(rsp_p->data.sw_date, 0) * 0.001,
               get_u8( rsp_p->data.sw_date, 6),
	       get_u8( rsp_p->data.sw_date, 7),
               get_i8( rsp_p->data.sw_date, 8),
	       get_u32(rsp_p->data.sw_date, 2) * 1.0 / 100000);
         {
            unsigned exp_len = sizeof(rsp_p->hdr) + 2+4+4;
            if (rsp_data_len != exp_len)
               log.printf("invalid len, got: %u, exp: %u\n", rsp_data_len, exp_len);
         }
         break;

      case SR_CMD_SW_DATE:
         log.printf("SW_DATE, \"%.20s\"\n", rsp_p->data.sw_date);
         {
            unsigned exp_len = sizeof(rsp_p->hdr) + sizeof(rsp_p->data.sw_date);
            if (rsp_data_len != exp_len)
               log.printf("invalid len, got: %u, exp: %u\n", rsp_data_len, exp_len);
         }
         break;

      case SR_CMD_TR_STAT:
      case SR_CMD_START:
      case SR_CMD_START_PURE:
      case SR_CMD_TIME_SYNC:
         log.printf("TR_STAT, add1: %u, add2: %u, cmd: %u, tx: %u, ack: %u, re: %u, done: %u, rx: %u, err: %u, ign: %u, empty: %u, rssi: %d %d, res: %x,%x\n",
               rsp_p->data.tr_stat.add1_pkt_cnt,
               rsp_p->data.tr_stat.add2_pkt_cnt,
               rsp_p->data.tr_stat.rf_cmd_cnt,
               rsp_p->data.tr_stat.s_tx,
               rsp_p->data.tr_stat.s_tx_acked,
               rsp_p->data.tr_stat.s_tx_retrans,
               rsp_p->data.tr_stat.s_tx_done,
               rsp_p->data.tr_stat.s_rx,
               rsp_p->data.tr_stat.s_rx_err,
               rsp_p->data.tr_stat.s_rx_ign,
               rsp_p->data.tr_stat.s_rx_empty,
               rsp_p->data.tr_stat.rssi_min,
               rsp_p->data.tr_stat.rssi_max,
               rsp_p->data.tr_stat.error[0],
               rsp_p->data.tr_stat.error[1]);
         {
            unsigned exp_len = sizeof(rsp_p->hdr) + sizeof(rsp_p->data.tr_stat);
            if (rsp_data_len != exp_len)
               log.printf("invalid len, got: %u, exp: %u\n", rsp_data_len, exp_len);
         }
         break;

      default:
         dump_data(log, "XXX", &rsp_data[2], rsp_data_len-2);
         break;
   }
}

bool rf_scanner(Logger & log, FTDI & ftdi, Msg & m)
{
   pkt_stats.clear();

   uint8_t tx_ch = cmd_rf_scanner;
   if (!ftdi_write_and_check(log, ftdi, &tx_ch, 1))
      return false;

   Pkt pkt_adv;
   Pkt pkt_rsp;
   {
      uint32_t time_prev = 0;
      bool first = true;
      while(1) {
         Pkt pkt;
	 if (!m.read_any(log, ftdi, pkt)) {
            m.dump(log);
	    dump_rx(log, ftdi, 0x200);
	    break;
	 }
         if (! pkt.is_valid())
            break;

	 uint32_t time = pkt.f_time();
	 uint32_t time_diff = first ? 0 : (time - time_prev);
	 time_prev = time;
	 first = false;

	 bool valid_data = pkt_stats.add(pkt, time_diff);

	 log.enable_stdout(false);
	 uint8_t ble_hdr = pkt.f_ble_hdr();
         log.printf("rx_len: %u, status: %02x, rssi: %d, dt: %.3fms, hdr: %02x, BLE len: %u\n",
               pkt.f_len(),
               pkt.f_status(),
               pkt.f_rssi(),
               time_diff * 1.0 / RF_TICKS_PER_1MS,
               ble_hdr,
               pkt.f_ble_len());

	 if (valid_data) {
	    switch (ble_hdr & BLE_PDU_TYPE_MASK) {
	       case BLE_PDU_TYPE_ADV_IND:
		  pkt_adv = pkt;
		  break;
	       case BLE_PDU_TYPE_SCAN_RSP:
		  pkt_rsp = pkt;
		  break;
	    }
	    for(unsigned i=0; i<pkt.f_ble_len(); ++i)
	       log.printf(" %02x",  pkt.f_ble_data()[i]);
	 }
	 log.printf("\n");
	 log.enable_stdout(true);
      }
   }

   if (pkt_adv.is_valid()) {
      show_pkt_adv(log, pkt_adv);
   } else {
      log.printf("nothing received\n");
   }

   bool rf_rx = false;
   if (pkt_rsp.is_valid()) {
      show_pkt_rsp(log, pkt_rsp);
      rf_rx = true;
   }

   if (!m.got_msg())
      m.read(log, ftdi);

   bool res = false;
   for(unsigned i=0; i<3; ++i) {
      if (m.got_msg()) {
	 if (m.parse(log)) {
	    unsigned rx_ch = m.m_rx[msg_rx_ch_num - 1];
	    if (rx_ch == tx_ch) {
	       if (m.check_resp_rf_scanner(log, false)) {
		  res = true;
		  break;
	       }
	    } else
	       log.printf("tx/rx mismatch exp: %02x got: %02x\n", tx_ch, rx_ch);
	 } else
	    m.dump(log);
      }
      m.read(log, ftdi);
   }

   log.enable_stdout(false);
   pkt_stats.show(log);
   log.enable_stdout(true);

   return res && rf_rx;
}
#define US 1000000L
typedef struct {
	uint64_t pc_tx, head_rx, head_tx_offset, pc_rx;
} sync_times_t;

bool rf_time_sync(Logger_C & log, FTDI & ftdi, Msg & m, uint8_t tx_ch, FILE * f_out, bool verbose, sync_times_t * measurements=NULL)
{
   pkt_stats.clear();

   timestamp_t t1, t2;
   get_timestamp(t1); // time before USB write

   if (!ftdi_write_and_check(log, ftdi, &tx_ch, 1))
      return false;
   log.enable_stdout(false);
   Pkt pkt_adv;
   while(1) {
         Pkt pkt;
	 timestamp_t * tp = pkt_adv.is_valid() ? 0 : &t2;
	 if (!m.read_any(log, ftdi, pkt, tp)) {
            m.dump(log);
	    dump_rx(log, ftdi, 0x200);
	    break;
	 }

         if (! pkt.is_valid())
            break;

	 bool valid_data = pkt_stats.add(pkt, 0);

	 uint8_t ble_hdr = pkt.f_ble_hdr();
         log.printf("rx_len: %u, status: %02x, rssi: %d, hdr: %02x, BLE len: %u\n",
               pkt.f_len(),
               pkt.f_status(),
               pkt.f_rssi(),
               ble_hdr,
               pkt.f_ble_len());

	 if (valid_data) {
	    switch (ble_hdr & BLE_PDU_TYPE_MASK) {
	       case BLE_PDU_TYPE_ADV_NONCONN_IND:
		  pkt_adv = pkt;
		  break;
	    }
	    for(unsigned i=0; i<pkt.f_ble_len(); ++i)
	       log.printf(" %02x",  pkt.f_ble_data()[i]);
	 }
	 log.printf("\n");
   }

   bool pkt_ok = false;

   if (pkt_adv.is_valid()) {
      pkt_ok = show_pkt_time_sync(log, pkt_adv);
   }

   log.printf("1: %f 2: %f\n",
	 t1, t2);

   if (!m.got_msg())
      m.read(log, ftdi);

   bool msg_ok = false;
   for(unsigned i=0; i<3; ++i) {
      if (m.got_msg()) {
	 if (m.parse(log)) {
	    unsigned rx_ch = m.m_rx[msg_rx_ch_num - 1];
	    if (rx_ch == tx_ch) {
	       if (m.check_resp_rf_time_sync(log, false)) {
		  msg_ok = true;
		  break;
	       }
	    } else
	       log.printf("tx/rx mismatch exp: %02x got: %02x\n", tx_ch, rx_ch);
	 } else
	    m.dump(log);
      }
      m.read(log, ftdi);
   }

   log.enable_stdout(verbose);
   pkt_stats.show_one(log);
   log.enable_stdout(true);

   if (pkt_ok && msg_ok) {      
      const uint8_t * adv_data = &pkt_adv.f_ble_data()[BLE_ADDR_LEN];
      const struct rf_ts_adv2_data_t * adv2_p = reinterpret_cast<const rf_ts_adv2_data_t *> (adv_data);
      if (adv2_p->rx_seq != m.resp.rf_time_sync.tx_seq) {
	 log.printf("time_sync: seq mismatch tx: %02x rx: %02x\n",
	       m.resp.rf_time_sync.tx_seq,
	       adv2_p->rx_seq);
	 return false;
      }

      uint32_t h_rx = adv2_p->rx_time;
      uint32_t d_rx = pkt_adv.f_time();
      uint32_t d_uart_rx = m.resp.rf_time_sync.uart_rx_time;
      uint32_t d_uart_tx = m.resp.rf_time_sync.uart_tx_time;
	  if (f_out)
		  fprintf(f_out, "%.3f %.3f %u %u %u %u\n",
			t1,t2,
			d_uart_rx,
			d_rx,
			d_uart_tx,
			h_rx);
	  if (measurements) {
		  measurements->pc_tx = t1 * 1000000;
		  measurements->head_rx = h_rx;
		  measurements->head_tx_offset = 1000;
		  measurements->pc_rx = t2 * 1000000;
	  }
   } 
   
   return pkt_ok && msg_ok;
}


bool rf_rx_data_start(Logger & log, FTDI & ftdi, Msg & m, uint8_t cmd)
{
   rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, cmd);
   rf_scanner(log, ftdi, m);

   pkt_stats.clear();

   uint8_t tx_ch = cmd_rf_run;
   return ftdi_write_and_check(log, ftdi, &tx_ch, 1);
}

bool rf_rx_data(Logger & log, FTDI & ftdi, Msg & m, const char * filename, unsigned pkt_num)
{
   FILE * f_out = fopen(filename, "w");
   assert(f_out != NULL);

   bool verbose = false;
   bool res = true;

   uint32_t time_prev = 0;
   for(unsigned i=0; i < pkt_num; ++i) {
      Pkt pkt;
      if (!m.read_any(log, ftdi, pkt)) {
         m.dump(log);
         dump_rx(log, ftdi, 0x200);
         res = false;
         break;
      }
      if (! pkt.is_valid()) {
         res = false;
         break;
      }

      uint32_t time = pkt.f_time();
      uint32_t time_diff = (i == 0) ? 0 : (time - time_prev);
      time_prev = time;

      bool valid_data = pkt_stats.add(pkt, time_diff);

      uint8_t status = pkt.f_status();
      int8_t  rssi   = pkt.f_rssi();
      if ((verbose) || ((i % 100) == 0))
         log.printf("%3u: rx_len: %u, status: %02x, rssi: %d, dt: %.3fms, hdr: %02x, BLE len: %u\n",
               i,
               pkt.f_len(),
               status, rssi,
               time_diff * 1.0 / RF_TICKS_PER_1MS,
               pkt.f_ble_hdr(),
               pkt.f_ble_len());

      if (!valid_data)
         continue; // skip

      if (write_data(f_out, pkt.f_ble_data(), pkt.f_ble_len()))
         continue; // data format ok

      fprintf(f_out, "%02x %d:", status, rssi);
      for(unsigned i=0; i<pkt.f_ble_len(); ++i)
         fprintf(f_out, " %02x",  pkt.f_ble_data()[i]);
      fprintf(f_out, "\n");
   }

   fclose(f_out);

   return res;
}

bool rf_rx_data_end(Logger & log, FTDI & ftdi, Msg & m)
{
   if (!m.got_msg()) {
      uint8_t tx_ch = cmd_nop;
      ftdi_write_and_check(log, ftdi, &tx_ch, 1);
      m.read(log, ftdi);
   }

   bool second_msg_read = true;
   unsigned res = 0;
   for(unsigned i=0; i<3; ++i) {
      if (m.got_msg()) {
         if (m.parse(log)) {
            unsigned rx_ch_1 = m.m_rx[msg_rx_ch_num - 1];
            unsigned rx_ch_2 = m.m_rx[msg_rx_ch_num - 2];
	    if ( (rx_ch_1 == cmd_rf_run) ||
	         ((rx_ch_1 == cmd_nop) && (rx_ch_2 == cmd_rf_run)) ) {
               if (m.check_resp_rf_rx(log, false)) {
                  ++res;
                  if ( (res >= 2) ||
		       (!second_msg_read && (res >= 1)) )
                     break;
               }
            } else
               log.printf("tx/rx mismatch exp: %02x got: %02x\n", cmd_rf_run, rx_ch_1);
         } else
	    m.dump(log);
      }
      m.read(log, ftdi);
   }

   pkt_stats.show(log);

   return res > 0;
}


void demo(Logger & log, FTDI & ftdi, unsigned transfer_time)
{
   ftdi.purge(FT_PURGE_RX);
   Msg m;

   // start communication with local HW
   {
      unsigned attempt = 0;
      while(1) {
         if (uart_tx_rx_test(log, ftdi, m, true))
            break; // OK
         ++attempt;
         if (attempt > 5)
            return;
      }
   }

   // check local HW status
   if (uart_cmd(log, ftdi, m, cmd_hw_id, false))
      m.check_resp_hw_id(log);

   if (uart_cmd(log, ftdi, m, cmd_hw_stat, false))
      m.check_resp_hw_stat(log);

   // find remote device, check status
   rf_config_set(log, ftdi, m, cmd_rf_set_power, 7); // 0dB
   rf_config_set(log, ftdi, m, cmd_rf_set_timeout, 30); // 3 sec
   rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_HW_STAT);

   // wait for RF reception
   while(! rf_scanner(log, ftdi, m)) { }

   rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_SW_DATE);
   rf_scanner(log, ftdi, m);
   rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_TR_STAT);
   rf_scanner(log, ftdi, m);
   rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_DEBUG);
   rf_scanner(log, ftdi, m);
   rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_SET_POWER + 7); // 0dB
   rf_scanner(log, ftdi, m);
   rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_HW_STAT);
   rf_scanner(log, ftdi, m);

   { // time sync
      unsigned num = 500;
      const char filename[] =
#ifdef __linux__
	 "/tmp/time_sync.txt";
#else
         "time_sync.txt";
#endif
      FILE * f_out = fopen(filename, "w");
      assert(f_out != NULL);

      rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_TIME_SYNC);
      rf_scanner(log, ftdi, m);

      for(unsigned i=0; i<num; ++i)
	 rf_time_sync(log, ftdi, m, cmd_rf_tsync, f_out, (i%50 == 0));

      rf_time_sync(log, ftdi, m, cmd_rf_ts_end, NULL, false);

      fclose(f_out);

      rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_TR_STAT);
      rf_scanner(log, ftdi, m);
      rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_HW_STAT);
      rf_scanner(log, ftdi, m);
      rf_scanner(log, ftdi, m);
   }

   // ADC data transfer
   rf_config_set(log, ftdi, m, cmd_rf_set_mode, 2);
   rf_config_set(log, ftdi, m, cmd_rf_set_timeout, 20); // 2 sec

   {
      rf_rx_data_start(log, ftdi, m, SR_CMD_START); // start

      unsigned pkt_num = transfer_time * 500 / 4;
      const char filename[] =
#ifdef __linux__
	 "/tmp/data.1.txt";
#else
         "data.1.txt";
#endif
      rf_rx_data(log, ftdi, m, filename, pkt_num); // receive data
      rf_rx_data_end(log, ftdi, m); // read status

      // check status after transfer
      if (uart_cmd(log, ftdi, m, cmd_hw_stat, false))
	 m.check_resp_hw_stat(log);
   }

   {
      rf_rx_data_start(log, ftdi, m, SR_CMD_START_PURE); // start

      unsigned pkt_num = transfer_time * 500 / 4;
      const char filename[] =
#ifdef __linux__
	 "/tmp/data.2.txt";
#else
         "data.2.txt";
#endif
      rf_rx_data(log, ftdi, m, filename, pkt_num); // receive data
      rf_rx_data_end(log, ftdi, m); // read status
   }

   rf_config_set(log, ftdi, m, cmd_rf_set_timeout, 30); // 3 sec
   rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_HW_STAT);
   rf_scanner(log, ftdi, m);
   rf_scanner(log, ftdi, m);
   for(unsigned i=0; i<2; ++i) {
      bool res = true;
      rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_TR_STAT);
      res = rf_scanner(log, ftdi, m) && res;
      rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_SET_POWER + 5); // -6dB
      res = rf_scanner(log, ftdi, m) && res;
      rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_HW_STAT);
      res = rf_scanner(log, ftdi, m) && res;
      rf_config_set(log, ftdi, m, cmd_rf_set_power, 5); // -6dB
      if (res)
	 break;
   }
}

#include "ftdi_uart.h"

#ifndef __linux__
//#include "FTDI_select.h"
#endif

int demo_main(int argc, char *argv[])
{
   Logger
#ifdef __linux__
      log("demo_1.log");
#else
      log("demo_1.log");
#endif
   log.printf("demo_ts (compiled: " __DATE__ " " __TIME__ ") start ");
   log.timestamp();

   FTDI ftdi;
   int index = 0;

#ifdef __linux__
   unsigned transfer_time = 10; // 10 seconds

   if (argc > 1)
      index = atoi(argv[1]);
   if (argc > 2)
      transfer_time = atoi(argv[2]);
#else // !__linux__
   unsigned transfer_time = 120;
   /*
   {
      DWORD number;
      ftdi.list_devices(&number, NULL, FT_LIST_NUMBER_ONLY);
      if (! ftdi) {
	 log.printf("list_devices: %s\n", ftdi.status_msg());
	 log.timestamp();
	 log.flush();
	 getchar();
	 return 1;
      }
      log.printf("Number of FTDI devices present: %u\n", (unsigned)number);

      if (number > 1)
	 index = FTDI_select(log, ftdi, number);
   }*/
#endif

   if (!ftdi_open(log, ftdi, index, false)) {
      log.timestamp();
      log.flush();
#ifndef __linux__
      printf("\nPress enter to close this window\n");
      getchar();
#endif
      return 1;
   }

   ftdi_config(log, ftdi, 3000000, false); // 3Mb/sec

   if (ftdi_uart(log, ftdi))
      demo(log, ftdi, transfer_time);

   log.printf("\n");

   ftdi_close(log, ftdi);

   log.printf("end ");
   log.timestamp();
   log.flush();

#ifndef __linux__
   printf("\nPress enter to close this window\n");
   getchar();
#endif
   return 0;
}
