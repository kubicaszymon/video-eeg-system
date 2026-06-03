
static
signed u2s_24bit(unsigned v)
{
   if (v < (1<<23))
      return v;
   else
      return v - (1<<24);
}
