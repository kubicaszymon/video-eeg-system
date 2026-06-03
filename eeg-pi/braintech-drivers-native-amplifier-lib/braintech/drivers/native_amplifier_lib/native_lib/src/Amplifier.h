/* Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
 * All rights reserved. */

#ifndef AMPLIFIERDRIVER_H
#define AMPLIFIERDRIVER_H

#include <vector>
#include <string>
#include <memory>
#include <tuple>

#include "AmplifierDescription.h"
#include "Logger.h"
#include "Utils.h"

std::vector<std::string> split_string(const std::string & str, char separator);

struct AmplifierOptions
{
    virtual ~AmplifierOptions() {}

    // Sampling rate to use
    int sampling_rate = 128;

    // String with channel names or indexes separated by semicolons
    std::string active_channels = "*";
};

class Amplifier
{
private:
    double sleep_res;
    double get_time_res;

    double get_sleep_resolution();

protected:
    bool sampling = false;

    uint sampling_rate;
    uint sampling_rate_;

    std::string active_channels_str;
    std::vector<std::shared_ptr<Channel>> active_channels;
    uint active_channels_with_impedance;

    double last_sample;
    double sample_timestamp;
    double sampling_start_time;

    std::shared_ptr<AmplifierDescription> description;
    virtual double get_expected_sample_time();

public:
    Amplifier();
    virtual ~Amplifier();

    virtual void init(AmplifierOptions & options);

    void set_log_callback(Logger::LogCallback callback_func, void * callback_param);

    virtual void start_sampling();
    virtual void stop_sampling(bool disconnecting = false);

    std::string get_description_json();

    void set_active_channels(const std::vector<std::string> & channels);
    void set_active_channels_string(const std::string & channels);

    inline bool is_sampling()
    {
        return sampling;
    }

    virtual uint set_sampling_rate(const uint samp_rate);

    inline void set_sampling_rate_(const uint samp_rate)
    {
        if(!description)
        {
            sampling_rate_ = samp_rate;
            return;
        }
        set_sampling_rate(samp_rate);
        logger.log("Current Sampling rate:" + std::to_string(get_sampling_rate()) + "\n");
    }

    inline int get_sampling_rate()
    {
        return sampling_rate;
    }

    inline int get_active_channels_number()
    {
        return active_channels.size();
    }

    inline int get_active_channels_with_impedance_number()
    {
        return active_channels_with_impedance;
    }

    inline std::string get_active_channels_string()
    {
        std::ostringstream out;
        for(uint i = 0; i < active_channels.size(); i++)
            out << (i ? ";" : "") << active_channels[i]->name;
        return out.str();
    }

    virtual double next_samples(bool synchronize = true);

    inline double get_sample_timestamp()
    {
        return sample_timestamp;
    }

    // sampling
    std::tuple<std::vector<double>, std::vector<double>> get_samples();
    std::tuple<std::vector<std::vector<double>>, std::vector<std::vector<double>>> get_samples_vec(unsigned int samples_per_vector);

    bool get_samples_to_buf(double * buf, double & tsbuf, double * impbuf, unsigned int buf_max_elements);
    int get_samples_vec_to_buf(double * buf,
                               double * tsbuf,
                               double * impbuf,
                               int buf_max_elements,
                               int number_of_sample_vectors);
	static inline double local_clock()
	{
		return get_high_resolution_clock();
	}
public:
    Logger logger;

    unsigned int cur_sample;

    void set_description(std::shared_ptr<AmplifierDescription> description);

    inline std::shared_ptr<AmplifierDescription> get_description()
    {
        return description;
    }

    template <class T>
    inline int fill_samples(std::vector<T> & samples, bool adjusted = false)
    {
        if(!sampling)
            return -1;

        if(!adjusted)
            for(uint i = 0; i < active_channels.size(); i++)
                samples[i] = active_channels[i]->get_sample();
        else
            for(uint i = 0; i < active_channels.size(); i++)
                samples[i] = active_channels[i]->get_adjusted_sample();

        return active_channels.size();
    }

    inline const std::vector<std::shared_ptr<Channel>> & get_active_channels()
    {
        return active_channels;
    }
};

#endif  /* AMPLIFIERDRIVER_H */
