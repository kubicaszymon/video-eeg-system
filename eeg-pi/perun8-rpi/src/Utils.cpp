#include <chrono>
#include <thread>
#include <iostream>

#ifdef _WIN32
#include <windows.h>
#define TICKS_PER_SECOND 10000000
#define EPOCH_DIFFERENCE 116444736000000000LL //in hundreds of nanoseconds
#endif


extern "C" {
#ifndef __linux__
	void usleep(uint32_t usec) {
		std::this_thread::sleep_for(std::chrono::microseconds(usec));
	}
#endif // !__linux__
	void nanosleep_ns(uint64_t nsec) {
		std::this_thread::sleep_for(std::chrono::nanoseconds(nsec));
	}


#ifdef __linux__
    double get_high_resolution_clock() {
    using namespace std::chrono;
    auto now = time_point_cast<nanoseconds>(high_resolution_clock::now());
    return now.time_since_epoch().count() / 1000000000.0;
	}
#endif

#ifdef __APPLE__
#include <time.h>
   double get_high_resolution_clock() {
    return clock_gettime_nsec_np(CLOCK_REALTIME) / 1000000000.0;
	}
#endif


#ifdef _WIN32

    double get_high_resolution_clock() {
        FILETIME time_now;
        GetSystemTimePreciseAsFileTime(&time_now);
        ULONGLONG windows_epoch;
        windows_epoch = (((ULONGLONG) time_now.dwHighDateTime) << 32) + time_now.dwLowDateTime;
        double unix_epoch = double(windows_epoch - EPOCH_DIFFERENCE);

        return unix_epoch / TICKS_PER_SECOND;
	}
#endif

} //extern C - has to engulf all functions or they get compiled as C++ and will not be linked