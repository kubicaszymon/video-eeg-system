// BLE constants

#ifndef _BLE_H
#define _BLE_H

enum {
   BLE_ADDR_LEN = 6, // BLE address length

   BLE_LL_HDR_LEN = 2, // LL header length
   BLE_LL_DATA_MAX = 255, // max LL data length
};

enum { // BLE PDU Type values
   // see: BLE spec, Vol6, PartB, Link Layer Spec, page 40, "Advertising channel PDU Header’s PDU Type field encoding"
   BLE_PDU_TYPE_MASK  = 0x0f,

   BLE_PDU_TYPE_ADV_IND         = 0,
   BLE_PDU_TYPE_ADV_DIRECT_IND  = 1,
   BLE_PDU_TYPE_ADV_NONCONN_IND = 2,
   BLE_PDU_TYPE_SCAN_REQ        = 3,
   BLE_PDU_TYPE_SCAN_RSP        = 4,
   BLE_PDU_TYPE_CONNECT_REQ     = 5,
   BLE_PDU_TYPE_ADV_SCAN_IND    = 6
};

#endif // _BLE_H
