// EEG32 demo 2
// © Copyright 2018 Pawel Jewstafjew Pawel<dot>Jewstafjew<at>gmail<dot>com

#include <assert.h>
#include <stdio.h>
#include <stdint.h>

#include <libusb-1.0/libusb.h>
#if __linux__
#include <unistd.h>
#else
#include <io.h>
#include <windows.h>

void usleep(__int64 usec)
{
	HANDLE timer;
	LARGE_INTEGER ft;

	ft.QuadPart = -(10 * usec); // Convert to 100 nanosecond interval, negative value indicates relative time

	timer = CreateWaitableTimer(NULL, TRUE, NULL);
	SetWaitableTimer(timer, &ft, 0, NULL, NULL, 0);
	WaitForSingleObject(timer, INFINITE);
	CloseHandle(timer);
}

#endif
#include "ctrl_seq.h"

// check response against expected pattern
bool usb_ctrl_check_response(const ctrl_seq_t & ctrl_seq, const uint8_t * data, unsigned len)
{
   if (len != ctrl_seq.length) {
      printf("usb_ctrl_check_response: wrong length %u / %u\n", len, ctrl_seq.length);
      return false;
   }
   unsigned mismatch = 0;
   for(unsigned i=0; i<ctrl_seq.length; ++i) {
      uint8_t got = data[i];
      uint8_t exp = ctrl_seq.data_in[i];
      uint8_t mask = ctrl_seq.data_in_mask[i];
      if ((got & mask) != exp) {
         printf("ctrl %x: got: %02x, exp: %02x, mask: %02x\n", i, got, exp, mask);
         ++mismatch;
         if (mismatch > 10)
            break;
      }
   }
   return (mismatch == 0);
}

#include "usb_api.h"

enum { usb_timeout = 50 };

// send Ctrl cmd, receive Ctrl response, check response
bool usb_ctrl_out_in(libusb_device_handle * dev_handle, const ctrl_seq_t & ctrl_seq, uint8_t * rx_buf, unsigned rx_buf_len)
{
   assert(ctrl_seq.length < PKT_LEN_CTRL);
   assert(rx_buf_len >= PKT_LEN_CTRL);

   { // send Ctrl cmd
      int transferred = 0;
      int res = libusb_bulk_transfer(dev_handle, EP_C_OUT, (unsigned char *)ctrl_seq.data_out, ctrl_seq.length, &transferred, usb_timeout);
      if (res) {
	 printf("OUT Transfer failed: %d\n", res);
	 return false;
      }
      if (transferred != (int)ctrl_seq.length) {
	 printf("Tx len: %d, exp: %u\n", transferred, ctrl_seq.length);
      }
   }

   bool status = true;
   { // receive Ctrl response
      int transferred = 0;
      int res = libusb_bulk_transfer(dev_handle, EP_C_IN, rx_buf, rx_buf_len, &transferred, usb_timeout); 
      if (res) {
	 printf("IN Transfer failed: %d (with %d/%d bytes)\n", res, transferred, ctrl_seq.length);
	 status = false;
      } else
      if (transferred > 0) {
	 status = usb_ctrl_check_response(ctrl_seq, rx_buf, transferred);
	 if (status)
	    printf("OK\n");
      }
   }
   return status;
}

bool usb_ctrl_out_in(libusb_device_handle * dev_handle, const ctrl_seq_t & ctrl_seq)
{
   uint8_t rx_buf[PKT_LEN_CTRL];
   return usb_ctrl_out_in(dev_handle, ctrl_seq, rx_buf, sizeof(rx_buf));
}

bool usb_set_alt(libusb_device_handle * dh, int interface, int alt)
{
   int res = libusb_set_interface_alt_setting(dh, interface, alt);
   if (res) {
      printf("libusb_set_interface_alt_setting(%d,%d): %d\n", interface, alt, res);
      libusb_close(dh);
      return false;
   }
   return true;
}

libusb_device_handle * usb_open_claim_set(libusb_device * dev, int interface, int alt)
{
   libusb_device_handle * dh;
   int res;
   res = libusb_open(dev, &dh);
   if (res) {
      printf("libusb_open: %d\n", res);
      return 0;
   }
   res = libusb_detach_kernel_driver(dh, interface);
   if (res) {
      printf("libusb_detach(%d): %d\n", interface, res);
   }
   res = libusb_claim_interface(dh, interface);
   if (res) {
      printf("libusb_claim(%d): %d\n", interface, res);
      libusb_close(dh);
      return 0;
   }
   if (! usb_set_alt(dh, interface, alt)) {
      libusb_close(dh);
      return 0;
   }

   return dh;
}

bool usb_get_status(libusb_device_handle * dev_handle, bool & ready)
{
   uint8_t buf[0x20];

   int res = libusb_control_transfer(dev_handle,
	 0xC0, VC_STATUS, 0, 0,
	 buf, sizeof(buf), usb_timeout);

   if (res != VC_STATUS_LEN) {
      printf("libusb_control_transfer(VC_STATUS): %d\n", res);
      return false;
   }

   if (buf[0] != VC_ST_VERSION) {
      printf("VC_STATUS: wrong version\n");
      printf("VC_STATUS:");
      for(int i=0; i<res; ++i)
	 printf(" %02x", buf[i]);
      printf("\n");
      return false;
   }

   switch (buf[1]) {
      case VC_ST_READY:
	 printf("device status: OK\n");
	 ready = true;
	 return true;

      case VC_ST_STARTUP:
	 ready = false;
	 return true;

      default:
	 printf("VC_STATUS:");
	 for(int i=0; i<res; ++i)
	    printf(" %02x", buf[i]);
	 printf("\n");
	 return false;
   }
}


inline static
signed u2s_24bit(unsigned v)
{
   if (v < (1<<23))
      return v;
   else
      return v - (1<<24);
}

inline static
unsigned b2u24(const uint8_t * data)
{
   unsigned v = 0;
   for(unsigned i=0; i<3; ++i) {
      v <<= 8;
      v |= data[i];
   }
   return v;
}

enum {
   ADS_CH_NUM = 8,
   ADS_NUMBER = 4,
   ads_ch_data_len = (1+ADS_CH_NUM) * 3,
   pkt_len_expected = 4 + ADS_NUMBER * ads_ch_data_len
};

static unsigned ads_data_write(FILE * out, const uint8_t * data, unsigned len)
{
   if ((len % pkt_len_expected) != 0) {
      // dump all data
      fprintf(out, "# %u", len);
      for(unsigned i=0; i<len; ++i)
         fprintf(out, " %02x", data[i]);
      fprintf(out, "\n");
      return 0;
   } else {
      for(unsigned s=0; s < len / pkt_len_expected; ++s) {
	 // timestamp, event
	 unsigned timestamp = 0;
	 for(unsigned i=0; i<3; ++i)
	    timestamp += data[i] << (i*8);
	 unsigned event = data[3];
	 fprintf(out, "%u %x ", timestamp, event);

	 // status words
	 for(unsigned n=0; n<ADS_NUMBER; ++n) {
	    unsigned v = b2u24(&data[4 + n * ads_ch_data_len + 0]);
	    fprintf(out, "0x%06x ", v);
	 }

	 // ADC data
	 for(unsigned n=0; n<ADS_NUMBER; ++n) {
	    for(unsigned i=1; i<1+ADS_CH_NUM; ++i) {
	       unsigned v = b2u24(&data[4 + n * ads_ch_data_len + i*3]);
	       fprintf(out, "%d ", u2s_24bit(v));
	    }
	 }

	 fprintf(out, "\n");
	 data += pkt_len_expected;
      }
      return len / pkt_len_expected;
   }
}

inline static
unsigned & transfer_completed(struct libusb_transfer * transfer)
{
   union int_ptr_union_t {
      void * ptr;
      unsigned _unsigned;
   } * ptr = (union int_ptr_union_t *)&transfer->user_data;
   return ptr->_unsigned;
}
extern "C" {
	static void LIBUSB_CALL usb_io_transfer_cb(struct libusb_transfer * transfer)
	{
	   transfer_completed(transfer) = 1;
	}
}
static bool submit(struct libusb_transfer * transfer)
{
   transfer_completed(transfer) = 0;
   int res = libusb_submit_transfer(transfer);
   if (res == LIBUSB_SUCCESS)
      return true;

   printf("libusb_submit_transfer: %d\n", res);
   transfer_completed(transfer) = 1;
   assert(0);
   return false;
}

libusb_context * libusb_ctx;

void usb_data_in(libusb_device_handle * dev_handle, unsigned number, unsigned interval, FILE * out)
{
   enum {
      pkt_num = 32,
      buf_num = 8,
      pkt_len = PKT_LEN_ISO,
      timeout = 100
   };

   unsigned transfer_num = (number/interval*8 + pkt_num-1) / pkt_num;
   if (transfer_num < buf_num)
      transfer_num = buf_num;

   uint8_t * const data_area = new uint8_t [buf_num*pkt_num*pkt_len];
   struct libusb_transfer ** const transfers = new struct libusb_transfer * [buf_num];
   for(unsigned i=0; i<buf_num; ++i)
      transfers[i] = libusb_alloc_transfer(pkt_num);

   {
      const unsigned data_buf_size = pkt_num*pkt_len;

      for(unsigned i=0; i<buf_num; ++i) {
         struct libusb_transfer * const transfer = transfers[i];
         uint8_t * const buf = &data_area[data_buf_size * i];

	 libusb_fill_iso_transfer(transfer, dev_handle, EP_D_IN, buf, data_buf_size, pkt_num, usb_io_transfer_cb, 0, timeout);
	 libusb_set_iso_packet_lengths(transfer, pkt_len);
      }
   }

   printf("status check, mismatch expected: ");
   usb_ctrl_out_in(dev_handle, ctrl_seq_check);

   printf("expected transfer time: %.3fs\n", transfer_num*pkt_num * interval * 0.125 / 1000);
   for(unsigned i=0; i<buf_num; ++i)
      submit(transfers[i]);

   unsigned idx_transfer = 0;
   unsigned idx_submit = 0;
   unsigned left_to_submit = transfer_num - buf_num;
   unsigned left_to_finish = transfer_num;
   unsigned received = 0;
   while(left_to_finish > 0) {
      {
	 struct libusb_transfer * transfer = transfers[idx_transfer];
	 idx_transfer = (idx_transfer + 1) % buf_num;
	 {
	    volatile const unsigned * completed = &transfer_completed(transfer);
	    while (! *completed) {
	       int res = libusb_handle_events(libusb_ctx);
	       if (res < 0) {
		  if (res == LIBUSB_ERROR_INTERRUPTED)
		     continue;

		  printf("libusb_handle_events: %d\n", res);
		  assert(0);
	       }
	    }
	 }
	 const uint8_t * data_buf = transfer->buffer;
	 const unsigned pkt_len = transfer->iso_packet_desc[0].length;
	 bool empty = true;
	 for(int i = 0; i < transfer->num_iso_packets; i++) {
	    const struct libusb_iso_packet_descriptor * desc = &transfer->iso_packet_desc[i];
	    if (desc->status == LIBUSB_TRANSFER_COMPLETED)
	       if (desc->actual_length > 0) {
		  const uint8_t * pkt_data = &data_buf[i*pkt_len];
		  received += ads_data_write(out, pkt_data, desc->actual_length);
		  empty = false;
	       }
	 }
	 if (empty)
		 fprintf(stderr, "Empty transfer after %d packets\n",received);
      }

      --left_to_finish;

      if (left_to_submit > 0) {
	 submit(transfers[idx_submit]);
	 idx_submit = (idx_submit + 1) % buf_num;
	 --left_to_submit;
      }
   }
   printf("%u samples received\n", received);

   for(unsigned i=0; i<buf_num; ++i)
      libusb_free_transfer(transfers[i]);
   delete[] transfers;
   delete[] data_area;
}

void adc_save_data(libusb_device_handle * dev_handle, const char * filename, unsigned number, bool fast)
{
   printf("save ADC data to %s\n", filename);

   FILE * out = fopen(filename, "w");
   assert(out);

   printf("ctrl_seq_start\n");
   if (!usb_ctrl_out_in(dev_handle, ctrl_seq_start)) {
      printf("failed\n");
      return;
   }

   if (! usb_set_alt(dev_handle, USB_IFC_ID, fast ? USB_ALT_ISO_1 : USB_ALT_ISO_2))
      return;

   usb_data_in(dev_handle, number, fast ? 1 : 2, out);

   printf("status check, mismatch expected: ");
   usb_ctrl_out_in(dev_handle, ctrl_seq_check);

   if (! usb_set_alt(dev_handle, USB_IFC_ID, USB_ALT_CTRL))
      return;

   printf("ctrl_seq_stop\n");
   if (!usb_ctrl_out_in(dev_handle, ctrl_seq_stop)) {
      printf("failed\n");
   }

   fclose(out);
}

bool get_time(libusb_device_handle * dev_handle)
{
   printf("get_time\n");

   for(unsigned j=0; j<4; ++j) {
      uint8_t rx_buf[PKT_LEN_CTRL];

      if (!usb_ctrl_out_in(dev_handle, ctrl_seq_get_time, rx_buf, sizeof(rx_buf))) {
         printf("ctrl_seq_get_time failed\n");
         return false;
      }

      unsigned timestamp = 0;
      for(unsigned i=0; i<6; ++i)
         timestamp |= (rx_buf[1+i] & 0xf) << (i*4);

      printf("timestamp: %u\n", timestamp);
   }

   return true;
}

void adc_demo(libusb_device_handle * dev_handle)
{
   printf("ctrl_seq_init\n");
   if (!usb_ctrl_out_in(dev_handle, ctrl_seq_init)) {
      printf("failed\n");
      return;
   }

   printf("ctrl_seq_stop\n");
   if (!usb_ctrl_out_in(dev_handle, ctrl_seq_stop)) {
      printf("failed\n");
      return;
   }

   if (!get_time(dev_handle))
      return;

   printf("ctrl_seq_config_500\n");
   if (!usb_ctrl_out_in(dev_handle, ctrl_seq_config_500)) {
      printf("failed\n");
      return;
   }

   adc_save_data(dev_handle, "adc_500.txt", 1000, false); // 1000ms

   printf("ctrl_seq_config_imp_500\n");
   if (!usb_ctrl_out_in(dev_handle, ctrl_seq_config_imp_500)) {
      printf("failed\n");
      return;
   }

   adc_save_data(dev_handle, "adc_imp_500.txt", 1000, false); // 1000ms

   printf("ctrl_seq_config_2000\n");
   if (!usb_ctrl_out_in(dev_handle, ctrl_seq_config_2000)) {
      printf("failed\n");
      return;
   }

   adc_save_data(dev_handle, "adc_2000.txt", 1000, false); // 1000ms

   printf("ctrl_seq_config_4000\n");
   if (!usb_ctrl_out_in(dev_handle, ctrl_seq_config_4000)) {
      printf("failed\n");
      return;
   }

   adc_save_data(dev_handle, "adc_4000.txt", 1000, false); // 1000ms

   printf("ctrl_seq_config_imp_4000\n");
   if (!usb_ctrl_out_in(dev_handle, ctrl_seq_config_imp_4000)) {
      printf("failed\n");
      return;
   }

   adc_save_data(dev_handle, "adc_imp_4000.txt", 1000, false); // 1000ms

   printf("ctrl_seq_config_8000\n");
   if (!usb_ctrl_out_in(dev_handle, ctrl_seq_config_8000)) {
      printf("failed\n");
      return;
   }

   adc_save_data(dev_handle, "adc_8000.txt", 1000, false); // 1000ms

   printf("ctrl_seq_config_16000\n");
   if (!usb_ctrl_out_in(dev_handle, ctrl_seq_config_16000)) {
      printf("failed\n");
      return;
   }

   adc_save_data(dev_handle, "adc_16000.txt", 1000, true); // 1000ms

   printf("ctrl_seq_config_imp_16000\n");
   if (!usb_ctrl_out_in(dev_handle, ctrl_seq_config_imp_16000)) {
      printf("failed\n");
      return;
   }

   adc_save_data(dev_handle, "adc_imp_16000.txt", 1000, true); // 1000ms
}

static void delay(unsigned msec)
{
   usleep(msec * 1000);
}

bool adc_pwr_on(libusb_device_handle * dev_handle)
{
   for(unsigned i=0; i<3; ++i) {
      printf("ctrl_seq_pwr_on\n");
      if (!usb_ctrl_out_in(dev_handle, ctrl_seq_pwr_on)) {
	 printf("failed\n");
	 return false;
      }

      delay(50);

      printf("ctrl_seq_check\n");
      if (usb_ctrl_out_in(dev_handle, ctrl_seq_check))
	 return true;

      if (! usb_set_alt(dev_handle, USB_IFC_ID, USB_ALT_OFF))
	 return false;
      if (! usb_set_alt(dev_handle, USB_IFC_ID, USB_ALT_CTRL))
	 return false;
   }

   return false;
}


void usb_dev_handle(libusb_device_handle * dev_handle)
{
   while(1) {
      bool ready;
      if (! usb_get_status(dev_handle, ready))
	 return;

      if (ready)
	 break;

      printf("waiting for device startup to complete\n");
      delay(500);
   }

   if (! usb_set_alt(dev_handle, USB_IFC_ID, USB_ALT_CTRL))
      return;

   printf("ctrl_seq_check\n");
   if (!usb_ctrl_out_in(dev_handle, ctrl_seq_check)) {
      printf("failed\n");
      return;
   }

   if (!adc_pwr_on(dev_handle))
      return;

   delay(150);
   adc_demo(dev_handle);

   printf("ctrl_seq_pwr_off\n");
   if (!usb_ctrl_out_in(dev_handle, ctrl_seq_pwr_off)) {
      printf("failed\n");
   }
}

void usb_dev(libusb_device * dev)
{
   libusb_device_handle * dev_handle = usb_open_claim_set(dev, USB_IFC_ID, USB_ALT_OFF);
   if (!dev_handle)
      return;

   usb_dev_handle(dev_handle);

   int res = libusb_release_interface(dev_handle, USB_IFC_ID);
   if (res)
      printf("libusb_release: %d\n", res);
   libusb_close(dev_handle);
}

int main(int argc, char* argv[])
{
	setbuf(stdout, NULL);
   enum {
      CYP_VID = 0x04b4,
      CYP_PID = 0x8613,
   };

   {
      int res = libusb_init(&libusb_ctx);
      if (res) {
	 printf("libusb_init: %d\n", res);
         return 1;
      }
   }
   libusb_set_debug(libusb_ctx, LIBUSB_LOG_LEVEL_WARNING);

   // discover USB devices
   libusb_device ** dev_list;
   int dev_num = libusb_get_device_list(libusb_ctx, &dev_list);
   if (dev_num < 1) {
      printf("no USB device found (%d)\n", dev_num);
      libusb_exit(libusb_ctx);
      return 1;
   }

   for(int i=0; i<dev_num; ++i) {
      libusb_device * dev = dev_list[i];
      struct libusb_device_descriptor desc;
      int res = libusb_get_device_descriptor(dev, &desc);
      if (res) {
	 printf("%u:%u libusb_get_device_descriptor: %d\n",
	       libusb_get_bus_number(dev), libusb_get_device_address(dev), res);
	 continue;
      }
      printf("USB dev %d: %04X:%04X\n", i, desc.idVendor, desc.idProduct);
      if ( ((desc.idVendor == CYP_VID) && (desc.idProduct == CYP_PID)) ) {
	 printf("selected: %u:%u %04x:%04x:%04x\n",
	       libusb_get_bus_number(dev), libusb_get_device_address(dev),
	       desc.idVendor, desc.idProduct, desc.bcdDevice);

        usb_dev(dev);
	break;
      }
   }

   libusb_free_device_list(dev_list, 1);

   libusb_exit(libusb_ctx);
   usleep(100000000);
   return 0;
}
