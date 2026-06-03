/* Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
 * All rights reserved. */

#ifndef CPP_AMPS_UTILS_H
    #define CPP_AMPS_UTILS_H
    #include <stdint.h>

    #ifdef  __cplusplus
        extern "C" {
    #endif //  __cplusplus__

    #ifdef _WIN32
        void usleep(uint32_t usec);
    #endif // !__linux__

    void nanosleep_ns(uint64_t nsec);
    double get_high_resolution_clock();

    #ifdef  __cplusplus
        }
    #endif
#endif  /* CPP_AMPS_UTILS_H */
