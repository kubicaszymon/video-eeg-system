// EEG32 load
// © Copyright 2018 Pawel Jewstafjew Pawel<dot>Jewstafjew<at>gmail<dot>com

#include <assert.h>
#include <stdio.h>
#include <stdint.h>

#include <libusb-1.0/libusb.h>

bool usb_ctrl_1(libusb_device_handle * dev_handle, bool sel, unsigned offset, uint8_t * data, unsigned length)
{
   enum { timeout = 100 };
   unsigned done = 0;
   while(done < length) {
      unsigned len = length - done;
      if (len > 0x1000)
         len = 0x1000;
      int res = libusb_control_transfer(dev_handle,
            sel ? 0x40 : 0xC0, 0xA0,
            offset + done, 0,
            &data[done], len, timeout);
      if (res != (int)len) {
         printf("libusb_control_transfer(ctrl_1): %d\n", res);
         return false;
      }
      done += res;
   }
   return true;
}

bool usb_ctrl_2(libusb_device_handle * dev_handle, bool & status)
{
   enum { timeout = 10 };

   uint8_t buf[0x20];
   int res = libusb_control_transfer(dev_handle,
	 0xC0, 0xAA,
	 0x55, 0,
	 buf, sizeof(buf), timeout);

   if (res != 8) {
      printf("libusb_control_transfer(ctrl_2): %d\n", res);
      return false;
   }

   if ( (buf[0] != 0x1D) || (buf[1] != 0) ) {
      printf("libusb_control_transfer(ctrl_2):");
      for(int i=0; i<res; ++i)
	 printf(" %02x", buf[i]);
      printf("\n");
      return false;
   }

   if ((buf[2] != 0) || (buf[3] != 0))
      status = false;

   return true;
}

bool set_flag(libusb_device_handle * dev_handle, uint8_t val)
{
   return usb_ctrl_1(dev_handle, true, 0xE600, &val, 1);
}

const uint8_t stage_1_data[] = {
#include "eeg_stage_1"
};

#include <string.h>

bool stage_1(libusb_device_handle * dev_handle)
{
   for(unsigned i=0; i<3; ++i) {
      const uint8_t * data = stage_1_data;
      const unsigned length = sizeof(stage_1_data);

      if (! set_flag(dev_handle, 1))
	 continue;

      if (! usb_ctrl_1(dev_handle, true, 0, const_cast <uint8_t *>(data), length))
	 continue;

      uint8_t buf[length];
      if (! usb_ctrl_1(dev_handle, false, 0, buf, length))
	 continue;

      if (memcmp(data, buf, length) != 0) {
	 printf("stage 1: error\n");
	 continue;
      }

      if (! set_flag(dev_handle, 0))
	 continue;

      printf("stage 1: OK\n");
      return true;
   }

   return false;
}

#include <time.h> // time()

bool send_data_1(libusb_device_handle * dev_handle, unsigned stage, const char * name, unsigned i, const uint8_t * data, unsigned length)
{
   enum { CHUNK_SIZE = 0x400 };
   enum { timeout = 10000 };
   time_t next_msg = 0;
   bool status = true;
   unsigned left = length;

   while (left > 0) {
      time_t now = time(0);
      if (now > next_msg) {
	 next_msg = now + 1;
	 printf("%s:%u - %2u%% done, DO NOT STOP THIS PROGRAM, DO NOT DISCONNECT THE DEVICE\n", name, i, (length - left) * 100 / length);
      }

      unsigned len = left;
      if (len > CHUNK_SIZE)
	 len = CHUNK_SIZE;

      int res = libusb_control_transfer(dev_handle,
	    0x40, 0xA2,
	    stage & 0xffff, stage >> 16,
	    (uint8_t *)data, len, timeout);

      if (res != (int)len) {
	 printf("libusb_control_transfer(ctrl_3): %d\n", res);
	 return false;
      }

      if (! usb_ctrl_2(dev_handle, status))
	 return false;

      stage += len;
      data += len;
      left -= len;
   }

   return status;
}

bool send_data(libusb_device_handle * dev_handle, unsigned stage, const char * name, const uint8_t * data, unsigned length)
{
   for(unsigned i = 0; i < 4; ++i)
      if (send_data_1(dev_handle, stage, name, i+1, data, length)) {
	 printf("%s: OK\n", name);
	 return true;
      }

   return false;
}

const uint8_t stage_2_data[] = {
#include "eeg_stage_2"
};

const uint8_t stage_3_data[] = {
#include "eeg_stage_3"
};

enum {
   STAGE_2 = 0x540000,
   STAGE_3 = 0x510000,
};

bool stage_2(libusb_device_handle * dev_handle)
{
   return send_data(dev_handle, STAGE_2, "stage 2", stage_2_data, sizeof(stage_2_data));
}

bool stage_3(libusb_device_handle * dev_handle)
{
   if (send_data(dev_handle, STAGE_3, "stage 3", stage_3_data, sizeof(stage_3_data)))
      return true;

   {
      static const uint8_t data[] = { 0xff };
      send_data(dev_handle, STAGE_3, "stage 3e", data, sizeof(data));
   }
   return false;
}

void usb_dev_handle(libusb_device_handle * dev_handle)
{
   if (! stage_1(dev_handle)) {
      printf("stage 1: FAILED\n");
      return;
   }

   {
      bool status;
      if (! usb_ctrl_2(dev_handle, status))
	 return;
   }

   if (! stage_2(dev_handle)) {
      printf("stage 2: FAILED\n");
      return;
   }

   if (! stage_3(dev_handle)) {
      printf("stage 3: FAILED\n");
      return;
   }

   printf("load completed\n");
}

void usb_dev(libusb_device * dev)
{
   libusb_device_handle * dev_handle;
   int res = libusb_open(dev, &dev_handle);
   if (res) {
      printf("libusb_open: %d\n", res);
      return;
   }

   usb_dev_handle(dev_handle);

   libusb_close(dev_handle);
}

int main(int argc, char* argv[])
{
   enum {
      CYP_VID = 0x04b4,
      CYP_PID = 0x8613,
   };

   libusb_context * libusb_ctx;

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

   return 0;
}
