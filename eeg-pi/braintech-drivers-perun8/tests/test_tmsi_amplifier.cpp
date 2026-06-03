/*
 * File:   test_driver.cpp
 * Author: Macias
 *
 * Created on 2010-10-19, 16:06:44
 */

#include "TmsiAmplifier.h"
#include "amplifier_tester.h"

std::unique_ptr<AmplifierOptions> get_options(po::variables_map & vm)
{
    auto options = std::make_unique<TmsiAmplifierOptions>();
    fill_common_options(vm,options.get());
    if(vm.count("device-type"))
        options->device_type = vm["device-type"].as<int>();

    if(vm.count("device-url"))
        options->device_url = vm["device-url"].as<std::string>();

    if(vm.count("save-responses"))
        options->save_responses = vm["save-responses"].as<std::string>();

    return options;
}

int main(int argc, char * argv[])
{
    TmsiAmplifier amp;

    po::options_description tmsi_options("Tmsi Amplifier Options");

    tmsi_options.add_options()
    ("device-type,t", po::value<int>()->default_value(USB_AMPLIFIER), "Device type (USB - 1, FILE - 2, BLUETOOTH - 3)")
    ("device-url,u", po::value<std::string>()->default_value("/dev/tmsi0"), "Device path for usb connection")
    ("save-responses,o", po::value<std::string>(), "File to dump amplifier responses")
    ;

    return test_driver(argc, argv, amp, tmsi_options, get_options);
}
