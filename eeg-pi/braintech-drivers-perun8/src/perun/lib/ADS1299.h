// TI ADS1299
// Low-Noise, 8-Channel, 24-Bit Analog-to-Digital Converter
// http://www.ti.com/product/ADS1299

#ifndef HW_ADS1299_H
#define HW_ADS1299_H

// ADS1299 SPI commands
enum {
   ADS_WAKEUP  = 0x02,
   ADS_STANDBY = 0x04,
   ADS_RESET   = 0x06,
   ADS_START   = 0x08,
   ADS_STOP    = 0x0A,
   ADS_RDATAC  = 0x10,
   ADS_SDATAC  = 0x11,
   ADS_RDATA   = 0x12,
   ADS_RREG    = 0x20,
   ADS_WREG    = 0x40,
};

// ADS1299 registers
enum {
   ADS_REG_ID         = 0x00,
   ADS_REG_CONFIG1    = 0x01,
   ADS_REG_CONFIG2    = 0x02,
   ADS_REG_CONFIG3    = 0x03,
   ADS_REG_LOFF       = 0x04,
   ADS_REG_CH1SET     = 0x05,
   ADS_REG_CH2SET     = 0x06,
   ADS_REG_CH3SET     = 0x07,
   ADS_REG_CH4SET     = 0x08,
   ADS_REG_CH5SET     = 0x09,
   ADS_REG_CH6SET     = 0x0A,
   ADS_REG_CH7SET     = 0x0B,
   ADS_REG_CH8SET     = 0x0C,
   ADS_REG_BIAS_SENSP = 0x0D,
   ADS_REG_BIAS_SENSN = 0x0E,
   ADS_REG_LOFF_SENSP = 0x0F,
   ADS_REG_LOFF_SENSN = 0x10,
   ADS_REG_LOFF_FLIP  = 0x11,
   ADS_REG_LOFF_STATP = 0x12,
   ADS_REG_LOFF_STATN = 0x13,
   ADS_REG_GPIO       = 0x14,
   ADS_REG_MISC1      = 0x15,
   ADS_REG_MISC2      = 0x16,
   ADS_REG_CONFIG4    = 0x17,

   ADS_LAST_REG       = ADS_REG_CONFIG4,
   ADS_REG_NUM        = ADS_LAST_REG+1 //number of registers
};

enum {
   // number of ADC channels
   ADS_CH_NUM = 8,
   // data size returned by RDATA or RDATAC cmd
   // ctr word (3 bytes) + ADS_CH_NUM of 24 bit words
   ADS_DATA_SIZE = 3 + ADS_CH_NUM*3,

   // ADS_REG_ID
   ADS_ID_1299 = 0x1E, // ID reg value, ADS1299
   ADS_ID_MASK = 0x1F, // ID reg mask (ignore REV_ID)

   // ADS_REG_CONFIG1
   ADS_CONFIG1_FIXED = 0x90, // fixed fields in ADS_REG_CONFIG1
   ADS_DR_16  = 0<<0, // 16kSPS
   ADS_DR_8   = 1<<0,
   ADS_DR_4   = 2<<0,
   ADS_DR_2   = 3<<0,
   ADS_DR_1   = 4<<0, // 1kSPS
   ADS_DR_05  = 5<<0, // 500SPS
   ADS_DR_025 = 6<<0, // 250SPS

   // ADS_REG_CONFIG2
   ADS_CONFIG2_FIXED = 0xC0, // fixed fields in ADS_REG_CONFIG2
   ADS_INT_TEST    = 1<<4, // Test signals are generated internally
   ADS_TEST_AMP    = 1<<2, // Test signal amplitude
   ADS_TEST_FREQ_0 = 0<<0, // Pulsed at fCLK / (1<<21)
   ADS_TEST_FREQ_1 = 1<<0, // Pulsed at fCLK / (1<<20)
   ADS_TEST_FREQ_3 = 3<<0, // At dc

   // ADS_REG_CONFIG3
   ADS_CONFIG3_FIXED  = 0x60, // fixed fields in ADS_REG_CONFIG3
   ADS_PDB_REFBUF     = 1<<7, // _not_ Power-down reference buffer
   ADS_BIAS_MEAS      = 1<<4, // BIAS measurement
   ADS_BIASREF_INT    = 1<<3, // BIASREF connected to (AVDD + AVSS) / 2
   ADS_PDB_BIAS       = 1<<2, // _not_ BIAS buffer power down
   ADS_BIAS_LOFF_SENS = 1<<1, // BIAS sense function
   ADS_BIAS_STAT      = 1<<0, // BIAS lead-off status

   // ADS_REG_LOFF
   ADS_ILOFF_6N      = 0<<2, // Lead-off current: 6nA
   ADS_ILOFF_24N     = 1<<2, // Lead-off current: 6nA
   ADS_ILOFF_6U      = 2<<2, // Lead-off current: 6nA
   ADS_ILOFF_24U     = 3<<2, // Lead-off current: 6nA
   ADS_FLOFF_DC      = 0<<0, // Lead-off freq: DC
   ADS_FLOFF_7       = 1<<0, // Lead-off freq: 7.8Hz
   ADS_FLOFF_31      = 2<<0, // Lead-off freq: 31Hz
   ADS_FLOFF_F4      = 3<<0, // Lead-off freq: fDR/4

   // ADS_REG_CHxSET
   ADS_CH_PD   = 1<<7, // channel Power-down
   ADS_GAIN_1  = 0<<4, // channel gain
   ADS_GAIN_2  = 1<<4,
   ADS_GAIN_4  = 2<<4,
   ADS_GAIN_6  = 3<<4,
   ADS_GAIN_8  = 4<<4,
   ADS_GAIN_12 = 5<<4,
   ADS_GAIN_24 = 6<<4,
   ADS_SRB2    = 1<<3, // SRB2 connection
   ADS_MUX_INPUT    = 0<<0, // Normal input
   ADS_MUX_SHORT    = 1<<0, // Input shorted
   ADS_MUX_BIAS     = 2<<0, // BIAS measurements
   ADS_MUX_MVDD     = 3<<0, // MVDD for supply measurement
   ADS_MUX_TEMP     = 4<<0, // Temperature sensor
   ADS_MUX_TEST     = 5<<0, // Test signal
   ADS_MUX_BIAS_DRP = 6<<0, // BIAS_DRP (positive electrode is the driver)
   ADS_MUX_BIAS_DRN = 7<<0, // BIAS_DRN (negative electrode is the driver)

   // ADS_REG_MISC1
   ADS_SRB1    = 1<<5, // SRB1 connection (all inverting inputs)
};

#endif // HW_ADS1299_H
