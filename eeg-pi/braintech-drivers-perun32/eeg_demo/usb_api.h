// defines for USB interface
// © Copyright 2018 Pawel Jewstafjew Pawel<dot>Jewstafjew<at>gmail<dot>com

#ifndef USB_API_H
#define USB_API_H

enum { // USB Interface
   USB_IFC_ID = 0,
};

enum {
   USB_ALT_OFF   = 0,
   USB_ALT_CTRL  = 1,
   USB_ALT_ISO_1 = 3,
   USB_ALT_ISO_2 = 4,
};

enum {
   EP_C_OUT = 0x06, // Ctrl OUT Endpoint (host sends command)
   EP_C_IN  = 0x88, // Ctrl IN  Endpoint (host reads response)
   EP_D_IN  = 0x82  // Data IN  Endpoint (host reads data)
};

enum { // USB packet length
   PKT_LEN_CTRL = 0x200, // Ctrl In/Out
   PKT_LEN_ISO  =   450, // Data In
};

enum vc_enum {
   VC_STATUS = 0xB0 // get status
};

enum vc_status_response_enum {
   VC_ST_VERSION = 0x10, // version code
   VC_ST_READY   = 0xA5,
   VC_ST_STARTUP = 0x51,
   VC_STATUS_LEN = 9 // VC_STATUS response length
};

#endif // USB_API_H
