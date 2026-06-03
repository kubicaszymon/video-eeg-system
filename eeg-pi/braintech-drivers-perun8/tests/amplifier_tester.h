
#include <boost/program_options.hpp>
#include "Amplifier.h"

namespace po = boost::program_options;

typedef std::unique_ptr<AmplifierOptions> (*GetOptionsFunc)(po::variables_map & vm);

void fill_common_options(po::variables_map & vm,AmplifierOptions * options);

int test_driver(int argc, char * argv[],
                Amplifier & amplifier,
                po::options_description & extra_options,
                GetOptionsFunc get_options);

