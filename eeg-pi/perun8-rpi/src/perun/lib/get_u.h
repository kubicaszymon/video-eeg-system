
__attribute__ (( pure ))
inline static uint8_t get_u8(const void * ptr, unsigned offset)
{
   const uint8_t * data = (const uint8_t *)ptr;
   return data[offset];
}

__attribute__ (( pure ))
inline static int8_t get_i8(const void * ptr, unsigned offset)
{
   const int8_t * data = (const int8_t *)ptr;
   return data[offset];
}

__attribute__ (( pure ))
inline static uint16_t get_u16(const void * ptr, unsigned offset)
{
   const uint8_t * data = (const uint8_t *)ptr;
   return (data[offset + 0] << 0)
        + (data[offset + 1] << 8);
}

__attribute__ (( pure ))
inline static uint32_t get_u32(const void * ptr, unsigned offset)
{
   const uint8_t * data = (const uint8_t *)ptr;
   return (data[offset + 0] <<  0)
        + (data[offset + 1] <<  8)
        + (data[offset + 2] << 16)
        + (data[offset + 3] << 24);
}
