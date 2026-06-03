
enum { msg_hdr_len = 8 };
static const char msg_hdr[msg_hdr_len] = { 0x55, 0x55, 0x55, 0x55, 0x55, 0x55, 0x55, 0x55 };

enum { msg_rx_ch_num = 4 };

enum {
   cmd_arg_mask = 0x0f,
   cmd_nop      = 0x00, // NOP
   cmd_version  = 0x30, // return SW version
   cmd_hw_id    = 0x31, // return HW ID data
   cmd_hw_stat  = 0x32, // return VCC, TEMP

   cmd_rf_set_power       = 0x22, // set RF power
   cmd_rf_set_mode        = 0x27, // set mode
   cmd_rf_set_scan_cmd    = 0x28, // set scan_req_cmd
   cmd_rf_set_timeout     = 0x29, // set first Rx timeout

   cmd_rf_run     = 0x39, // RF BLE run data transfer
   cmd_rf_scanner = 0x3B, // RF BLE Scanner
   cmd_rf_tsync   = 0x3C, // RF time sync
   cmd_rf_ts_end  = 0x3D, // RF time sync end

   cmd_set_v0 = 0x40, // set bits  3..0, clear bits 15..4
   cmd_set_v1 = 0x50, // set bits  7..4
   cmd_set_v2 = 0x60, // set bits 11..8
   cmd_set_v3 = 0x70, // set bits 15..12
};

struct resp_hw_id_t {
   uint32_t dev_lot;  // Manufacturing Lot number
   uint32_t dev_coor; // Manufacturing coordinate
   uint32_t dev_id;   // ICEPICK_DEVICE_ID: PG_REV, WAFER_ID
   uint32_t dev_uid;  // USER_ID: PG_REV, PKG, PROTOCOL
   uint8_t  dev_rev;  // MISC_CONF_1: MINOR_REV
};

struct resp_hw_stat_t {
   uint32_t din;  // GPIO In
   uint32_t dout; // GPIO Out
   uint32_t doe;  // GPIO OE
   uint16_t vcc;  // Vcc
   uint16_t temp; // Temp
   uint8_t clk_hf; // HF clock source
   uint8_t clk_mf; // MF clock source
   uint8_t clk_lf; // LF clock source
};

struct resp_rf_config_t {
   uint16_t frequency;   // frequency in MHz
   uint16_t pkt_num;     // number of BLE data pkt to send/receive
   uint8_t  ble_channel; // BLE channel
   uint8_t  whitening;   // BLE whitening
   uint8_t  power_idx;   // index to rfPowerTable
   uint8_t  ble_data_size; // Tx data size in BLE data pkt
   uint8_t  adc_samples; // number of ADC samples per packet
   uint8_t  mode;
   uint8_t  scan_req_cmd;
   uint8_t  timeout;     // first Rx timeout in 0.1 sec
};

struct rf_event_log_t {
   uint32_t time;
   uint32_t event;
};
enum { resp_rf_dongle_event_num = 4 };
enum { resp_rf_scanner_event_num = 4 };
enum { resp_rf_time_sync_event_num = 3 };

struct resp_rf_dongle_t {
   struct rf_event_log_t event_log[resp_rf_dongle_event_num];
   uint32_t loop_time; // total time in for() loop
   uint32_t rf_time;   // total RF CMD time
   uint32_t uart_time;
   uint32_t cmd_time;
   uint16_t cmd_status;
   uint16_t cmd_status_ok;
   uint16_t s_tx;        // BLE stats
   uint16_t s_tx_acked;
   uint16_t s_tx_retrans;
   uint16_t s_tx_done;
   uint16_t s_rx;
   uint16_t s_rx_err;
   uint16_t s_rx_ign;
   uint16_t s_rx_empty;
   uint8_t event_cnt;
   uint8_t max_rx_buf; // max number of Rx buffers in use
};

struct resp_rf_scanner_t {
   struct rf_event_log_t event_log[resp_rf_scanner_event_num];
   uint32_t cmd_time;
   uint16_t cmd_status;
   uint8_t event_cnt;
   uint8_t s_tx;
   uint8_t s_backed;
   uint8_t s_rx_adv;
   uint8_t s_rx_adv_err;
   uint8_t s_rx_adv_ign;
   uint8_t s_rx_rsp;
   uint8_t s_rx_rsp_err;
   uint8_t s_rx_rsp_ign;
};

struct resp_rf_time_sync_t {
   struct rf_event_log_t event_log[resp_rf_time_sync_event_num];
   uint32_t uart_rx_time;
   uint32_t tx_time;
   uint32_t uart_tx_time;
   uint32_t cmd1_time;
   uint32_t cmd2_time;
   uint16_t cmd1_status;
   uint16_t cmd2_status;
   uint8_t event_cnt;
   uint8_t tx_seq;
   uint8_t s_tx_adv;
   uint8_t s_rx_adv;
   uint8_t s_rx_adv_err;
   uint8_t s_rx_adv_ign;
};

union resp_data_t {
   struct resp_hw_id_t     hw_id;
   struct resp_hw_stat_t   hw_stat;

   struct resp_rf_config_t    rf_config;
   struct resp_rf_dongle_t    rf_dongle;
   struct resp_rf_scanner_t   rf_scanner;
   struct resp_rf_time_sync_t rf_time_sync;

   uint16_t value;
};


// RF packet
enum { // used with msg_pkt_t
   pkt_hdr = 0xAC
};
