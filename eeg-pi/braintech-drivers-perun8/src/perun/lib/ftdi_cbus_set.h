
#ifndef FTDI_BUS_SET_H
#define FTDI_BUS_SET_H

bool ftdi_cbus_set(Logger & log, FTDI & ftdi, unsigned v, unsigned dir)
{
   uint8_t b = (v & 0xF) | ((dir << 4) & 0xF0);

   if (! ftdi.set_bit_mode(b, FT_BITMODE_CBUS_BITBANG)) {
      log.printf("set bitmode CBUS error: (%d) %s\n", (unsigned)ftdi, ftdi.status_msg());
      return false;
   }

   return true;
}

#endif // FTDI_BUS_SET_H
