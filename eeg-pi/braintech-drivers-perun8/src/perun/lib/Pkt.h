// RF packet
// (received from dongle)
#ifndef __pkt_h__

#define __pkt_h__
#include "get_u.h"

/*
struct msg_pkt_t {
   uint8_t hdr;
   uint8_t len[2]; // pkt length
//   uint8_t pkt_data[];
   uint8_t rssi;   // pkt RSSI
   uint8_t status; // pkt status
   uint8_t time[4]; // pkt timestamp
   uint8_t chk; // checksum
};
*/

class Pkt
{
public:
   enum {
      F_HDR_LEN = 1,
      F_LEN_POS = F_HDR_LEN,
      F_LEN_LEN = 2,
      F_LEN_END = F_LEN_POS + F_LEN_LEN,
      F_DATA_POS = F_LEN_END,

      F_BLE_HDR_LEN = 1, // BLE header, first byte, pkt type, flags
      F_BLE_HDR_POS = F_DATA_POS,
      F_BLE_LEN_LEN = 1, // BLE header, second byte, length
      F_BLE_LEN_POS = F_DATA_POS + F_BLE_HDR_LEN,

      F_BLE_DATA_POS = F_DATA_POS + F_BLE_HDR_LEN + F_BLE_LEN_LEN,

      F_CHK_LEN     = 1,
      F_CHK_EPOS    = F_CHK_LEN, // offset from the end
      F_TIME_LEN    = 4,
      F_TIME_EPOS   = F_CHK_EPOS + F_TIME_LEN, // offset from the end
      F_STATUS_LEN  = 1,
      F_STATUS_EPOS = F_TIME_EPOS + F_STATUS_LEN, // offset from the end
      F_RSSI_LEN    = 1,
      F_RSSI_EPOS   = F_STATUS_EPOS + F_RSSI_LEN, // offset from the end

      // minimum possible lenght (no data)
      PKT_MIN_LEN = F_HDR_LEN + F_LEN_LEN + F_CHK_LEN,
      // max data length + headers + some margin
      PKT_BUF_LEN = 256 + 16
   };
private:
   unsigned pkt_len;
   uint8_t pkt[PKT_BUF_LEN];
   uint8_t chk; // checksum
public:
   Pkt() : pkt_len(0), chk(0) {}
   void clear() {
      pkt_len = 0;
      chk = 0;
   }
   // append a byte to the end of the pkt
   void add_byte(uint8_t v) {
      assert(pkt_len < sizeof(pkt));
      pkt[pkt_len++] = v;
      chk ^= v;
   }
   unsigned raw_len() const { return pkt_len; }
   bool f_len_available() const {
      return pkt_len == F_LEN_END;
   }
   uint16_t f_len() const { // get lenght field
      assert(pkt_len >= F_LEN_END);
      return get_u16(pkt, F_LEN_POS);
   }
   const uint8_t * f_data() const { // get pointer to pkt data
      return &pkt[F_DATA_POS];
   }
   unsigned f_data_len() const { // pkt data len calculated from f_len
      return f_len() - (F_RSSI_LEN + F_STATUS_LEN + F_TIME_LEN);
   }
   uint8_t f_ble_hdr() const { // get BLE header, first byte
      return pkt[F_BLE_HDR_POS];
   }
   uint8_t f_ble_len() const { // get BLE data length, second byte of header
      return pkt[F_BLE_LEN_POS];
   }
   const uint8_t * f_ble_data() const { // get pointer to pkt BLE data
      return &pkt[F_BLE_DATA_POS];
   }
   unsigned f_ble_data_len() const { // pkt BLE data len calculated from f_len
      return f_data_len() - (F_BLE_HDR_LEN + F_BLE_LEN_LEN);
   }
   int8_t f_rssi() const { // get rssi field
      return pkt[pkt_len - F_RSSI_EPOS];
   }
   uint8_t f_status() const { // get status field
      return pkt[pkt_len - F_STATUS_EPOS];
   }
   uint32_t f_time() const { // get timestamp field
      return get_u32(pkt, pkt_len - F_TIME_EPOS);
   }
   unsigned total_lenght() const { // tatal "raw data" length
      return F_HDR_LEN + F_LEN_LEN + f_len() + F_CHK_LEN;
   }
   bool is_valid() const {
      return (pkt_len >= PKT_MIN_LEN)
         && (pkt_len == total_lenght())
         && (chk == 0);
   }
   void dump(Logger & log) const {
      log.printf("Pkt:");
      for(unsigned i=0; i<pkt_len; ++i)
         log.printf(" %02x", pkt[i]);
      log.printf(" (%u, %u)\n", pkt_len, chk);
   }
   void dump_chk(Logger & log) const {
      assert(pkt_len > 3);
      if (chk == 0)
         log.printf("chk OK\n");
      else {
         uint8_t chk_got = pkt[pkt_len - F_CHK_EPOS];
         uint8_t chk_exp = chk ^ chk_got;
         log.printf("wrong chk: %02x/%02x\n", chk_got, chk_exp);
      }
   }
};
#endif
