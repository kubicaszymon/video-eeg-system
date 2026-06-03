// RF proto
#ifdef _MSC_VER
#define PACKED_STRUCT(name) \
    __pragma(pack(push, 1)) struct name
#define ENDPACKED_STRUCT __pragma(pack(pop))
#elif defined(__GNUC__)
#define PACKED_STRUCT(name) struct __attribute__((packed)) name
#define ENDPACKED_STRUCT
#endif
struct rf_seq_cmd_t {
   uint8_t seq;  // sequence number
   uint8_t cmd;  // command
};

// data in SCAN_RSP packet
struct rf_scan_rsp_data_t {
   struct rf_seq_cmd_t hdr;
   union rf_scan_rsp_data_body_t {
      char sw_date[20]; // SW date string (DATE(11) + ' ' + TIME(8))
      struct rf_scan_rsp_tr_stat_t {
	 uint16_t add1_pkt_cnt; // count pkts added to empty queue
	 uint16_t add2_pkt_cnt; // count pkts added to non-empty queue
	 uint16_t rf_cmd_cnt;   // count RF Master commands
	 uint16_t s_tx;        // BLE stats
	 uint16_t s_tx_acked;
	 uint16_t s_tx_retrans;
	 uint16_t s_tx_done;
	 uint16_t s_rx;
	 uint16_t s_rx_err;
	 uint16_t s_rx_ign;
	 uint16_t s_rx_empty;
	 uint8_t error[2];
	 int8_t rssi_min;
	 int8_t rssi_max;
      } tr_stat;
   } data;
};

PACKED_STRUCT(rf_ts_adv2_data_t) {
   uint32_t rx_time;
   uint8_t  rx_seq;
   int8_t  rx_rssi;
};
ENDPACKED_STRUCT

enum { // SCAN_REQ command
  SR_CMD_HW_STAT = 0x00, // get hw_stat response
  SR_CMD_SW_DATE, // get SW date string response
  SR_CMD_TR_STAT, // get tr_stat response
  SR_CMD_START       = 0x5A, // start data transfer
  SR_CMD_START_PURE  = 0x5B, // start data transfer, lead-off det disabled

  SR_CMD_TIME_SYNC   = 0x60, // start time sync mode

  SR_CMD_SET_POWER  = 0xC0, // set Tx power
  SR_CMD_DEBUG      = 0xDB, // get debug response
};
