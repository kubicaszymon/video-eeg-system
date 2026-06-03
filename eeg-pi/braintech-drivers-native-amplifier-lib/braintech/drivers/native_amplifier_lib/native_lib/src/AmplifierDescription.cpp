/* Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
 * All rights reserved. */

#include "AmplifierDescription.h"
#include "Amplifier.h"



void AmplifierDescription::clear_channels()
{
    channels.clear();
}

void AmplifierDescription::add_channel(std::shared_ptr<Channel> channel)
{
    channels.push_back(channel);
    if(channel->is_generated())
        add_generated_channel(channel);
    else
        physical_channels++;
}

std::vector<std::shared_ptr<Channel>> AmplifierDescription::get_channels()
{
    return channels;
}


AmplifierDescription::~AmplifierDescription()
{
    clear_channels();
}

AmplifierDescription::AmplifierDescription(const std::string & name,
                                           Amplifier * driver)
    : physical_channels(0)
    , driver(driver)
    , name(name)
{
}

std::vector<uint> AmplifierDescription::get_sampling_rates()
{
    return sampling_rates;
}

std::string AmplifierDescription::get_name()
{
    return name;
}

std::string AmplifierDescription::get_json()
{
    std::stringstream out;

    out << "{\t\"name\":\"" << get_name() << "\",\n";
    out << "\t\"physical_channels\": " << get_physical_channels() << ",\n";
    out << "\t\"sampling_rates\":[";
    for(uint i = 0; i < sampling_rates.size(); i++)
    {
        if(i)
            out << ',';
        out << sampling_rates[i];
    }
    out << "],\n\t\"channels\": [";
    for(uint i = 0; i < channels.size(); i++)
        out << (i ? ",\n\t\t" : "\t\t") << channels[i]->get_json();
    out << "]}";

    return out.str();
}

std::shared_ptr<Channel> AmplifierDescription::find_channel(const std::string & channel)
{
    std::istringstream stream(channel);
    int tmp;

    if(!((stream >> tmp).fail()))
    {
        if(tmp < 0)
            return generated_channel(-tmp);
        else if((uint) tmp < channels.size())
            return channels[tmp];
    }

    for(uint j = 0; j < channels.size(); j++)
        if(channels[j]->name == channel)
            return channels[j];

    return nullptr;
}

NoSuchChannel::~NoSuchChannel() throw()
{
}

NoImpedanceForChannel::~NoImpedanceForChannel() throw()
{
}

std::string Channel::get_json()
{
    std::ostringstream out;
    out.setf(std::ios::scientific, std::ios::floatfield);
    out.precision(std::numeric_limits<double>::digits10 + 1);
    out << "{"
        << "\"name\":\"" << name << "\","
        << "\"gain\":" << gain << ","
        << "\"filters\":" << get_filters_json() << ","
        << "\"offset\":" << offset << ","
        << "\"impedance\":" << impedance << ","
        << "\"idle\":" << get_idle() << ","
        << "\"type\":\"" << get_type() << "\","
        << "\"unit\": \"" << get_unit() << "\","
        << "\"other_params\": [";
    for(size_t i = 0; i < other_params.size(); i++)
        out << (i ? "," : "") << other_params[i];
    out << "]}";
    return out.str();
}

Channel::Channel(const std::string & name, Amplifier * amp)
    : amplifier(amp)
    , name(name)
    , gain(1.0)
    , offset(0)
    , impedance(ImpedanceFlag::unknown)
    , is_signed(true)
    , bit_length(32)
{
}

std::string Channel::get_idle()
{
    std::ostringstream out;
    if(is_signed)
        out << (int)(-1 << (bit_length - 1));
    else
        out << (uint)(1 << (bit_length - 1));
    return out.str();
}

float Channel::get_impedance()
{
    if(impedance == ImpedanceFlag::present)
        return get_raw_sample();
    else
        throw NoImpedanceForChannel(name);
}

int SampleCounterChannel::get_raw_sample()
{
    return amplifier->cur_sample;
}

double SinusChannel::get_value()
{
    return std::sin((amplifier->cur_sample % period) * 2 * M_PI / period);
}

double CosinusChannel::get_value()
{
    return std::cos((amplifier->cur_sample % period) * 2 * M_PI / period);
}

double ModuloChannel::get_value()
{
    return (amplifier->cur_sample % period) / double(period);
}

FunctionChannel::FunctionChannel(Amplifier * amp,
                                 uint period,
                                 const std::string & function_name)
    : GeneratedChannel(function_name, amp)
{
    this->period = period;
    amplitude =  30.0;

    char tmp[100];
    snprintf(tmp, 100, "[%d]%dVolt-6", period, amplitude);

    name += tmp;

    //uint max = 1 << (30);
    gain = 1e-6;
    offset = amplitude / 2;

}

int FunctionChannel::get_raw_sample()
{
    return (get_adjusted_sample() - offset) / gain;
    //printf("(%d * %f + %f) * %f + %f = %f  <=>  %f * %d = %f \n",temp,gain,offset,a,b,(temp*gain+offset)*a+b,get_value(),amplitude,get_value()*amplitude);
}

double FunctionChannel::get_adjusted_sample()
{
    return get_value() * amplitude;
}

DummyAmpDesc::DummyAmpDesc(Amplifier * driver)
    : AmplifierDescription("Dummy Amplifier", driver)
{
    add_channel(std::make_shared<SinusChannel>(driver, 128));
    add_channel(std::make_shared<CosinusChannel>(driver, 128));
    add_channel(std::make_shared<ModuloChannel>(driver, 128));
    add_channel(std::make_shared<FunctionChannel>(driver, 128));

    add_channel(std::make_shared<SinusChannel>(driver, 256));
    add_channel(std::make_shared<CosinusChannel>(driver, 256));
    add_channel(std::make_shared<ModuloChannel>(driver, 256));
    add_channel(std::make_shared<FunctionChannel>(driver, 256));

    add_channel(std::make_shared<SinusChannel>(driver, 512));
    add_channel(std::make_shared<CosinusChannel>(driver, 512));
    add_channel(std::make_shared<ModuloChannel>(driver, 512));
    add_channel(std::make_shared<FunctionChannel>(driver, 512));

    add_channel(std::make_shared<SinusChannel>(driver, 1024));
    add_channel(std::make_shared<CosinusChannel>(driver, 1024));
    add_channel(std::make_shared<ModuloChannel>(driver, 1024));
    add_channel(std::make_shared<FunctionChannel>(driver, 1024));

    add_channel(std::make_shared<SinusChannel>(driver, 2048));
    add_channel(std::make_shared<CosinusChannel>(driver, 2048));
    add_channel(std::make_shared<ModuloChannel>(driver, 2048));
    add_channel(std::make_shared<FunctionChannel>(driver, 2048));

    add_channel(std::make_shared<SinusChannel>(driver, 4096));
    add_channel(std::make_shared<CosinusChannel>(driver, 4096));
    add_channel(std::make_shared<ModuloChannel>(driver, 4096));
    add_channel(std::make_shared<FunctionChannel>(driver, 4096));

    add_channel(std::make_shared<RandomBoolChannel>("Random_Bool", driver));

    add_channel(std::make_shared<SawChannel>(driver));
    add_channel(std::make_shared<SampleCounterChannel>(driver));

    sampling_rates.push_back(128);
    sampling_rates.push_back(256);
    sampling_rates.push_back(512);
    sampling_rates.push_back(1024);
    sampling_rates.push_back(2048);
}
