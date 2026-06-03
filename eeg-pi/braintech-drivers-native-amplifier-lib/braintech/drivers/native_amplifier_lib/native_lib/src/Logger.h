/* Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
 * All rights reserved. */

#ifndef LOGGER_H
#define LOGGER_H

#include <chrono>
#include <string>

class Logger
{
public:
    typedef void (*LogCallback)(const char *, void * param);

    Logger(unsigned int p_sampling, const std::string & p_name);

    void set_callback(LogCallback callback_func, void * callback_param = nullptr);

    void restart();

    void next_sample();

    // log single line
    void log(const char * msg);
    void log(const std::string & msg);

    int sampling = 1;
    std::string name = "logger";

    // used only to debug C++ code, in Python always false
    static bool print_to_stderr;

private:
    int header(char * buffer, int buffer_size);

    LogCallback callback = nullptr;
    void * callback_param = nullptr;

    std::chrono::time_point<std::chrono::system_clock> start_time;
    std::chrono::time_point<std::chrono::system_clock> last_pack_time;

    unsigned int number_of_samples = 0;
};

#endif /* LOGGER_H */

