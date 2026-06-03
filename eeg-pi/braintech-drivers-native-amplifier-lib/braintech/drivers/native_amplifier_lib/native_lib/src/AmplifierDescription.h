/* Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
 * All rights reserved. */

#ifndef AMPLIFIERDESCRIPTION_H_
#define AMPLIFIERDESCRIPTION_H_
#define _USE_MATH_DEFINES
#include <cmath>
#include <vector>
#include <string>
#include <memory>
#include <iostream>
#include <sstream>
#include <stdio.h>
#ifndef __linux__
typedef uint32_t uint;
#endif // !__linux__


#ifndef __linux__
typedef unsigned int uint;
#endif // !__linux__


enum ImpedanceFlag {
	unknown = 0,
	not_applicable = 1,
	present = 2
};

class Channel;
class Amplifier;

class AmplifierDescription
{
private:
    std::vector<std::shared_ptr<Channel>> channels;    
    std::vector<std::shared_ptr<Channel>> generated_channels;

protected:
    uint physical_channels;	
    Amplifier * driver;
    std::string name;

public:
    std::vector<uint> sampling_rates;

    AmplifierDescription(const std::string & name, Amplifier *);

    virtual ~AmplifierDescription();

    virtual std::vector<uint> get_sampling_rates();

    virtual std::string get_name();

    virtual std::string get_json();

    std::vector<std::shared_ptr<Channel>> get_channels();    

    void add_channel(std::shared_ptr<Channel> channel);

    void add_generated_channel(std::shared_ptr<Channel> channel)
    {
        generated_channels.push_back(channel);
    }

    void clear_channels();

    virtual std::shared_ptr<Channel> generated_channel(uint index)
    {
        if(index < generated_channels.size())
            return generated_channels[index];
        return nullptr;
    }

    virtual std::shared_ptr<Channel> find_channel(const std::string & channel);

    uint get_physical_channels()
    {
        return physical_channels;
    }

    inline Amplifier * get_driver()
    {
        return driver;
    }
};

class DummyAmpDesc: public AmplifierDescription
{
public:
    DummyAmpDesc(Amplifier * driver);
};

class Channel
{
protected:
    Amplifier * amplifier = nullptr;

public:
    std::string name;
    std::vector<double> other_params;

    double gain;
    double offset;
    ImpedanceFlag impedance;

    bool is_signed;
    short bit_length;
    short exp; // Unit exponent, 3 for Kilo, -6 for micro, etc.

public:
    Channel(const std::string & name, Amplifier * amp);

    virtual ~Channel()
    {
    }

    virtual std::string get_type()
    {
        return "UNKNOWN";
    }

    virtual std::string get_unit()
    {
        return "Unknown";
    }

    virtual std::string get_idle();

    virtual std::string get_json();

    virtual std::string get_filters_json() {
        return "[]";
    }

    virtual inline int get_raw_sample()
    {
        return rand() % 100;
    }

    virtual inline double get_sample()
    {
        return get_raw_sample();
    }

    virtual float get_impedance();

    virtual inline double get_adjusted_sample()
    {
        return get_raw_sample() * gain + offset;
    }

    virtual inline bool is_generated()
    {
        return false;
    }

    virtual inline bool has_impedance()
    {
        return impedance == ImpedanceFlag::present;
    }
};

class GeneratedChannel: public Channel
{
public:
    GeneratedChannel(const std::string & name, Amplifier * amp)
        : Channel(name, amp)
    {
        is_signed = 0;
        impedance = ImpedanceFlag::not_applicable;
    }

    inline bool is_generated()
    {
        return true;
    }
};

class RandomBoolChannel: public GeneratedChannel
{
public:
    RandomBoolChannel(const std::string & name, Amplifier * amp)
        : GeneratedChannel(name, amp)
    {
        bit_length = 1;
    }

    inline int get_raw_sample()
    {
        return rand() % 2;
    }

    virtual std::string get_type()
    {
        return "Boolean";
    }

    virtual std::string get_unit()
    {
        return "Bit";
    }
};

class SampleCounterChannel: public GeneratedChannel
{
public:
    SampleCounterChannel(Amplifier * amp, const std::string & name = "Sample_Counter")
        : GeneratedChannel(name, amp)
    {
        bit_length = 32;
    }

    int get_raw_sample();

    virtual std::string get_unit()
    {
        return "Integer";
    }

    virtual std::string get_type()
    {
        return "ZAAG";
    }
};

class SawChannel: public GeneratedChannel
{
private:
    unsigned int counter;

public:
    SawChannel(Amplifier * amp, const std::string & name = "Saw")
        : GeneratedChannel(name, amp)
    {
        bit_length = 32;
        counter = 0;
    }

    inline int get_raw_sample()
    {
        const unsigned int current_counter_value = counter;
        counter++;
        if(counter > 100)
            counter = 0;
        return current_counter_value;
    }

    virtual std::string get_unit()
    {
        return "Integer";
    }

    virtual std::string get_type()
    {
        return "ZAAG";
    }
};

class FunctionChannel: public GeneratedChannel
{
private:
    unsigned int amplitude;
    unsigned int exp;

public:
    FunctionChannel(Amplifier * amp,
                    unsigned int period,
                    const std::string & name = "Random");

    std::string get_unit()
    {
        char tmp[100];
        snprintf(tmp, 100, "Volt %d", exp);
        return tmp;
    }

    int get_raw_sample();

    double get_adjusted_sample();

protected:
    unsigned int period;

    virtual double get_value()
    {
        return (rand() % period) / float(period);
    }
};

class SinusChannel: public FunctionChannel
{
public:
    SinusChannel(Amplifier * amp, unsigned int period)
        : FunctionChannel(amp, period, "Sinus")
    {
    }

protected:
    virtual double get_value();
};

class CosinusChannel: public FunctionChannel
{
public:
    CosinusChannel(Amplifier * amp, unsigned int period)
        : FunctionChannel(amp, period, "Cosinus")
    {
    }

protected:
    virtual double get_value();
};

class ModuloChannel: public FunctionChannel
{
public:
    ModuloChannel(Amplifier * amp, unsigned int period)
        : FunctionChannel(amp, period, "Modulo")
    {
    }

protected:
    virtual double get_value();
};

class NoSuchChannel: public std::exception
{
    std::string name;

public:
    NoSuchChannel(const std::string & ch_name) throw()
    {
        name = "No such channel or channel index not in range: " + ch_name;
    }

    virtual const char * what() const throw()
    {
        return name.c_str();
    }

    virtual ~NoSuchChannel() throw();
};

class NoImpedanceForChannel: public std::exception
{
    std::string name;

public:
    NoImpedanceForChannel(const std::string & ch_name) throw()
    {
        name = "No impedance for channel or impedance unknown: " + ch_name;
    }

    virtual const char * what() const throw()
    {
        return name.c_str();
    }

    virtual ~NoImpedanceForChannel() throw();
};

#endif /* AMPLIFIERDESCRIPTION_H_ */
