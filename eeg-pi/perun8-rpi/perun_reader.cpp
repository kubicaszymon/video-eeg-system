// Perun 8 EEG reader - outputs 8 EEG channel samples as CSV to stdout
// Sampling rate: 500 Hz (fixed by Perun 8 hardware)
// Output: ch0,ch1,...,ch7 (gain-adjusted values in uV)
#include "PerunAmplifier.h"
#include <stdio.h>
#include <signal.h>
#include <string.h>
#include <vector>
#include <string>

static volatile bool running = true;

void signal_handler(int sig) {
    running = false;
}

int main(int argc, char *argv[]) {
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);

    int device_index = 0;
    if (argc > 1)
        device_index = atoi(argv[1]);

    fprintf(stderr, "Perun8 reader: opening device %d...\n", device_index);

    PerunAmplifier amp;
    PerunAmplifierOptions opts;
    opts.device_index = device_index;
    opts.measure_impedance = false;
    opts.sampling_rate = 500;
    // Use default active_channels = "*" (all channels)

    try {
        amp.init(opts);
    } catch (const std::exception &e) {
        fprintf(stderr, "ERROR: Failed to init amplifier: %s\n", e.what());
        return 1;
    }

    // Set active channels to just the 8 EEG channels
    std::vector<std::string> eeg_channels = {"P3", "Cz", "O2", "P4", "C3", "O1", "Pz", "C4"};
    try {
        amp.set_active_channels(eeg_channels);
    } catch (const std::exception &e) {
        fprintf(stderr, "WARNING: Could not set EEG-only channels: %s. Using all.\n", e.what());
    }

    int num_ch = amp.get_active_channels_number();
    fprintf(stderr, "Perun8 reader: %d active channels, starting sampling at %d Hz...\n",
            num_ch, amp.get_sampling_rate());

    amp.start_sampling();

    // Print header
    printf("P3,Cz,O2,P4,C3,O1,Pz,C4\n");
    fflush(stdout);

    std::vector<double> samples(num_ch);
    while (running && amp.is_sampling()) {
        double ts = amp.next_samples();
        if (ts < 0) break;

        amp.fill_samples(samples, true);  // true = adjusted (gain+offset applied, values in uV)

        // Print first 8 channels (or all if fewer)
        int n = num_ch < 8 ? num_ch : 8;
        for (int i = 0; i < n; i++) {
            if (i > 0) putchar(',');
            printf("%.4f", samples[i]);
        }
        putchar('\n');
        fflush(stdout);
    }

    amp.stop_sampling();
    fprintf(stderr, "Perun8 reader: stopped.\n");
    return 0;
}
