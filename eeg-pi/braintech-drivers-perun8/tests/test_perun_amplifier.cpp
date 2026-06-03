#include <memory>
#include "amplifier_tester.h"
#include "PerunAmplifier.h"
#include <ftdi.h>


unique_ptr<AmplifierOptions> get_options(po::variables_map & vm) {
	unique_ptr<PerunAmplifierOptions> options = make_unique<
			PerunAmplifierOptions>();
	if (vm.count("device-type"))
		options->device_index = vm["device-index"].as<int>();
	fill_common_options(vm, (AmplifierOptions*) options.get());
	return options;

}

int main(int argc, char * argv[]) {		
	PerunAmplifier amplifier;

	po::options_description perun_amplifier_options(
			"PerunAmplifier Options");
	perun_amplifier_options.add_options()("device-index,i",
			po::value<int>()->default_value(0), "Which device to use");

	return test_driver(argc, argv, amplifier, perun_amplifier_options,
			get_options);
}

