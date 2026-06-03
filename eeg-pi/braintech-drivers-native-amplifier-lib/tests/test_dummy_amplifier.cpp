
#include "amplifier_tester.h"
#include "DummyAmplifier.h"

std::unique_ptr<AmplifierOptions> get_options(po::variables_map &)
{
    std::unique_ptr<AmplifierOptions> options = std::make_unique<AmplifierOptions>();
    return options;
}

int main(int argc, char * argv[])
{
    DummyAmplifier amp;

    po::options_description dummy_amplifier_options("DummyAmplifier Options");

    return test_driver(argc, argv, amp, dummy_amplifier_options, get_options);
}

