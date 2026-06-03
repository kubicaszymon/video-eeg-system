/* Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
 * All rights reserved. */
#include <cmath>

#include "Amplifier.h"


std::vector<std::string> split_string(const std::string & str, char separator)
{
    uint i = 0;
    std::vector<std::string> res;

    while(true)
    {
        size_t j = str.find(separator, i);
        if(j == std::string::npos)
            break;
        res.push_back(str.substr(i, j - i));
        i = j + 1;
    }

    if(str.size() - i > 0)
        res.push_back(str.substr(i));

    return res;
}

void Amplifier::init(AmplifierOptions & options)
{
    set_sampling_rate_(options.sampling_rate);
    set_active_channels_string(options.active_channels);
}

void Amplifier::set_log_callback(Logger::LogCallback callback_func, void * callback_param)
{
    logger.set_callback(callback_func, callback_param);
}

void Amplifier::start_sampling()
{
    sampling = true;
    cur_sample = 0;

    logger.sampling = sampling_rate;

    logger.log(" Sampling started with sampling rate "
               + std::to_string(sampling_rate)
               + "\nActive Channels: "
               + get_active_channels_string()
               + "\n");
    double start = local_clock();

    get_time_res = (local_clock() - start) * 2;
    logger.log("Sleep resolution: "
               + std::to_string(sleep_res)
               + " local_clock resolution: "
               + std::to_string(get_time_res)
               + "\n");
    sampling_start_time = last_sample = sample_timestamp = local_clock();
}

double Amplifier::get_expected_sample_time()
{
    return sampling_start_time + cur_sample / (double)sampling_rate;
}

double Amplifier::next_samples(bool synchronize)
{
    cur_sample++;

    double expected = get_expected_sample_time();

    sample_timestamp = last_sample = local_clock();

    if(!synchronize)
        return sample_timestamp;

    double diff, seconds;

    diff = expected - last_sample;

    if(diff > sleep_res)
    {

        diff -= sleep_res;
		nanosleep_ns(diff * 1000000000);
        last_sample = local_clock();
    }

    while(last_sample + get_time_res < expected)
        last_sample = local_clock();
    sample_timestamp = expected;
    return sample_timestamp;
}

void Amplifier::set_active_channels(const std::vector<std::string> & channels)
{
    active_channels.clear();
    active_channels_with_impedance=0;

    if(!description)
        return;

    for(uint i = 0; i < channels.size(); i++)
    {
        if(channels[i] == "*")
		{
            active_channels = description->get_channels();            
			break;
		}
        std::shared_ptr<Channel> chan = description->find_channel(channels[i]);

        if(!chan)
            throw NoSuchChannel(channels[i]);
        else        
            active_channels.push_back(chan);		
    }
	for (const auto & ch : active_channels)
		if (ch->has_impedance())
			active_channels_with_impedance++;
}

void Amplifier::set_active_channels_string(const std::string & channels)
{
    if(!description)
    {
        active_channels_str = channels;
        return;
    }
    else if(get_active_channels_string() == channels)
    {
        return;
    }

    std::vector<std::string> names;
    uint i = 0;
    while(true)
    {
        uint64_t j = channels.find(';', i);
        if(j == std::string::npos)
            break;
        names.push_back(channels.substr(i, j - i));
        i = j + 1;
    }

    names.push_back(channels.substr(i));
    set_active_channels(names);

    logger.log("Active channels: " + get_active_channels_string() + "\n");
}

double Amplifier::get_sleep_resolution()
{
    double start = local_clock();    
    nanosleep_ns(1);
    return local_clock() - start;
}

Amplifier::Amplifier()
    : logger(128, "AmplifierDriver")
{
    description = nullptr;
    sampling_rate = sampling_rate_ = 128;
    cur_sample = 0;
    sample_timestamp = 0;
    sleep_res = get_sleep_resolution();
}

void Amplifier::set_description(std::shared_ptr<AmplifierDescription> new_description)
{
    description = new_description;
    set_sampling_rate(sampling_rate_);
    set_active_channels_string(active_channels_str);
}

Amplifier::~Amplifier()
{
}

void Amplifier::stop_sampling(bool disconnecting)
{
    sampling = false;

    logger.log("Sampling stopped" + std::string(disconnecting ? " and disconnecting" : "") + "\n");
}

uint Amplifier::set_sampling_rate(const uint samp_rate)
{
    return sampling_rate = samp_rate;
}

std::string Amplifier::get_description_json()
{
    if(!description)
        return std::string();

    return description->get_json();
}

std::tuple<std::vector<double>, std::vector<double>> Amplifier::get_samples()
{
	next_samples();    
    //logger.next_sample();

    std::vector<double> samples;
    samples.reserve(active_channels.size());

    std::vector<double> impedances;
    impedances.reserve(active_channels_with_impedance);

    for(const auto & ch : active_channels)
	{
        samples.push_back(ch->get_sample());
		if (ch->has_impedance())
			impedances.push_back(ch->get_impedance());
	}

    return std::make_tuple(samples, impedances);
}

std::tuple<std::vector<std::vector<double>>, std::vector<std::vector<double>>>
Amplifier::get_samples_vec(unsigned int samples_per_vector)
{
    std::vector<std::vector<double>> samples_vec;
    std::vector<std::vector<double>> impedances_vec;
    samples_vec.reserve(samples_per_vector);
    impedances_vec.reserve(samples_per_vector);

    for(unsigned int i = 0; i < samples_per_vector; i++)
    {
        if(!is_sampling())
        {
            break;
        }
        auto samples_with_impedances = get_samples();
        samples_vec.push_back(std::get<0>(samples_with_impedances));
        impedances_vec.push_back(std::get<1>(samples_with_impedances));
    }

    return std::make_tuple(samples_vec, impedances_vec);
}

bool Amplifier::get_samples_to_buf(double * buf, double & tsbuf, double * impbuf, unsigned int buf_max_elements)
{
	if (next_samples() < 0)
		return false;
    //logger.next_sample();

    if(active_channels.size() > buf_max_elements)
        return false;
	uint imp_index = 0;
    for(unsigned int i = 0; i < active_channels.size(); i++)
	{
		const auto ch = active_channels[i];
        buf[i] = ch->get_sample();
		if (ch->has_impedance())
			impbuf[imp_index++] = ch->get_impedance();
	}
    
    tsbuf = get_sample_timestamp();

    return true;
}

int Amplifier::get_samples_vec_to_buf(double * buf,
                                      double * tsbuf,
                                      double * impbuf,
                                      int buf_max_elements,
                                      int number_of_sample_vectors)
{
    int i = 0;
    for(; i < number_of_sample_vectors; i++)
    {
        if(!is_sampling())
            break;

        if(!get_samples_to_buf(
            buf + (i * buf_max_elements),
            *(tsbuf + i),
            impbuf + (i * active_channels_with_impedance),
            buf_max_elements)
          )
            break;
    }

    return i;
}
