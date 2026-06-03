/* Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
 * All rights reserved. */

#include <iostream>
#include <cstring>
#include <ctime>
#include "Logger.h"

namespace chrono = std::chrono;

bool Logger::print_to_stderr = false;

Logger::Logger(unsigned int p_sampling,
               const std::string & p_name)
    : sampling(p_sampling)
    , name(p_name)
{
    restart();
}

void Logger::set_callback(LogCallback callback_func, void * callback_param_)
{
    callback = callback_func;
    callback_param = callback_param_;
}

void Logger::restart()
{
    start_time = chrono::system_clock::now();
    last_pack_time = start_time;
    number_of_samples = 0;
}

void Logger::next_sample()
{
    if(++number_of_samples % sampling == 0)
    {
        const int buffer_size = 200;
        char buffer[buffer_size];

        chrono::time_point<chrono::system_clock> now = chrono::system_clock::now();

        chrono::duration<double, std::micro> t1 = now - last_pack_time;
        chrono::duration<double, std::micro> t2 = now - start_time;

        snprintf(buffer, buffer_size,
                 "Time of last %d samples / all avg:%f / %f",
                 sampling,
                 t1.count() / 1000000.,
                 (double(sampling) * t2.count()) / 1000000. / double(number_of_samples));

        log(buffer);
        last_pack_time = now;
    }
}

void Logger::log(const std::string & msg)
{
    log(msg.c_str());
}

void Logger::log(const char * msg)
{
    const int buffer_size = 1000;
    char buffer[buffer_size];
    if(callback)
    	callback(msg, callback_param);
    if (print_to_stderr){
		// write log header, return number of written bytes
		const int len = header(buffer, buffer_size);

		snprintf(buffer + len, buffer_size - len, " INFO - %s", msg);

		buffer[buffer_size - 1] = '\0';
		std::cerr << buffer << std::endl;
    }
}

int Logger::header(char * buffer, const int buffer_size)
{
    if(buffer_size <= 0)
        return 0;

    const auto now = chrono::system_clock::now();

    const time_t tnow = chrono::system_clock::to_time_t(now);

    std::tm * date = std::localtime(&tnow); // std::tm has resolution of seconds

    const int milliseconds =
        chrono::duration_cast<chrono::milliseconds>(
            now - chrono::system_clock::from_time_t(std::mktime(date))
        ).count();

    // total number of characters copied to buffer (not including the terminating null-character)
    const int len_1 = strftime(buffer, buffer_size, "%Y-%m-%d %H:%M:%S", date);

    if(len_1 == 0)
    {
        buffer[0] = '\0';
        return 0;
    }

    snprintf(buffer + len_1, buffer_size - len_1, ",%.3d - %s - ", milliseconds, name.c_str());

    buffer[buffer_size - 1] = '\0';

    return std::strlen(buffer);
}

