/*
 * File:   test_driver.cpp
 * Author: Macias
 *
 * Created on 2010-10-19, 16:06:44
 */

#include <cstdlib>
#define __STDC_LIMIT_MACROS
#include <cstdint>
#include <iostream>

/*
 * Simple C++ Test Suite
 */
#include <boost/date_time/posix_time/posix_time.hpp>
#include <boost/bind.hpp>

#include "amplifier_tester.h"
void fill_common_options(po::variables_map & vm,AmplifierOptions * options){
	if (vm.count("active_channels"))
		options->active_channels = vm["active_channels"].as<std::string>();
	if (vm.count("sampling_rate"))
		options->sampling_rate = vm["sampling_rate"].as<int>();
}
int _test_driver(int argc, char * argv[],
                 Amplifier & amp,
                 po::options_description & extra_options,
                 GetOptionsFunc get_options)
{
    Logger::print_to_stderr = true;

    int length;
    int saw;
    double time_diff;

    std::shared_ptr<Channel> ampSaw;
    std::shared_ptr<Channel> sampleCounter ;

    po::options_description options("Program Options");
    options.add_options()
    ("length,l", po::value<int>(&length)->default_value(5), "Length of the test in seconds")
    ("help,h", "Show help")
    ("start", "Start sampling")
    ("saw", po::value<int>(&saw)->default_value(0), "Set expected Saw difference. If set driver will monitor samples lost")
    ("time", po::value<double>(&time_diff)->default_value(0.0), "Monitor time difference. Display error, when difference between expected timestamps is bigger then give value")
    ;

    po::options_description common_amplifier_options("Common Amplifier Options");
    common_amplifier_options.add_options()
    ("sampling_rate,s", po::value<int>()->default_value(amp.get_sampling_rate()),
     "Sampling rate to use")
    ("active_channels,c", po::value<std::string>()->default_value("*"),
     "String with channel names or indexes separated by semicolons")
    ;

    options.add(common_amplifier_options);
    options.add(extra_options);

    po::variables_map vm;
    po::store(po::parse_command_line(argc, argv, options), vm);
    po::notify(vm);

    auto amp_options = get_options(vm);

    if(vm.count("help"))
    {
        std::cout << options;
        return 0;
    }
    else
    {
        std::cout << "Use --help for available options" << std::endl;
    }

    amp.init(*amp_options.get());

    std::cout << amp.get_description()->get_json() << "\n";

    int sample_rate = amp.get_sampling_rate();

    ampSaw = amp.get_description()->find_channel("Saw");
    sampleCounter = amp.get_description()->find_channel("Sample_Counter");

    auto channels = amp.get_active_channels();

    int last_saw = -1;

    if(!vm.count("start"))
        return 0;

    if(saw && (!ampSaw || !sampleCounter))
    {
        std::cerr << "Driver has no 'Saw' or 'Sample_Counter' channel which are required for 'saw' option";
        return -1;
    }

    amp.start_sampling();

    const auto start = boost::posix_time::microsec_clock::local_time();
    double start_time = 0;

    printf("SAMPLING STARTED at %s  and will stop after %d (%d)samples\n",
           to_simple_string(start).c_str(), length * sample_rate, length);

    std::cout.precision(3);

    uint lost_samples = 0;
    int i = 0;
    double last_sample_time = amp.get_sample_timestamp();
    double stop_time = get_time_as_double();
    int saw_jump = 1 << 31;

    while(i < length * sample_rate)
    {
        if(!amp.is_sampling())
        {
            stop_time = get_time_as_double();
            break;
        }

        const double cur_sample = amp.next_samples();
        if (start_time == 0)
        	start_time = amp.get_sample_timestamp();


        if(channels.size() > 0)
        {
            printf("[%15s] S %d, timestamp: %.20f\n",
                   boost::posix_time::to_simple_string(boost::posix_time::microsec_clock::local_time()).substr(12).c_str(),
                   i, cur_sample);
            for(uint j = 0; j < channels.size(); j++)
                printf("%12s: %f %x\n", channels[j]->name.c_str(),
                       channels[j]->get_sample(),
                       channels[j]->get_raw_sample());
        }

        if(saw)
        {
            int new_saw = ampSaw->get_raw_sample();

            if(last_saw != -1 && new_saw < last_saw && saw_jump == 1 << 31)
            {
                while((saw_jump >> 1) > last_saw)
                    saw_jump = saw_jump >> 1;

                printf(
                    "[%15s] S %d: Saw Jump set to: %d. Saw  %d ->%d\n",
                    boost::posix_time::to_simple_string(boost::posix_time::microsec_clock::local_time()).substr(12).c_str(),
                    sampleCounter ->get_raw_sample(), saw_jump, last_saw, new_saw);
            }

            if(last_saw >= 0 && (last_saw + saw) % saw_jump != new_saw)
            {
                int lost;

                if(new_saw < last_saw)
                    lost = (saw_jump - last_saw + new_saw) / saw - 1;
                else
                    lost = (new_saw - last_saw) / saw - 1;

                printf(
                    "[%15s] S %d: ERROR!!! At least %d Samples lost. Saw %d->%d (jump %d)\n",
                    to_simple_string(boost::posix_time::microsec_clock::local_time()).substr(12).c_str(),
                    sampleCounter ->get_raw_sample(), lost, last_saw, new_saw, saw_jump);

                lost_samples += lost;
            }
            last_saw = new_saw;
        }

        if(time_diff > 0)
        {
            const double expected_sample = last_sample_time + 1.0 / amp.get_sampling_rate();

            if(abs(expected_sample - cur_sample) > time_diff)
            {
                printf("[%15s] S %d: ERROR!!! Has different timestamp than expected: (exp: %.4f,got: %.4f,diff: %.4f)\n",
                       to_simple_string(boost::posix_time::microsec_clock::local_time()).substr(12).c_str(),
                       i,
                       expected_sample - start_time,
                       cur_sample - start_time,
                       cur_sample - expected_sample);
            }
        }

        last_sample_time = cur_sample;
        stop_time = get_time_as_double();
        i++;
    }

    boost::posix_time::ptime end = boost::posix_time::microsec_clock::local_time();

    printf("Sampling will be stopped at %s after %d samples\n", to_simple_string(end).c_str(), i);
    printf("Duration: %s\n", to_simple_string(end - start).c_str());
    printf("First TS: %f,last TS: %f, computed_frequency: %f\n", start_time, last_sample_time, i / (last_sample_time - start_time));
    printf("Actual frequency: %f\n", i / (stop_time - start_time));
    printf("Lost samples: %d\n", lost_samples);

    amp.stop_sampling();

    return 0;
}

int test_driver(int argc, char * argv[],
                Amplifier & amplifier,
                po::options_description & extra_options,
                GetOptionsFunc get_options)
{
    try
    {
        _test_driver(argc, argv, amplifier, extra_options, get_options);
        return 0;
    }
    catch(char const * msg)
    {
        std::cerr << "Amplifier exception: " << msg << "\n";
    }
    catch(std::exception & ex)
    {
        std::cerr << "Amplifier exception: " << ex.what() << "\n";
    }
    catch(...)
    {
        std::cerr << "Amplifier exception: <unknown>\n";
    }
    return -1;
}

