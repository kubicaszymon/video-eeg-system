#include "PerunAmplifier.h"
#include "Utils.h"
#include "demo.h"
#include <algorithm>

#define INVALID_TIMSTAMP -1.0
int PerunAmpLogger::printf(const char *format, ...) {
	if (verbosity == 0 || !stdout_enable)
		return 0;
	char tmp[10000];
	va_list ap;
	va_start(ap, format);
	int res = vsnprintf(tmp, 10000, format, ap);
	va_end(ap);
	char * end = strrchr(tmp, '\n');
	if (skip_line || (verbosity < 3 && (strncmp(tmp, "M:", 2) == 0 || strncmp(tmp, "Rsp", 3) == 0))) {
		skip_line = end == 0;
		return 0;
	}

	if (end) {
		*end = 0;
		buffer << tmp;
		flush();
		buffer << end + 1;
	}
	else
		buffer << tmp;
	return res;
}
bool PerunAmplifier::write_data(const uint8_t * data, unsigned length, PerunAmpSample & sample) {
	//based on demo.h::write_data	
	enum { adc_ch_num = 8 };

	// number of bytes in one ADC sample
	enum { ts_size = 4 };
	enum { adc_data_size = (adc_ch_num + 1) * 3 };
	enum { adxl_data_size = 3 * 2 };


	// check data size
	if ((length % adc_data_size) != (ts_size + adxl_data_size))
		return false;

	unsigned samples = length / adc_data_size;
	if (samples == 0)
		return false;

	const uint8_t * _adc_data = &data[ts_size];

	// check first ADC word
	for (unsigned s = 0; s < samples; ++s) {
		if (_adc_data[adc_data_size * s + 0] != 0xc0)
			return false;
		if (_adc_data[adc_data_size * s + 1] != 0x00)
			return false;
		if (_adc_data[adc_data_size * s + 2] != 0x00)
			return false;
	}
	// write ADXL data
	const uint8_t * adxl_data = &data[ts_size + adc_data_size * samples];

	for (unsigned ch = 0; ch < 3; ++ch) {
		int16_t val =
			(adxl_data[2 * ch + 0] << 0) |
			(adxl_data[2 * ch + 1] << 8);
		sample.acc_data[ch] = val;
	}
	sample.head_time = *(const uint32_t *)data;
	// write ADC samples/channels
	for (unsigned s = 0; s < samples; ++s) {
		// skip first word		
		for (unsigned ch = 1; ch < adc_ch_num + 1; ++ch) {
			unsigned val =
				(_adc_data[adc_data_size * s + 3 * ch + 0] << 16) |
				(_adc_data[adc_data_size * s + 3 * ch + 1] << 8) |
				(_adc_data[adc_data_size * s + 3 * ch + 2] << 0);
			signed vs = u2s_24bit(val);
			sample.adc_data[ch - 1] = vs;
		}
		sample.sample_in_packet = s;
		sample.timestamp = calculate_timestamp(sample);
		sample_queue.push(sample);
	}
	return true;
}
uint64_t PerunAmplifier::get_rat_timer(uint32_t current_rat_timer) {
	if (current_rat_timer < last_rat_timer)
	{
		if (last_rat_timer > (0xFFFFFFFF - 500 * 1000 * 4)) // 500ms
			rat_period++;
		else if (last_rat_timer - current_rat_timer > 500 * 1000 * 4) {
			stringstream err_msg;
			err_msg << "ERROR: Amplifier was probably turned off. Unable to synchronize timestamps.\n"
				"last_rat_timer: " << last_rat_timer << ", current_rat_timer: " << current_rat_timer << "\n";
			throw invalid_argument(err_msg.str().c_str());
		}
	}
	last_rat_timer = current_rat_timer;
	uint64_t result = rat_period;
	result = ((result << 32) + current_rat_timer) / 4;
	return result;
}

void PerunAmplifier::synchronize_time(unsigned num)
{
	Msg m = *msg;
	Pkt pkt;
	rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_TIME_SYNC);
	rf_scanner(log, ftdi, m);
	rf_scanner(log, ftdi, m);
	vector<pair<int64_t, int64_t>> stats(num);
	clear_rat();
	sync_times_t last;
	vector<sync_times_t> msr(num);
	unsigned j = 0;
	for (unsigned i = 0; i < num; ++i) {
		sync_times_t measurements;
		if (!rf_time_sync(log, ftdi, m, cmd_rf_tsync, NULL, (i % 50 == 0), &measurements)) {
			log.printf("SYNC ERROR\n");
			continue;
		}
		measurements.head_rx = get_rat_timer(measurements.head_rx);
		auto head_tx = measurements.head_rx + measurements.head_tx_offset;
		uint64_t time_diff = -(measurements.head_rx - measurements.pc_tx - measurements.pc_rx + head_tx) / 2,
			duration = measurements.pc_rx - measurements.pc_tx;
		stats[j] = make_pair(duration, time_diff);
		msr[j] = measurements;
		j++;
	}
	/*for (int i = 0; i < msr.size();i++) {
		cout << "Duration:" << stats[i].first << " Time diff:" <<stats[i].second;
		if (i > 0)
			cout << " Trials PC diff: " << msr[i].pc_tx - msr[i-1].pc_tx << " Trials HEAD diff: " << msr[i].head_rx - msr[i-1].head_rx << "\n";
		else
			cout << "\n";
	}*/
	rf_time_sync(log, ftdi, m, cmd_rf_ts_end, NULL, false, NULL);
	clear_rat();
	sort(stats.begin(), stats.begin() + j);
	int64_t time_diff_sum = 0;
    unsigned results = j/4;
	for (unsigned i = 0; i < results; i++)
		time_diff_sum += stats[i].second;


	rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_TR_STAT);
	rf_scanner(log, ftdi, m);
	rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_HW_STAT);
	rf_scanner(log, ftdi, m);
	rf_scanner(log, ftdi, m);
	log.printf("Prev offset between clocks: %d\n", time_offset % 1000000);
	time_offset = time_diff_sum / results;
	log.printf("Time offset between clocks: %d, min %lld , max %lld\n", time_offset % 1000000, stats[0].first, stats[results-1].first);
}

bool PerunAmplifier::receive_packet() {
	// based on demo.h::rf_rx_data inner loop	
	Msg m = *msg;
	Pkt pkt;
	PerunAmpSample sample;
	if (!m.read_any(log, ftdi, pkt, &sample.pc_time)) {
		m.dump(log);
		dump_rx(log, ftdi, 0x200);
		return false;
	}

	if (!pkt.is_valid()) {
		return false;
	}
	sample.dongle_time = pkt.f_time();
	uint32_t time = sample.dongle_time;

	if (start_time == 0)
		start_time = time;
	time = time - start_time;

	uint32_t time_diff = (current_time == 0) ? 0 : (time - current_time);
	current_time = time;
	bool valid_data = pkt_stats.add(pkt, time_diff);
	uint8_t status = pkt.f_status();
	sample.rssi = pkt.f_rssi();
	if ((verbose) || ((packets_received % (sampling_rate / 4)) == 0))
		log.printf(
			"%3u: rx_len: %u, status: %02x, rssi: %d, dt: %.3fms, hdr: %02x, BLE len: %u\n",
			packets_received, pkt.f_len(), status, sample.rssi,
			time_diff * 1.0 / RF_TICKS_PER_1MS, pkt.f_ble_hdr(),
			pkt.f_ble_len());
	packets_received++;
	if (valid_data && write_data(pkt.f_ble_data(), pkt.f_ble_len(), sample))
		return true; // ADC format ok

	if (!valid_data)
		return false;
	//Wrong data
	log.printf("%02x %d:", status, sample.rssi);
	for (unsigned i = 0; i < pkt.f_ble_len(); ++i)
		log.printf(" %02x", pkt.f_ble_data()[i]);
	log.printf("\n");
	return false;
}

double PerunAmplifier::next_samples(bool synchronize) {
	if (!sample_queue.pop(current_sample, chrono::milliseconds(10000)) || current_sample.timestamp < 0) {
		stop_sampling();
		return INVALID_TIMSTAMP;
	}

	for (unsigned int i = 0; i < ADC_CHANNELS; ++i)
		past_adc_data[i].put(current_sample.adc_data[i]);
	sample_timestamp = current_sample.timestamp;
	cur_sample++;
	return sample_timestamp;
}
double PerunAmplifier::calculate_timestamp(PerunAmpSample & sample) {
	//if (last_synchronization_time == 0)
	//	last_synchronization_time = sample.pc_time;
	//if (sample.sample_in_packet == 0 && sample.pc_time > last_synchronization_time + 10) {
	//	sample_duration = (sample.pc_time - last_synchronization_time) / samples_since_synchronization;
	//	//time_offset += samples_since_synchronization * (sample_duration - 1.0 / sampling_rate) * US;
	//	samples_since_synchronization = 0;
	//	last_synchronization_time = sample.pc_time;
	//	std::cerr << "time_offset " << time_offset << " " << sample_duration << std::endl;
	//}
	//samples_since_synchronization++;
	double after_first_sample_in_packet_timestamp = ((double)((int64_t)get_rat_timer(sample.head_time) + time_offset)) / US;
	double sample_timestamp = after_first_sample_in_packet_timestamp;
	return sample_timestamp + sample.sample_in_packet*sample_duration;
}

void PerunAmplifier::init_radio() {
	//demo.h::demo
	ftdi.purge(FT_PURGE_RX);
	Msg m = *msg;

	// start communication with local HW
	{
		unsigned attempt = 0;
		while (1) {
			if (uart_tx_rx_test(log, ftdi, m, true))
				break; // OK
			++attempt;
			if (attempt > 5)
				return;
		}
	}

	// check local HW status
	if (uart_cmd(log, ftdi, m, cmd_hw_id, false))
		m.check_resp_hw_id(log);

	if (uart_cmd(log, ftdi, m, cmd_hw_stat, false))
		m.check_resp_hw_stat(log);

	// find remote device, check status
	rf_config_set(log, ftdi, m, cmd_rf_set_power, 12); // 0dB
	rf_config_set(log, ftdi, m, cmd_rf_set_timeout, 30); // 3 sec
	rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_HW_STAT);

	// wait for RF reception
	while (!rf_scanner(log, ftdi, m)) {
	}

	rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_SW_DATE);
	rf_scanner(log, ftdi, m);
	rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_TR_STAT);
	rf_scanner(log, ftdi, m);
	rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_DEBUG);
	rf_scanner(log, ftdi, m);
	rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_SET_POWER + 12); // 0dB
	rf_scanner(log, ftdi, m);
	rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_HW_STAT);
	rf_scanner(log, ftdi, m);
	//demo::demo::489

}
void PerunAmplifier::start_sampling() {
	//synchronize_time(100);
	//synchronize_time(100);
	//synchronize_time(100);
	//synchronize_time(100);
	synchronize_time(10);

	last_synchronization_time = 0;
	sample_duration = 1.0 / sampling_rate;
	samples_since_synchronization = 0;
	Msg m = *msg;
	// ADC data transfer
	rf_config_set(log, ftdi, m, cmd_rf_set_mode, 2);
	rf_config_set(log, ftdi, m, cmd_rf_set_timeout, 20); // 2 sec
	start_data_transfer();

	current_time = 0;
	start_time = 0;
	last_timestamp = 0;
	packets_received = 0;
	sample_queue.clear();
	Amplifier::start_sampling();
	sampling_thread = thread(&PerunAmplifier::receive_packets, this);
}
void PerunAmplifier::start_data_transfer() {
	//demo.h::demo::489	 
	Msg m = *msg;
	rf_rx_data_start(log, ftdi, m, measure_impedance ? SR_CMD_START : SR_CMD_START_PURE); // start
	pkt_stats.clear();
	//demo.h::demo::495	
}
#define SAMPLING_RESTART_THRESHOLD 0.2

void PerunAmplifier::receive_packets() {
	double first_invalid_packet_timestamp = 0;
	uint32_t invalid_packets = 0;
	try {
		while (sampling) {
			if (!receive_packet()) {
				invalid_packets++;
				double now = get_high_resolution_clock();
				if (first_invalid_packet_timestamp == 0)
					first_invalid_packet_timestamp = now;
				else if (now - first_invalid_packet_timestamp > SAMPLING_RESTART_THRESHOLD) {
					log.printf("WARNING: Restarting data transfer after %d invalid packets in %f ms!\n",
						invalid_packets, (now - first_invalid_packet_timestamp) * 1000);
					start_data_transfer();
					first_invalid_packet_timestamp = 0;
				}
			}
			else {
				if (invalid_packets > 4)
					log.printf("Warning: invalid packets: %d\n", invalid_packets);
				invalid_packets = 0;
				first_invalid_packet_timestamp = 0;
			}
		}
	}
	catch (const invalid_argument &e) {
		log.printf(e.what());
		PerunAmpSample sample;
		sample.timestamp = -1;
		sample_queue.push(sample);
	}
}
void PerunAmplifier::stop_sampling(bool disconnecting) {
	if (!sampling)
		return;
	sampling = false;
	if (sampling_thread.joinable())
		sampling_thread.join();
	//demo.h::demo::510
	Msg m = *msg;
	rf_rx_data_end(log, ftdi, m); // read status

	// check status after transfer
	if (uart_cmd(log, ftdi, m, cmd_hw_stat, false))
		m.check_resp_hw_stat(log);

	rf_config_set(log, ftdi, m, cmd_rf_set_timeout, 30); // 3 sec
	rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_HW_STAT);
	rf_scanner(log, ftdi, m);
	rf_scanner(log, ftdi, m);
	for (unsigned i = 0; i < 2; ++i) {
		bool res = true;
		rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_TR_STAT);
		res = rf_scanner(log, ftdi, m) && res;
		rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_SET_POWER + 5); // -6dB
		res = rf_scanner(log, ftdi, m) && res;
		rf_config_set(log, ftdi, m, cmd_rf_set_scan_cmd, SR_CMD_HW_STAT);
		res = rf_scanner(log, ftdi, m) && res;
		rf_config_set(log, ftdi, m, cmd_rf_set_power, 5); // -6dB 
		if (res)
			break;
	}
	log.printf("Current time_offset: %f\n", time_offset / 1000.0);
	synchronize_time(100);
	Amplifier::stop_sampling(disconnecting);
}
void PerunAmplifier::init(AmplifierOptions & options) {
	PerunAmplifierOptions default_options;
	PerunAmplifierOptions * perun_options =
		dynamic_cast<PerunAmplifierOptions *>(&options);
	if (!perun_options) {
		perun_options = &default_options;
	}
	int index = perun_options->device_index;

	log.printf("Initializing device: %d\n", index);
	if (!ftdi_open(log, ftdi, index, false)) {
		log.timestamp();
		log.flush();
		throw std::logic_error("Invalid FDTDI Device");
	}
	initialized = true;
	measure_impedance = perun_options->measure_impedance;
	if (!measure_impedance) {
		auto channels = description->get_channels();
		for (uint i = 0; i < ADC_CHANNELS; i++)
			channels[i]->impedance = ImpedanceFlag::unknown;
	}

	msg = new Msg();
	ftdi_config(log, ftdi, 3000000, false); // 3Mb/sec 

	if (!ftdi_uart(log, ftdi))
		throw std::logic_error("Could not initialize device");
	init_radio();
	Amplifier::init(options);
}
PerunAmplifier::PerunAmplifier() : Amplifier(), log(&logger), sample_queue(500 * 100),
past_adc_data(vector<Window<int32_t>>(ADC_CHANNELS, Window<int32_t>(500, 0)))
{
	log.printf("PerunAmplifier (compiled: " __DATE__ " " __TIME__ ") start ");
	log.timestamp();
	sampling_rate_ = 500;
	set_description(std::make_shared<PerunAmplifierDescription>(this));
}

PerunAmplifier::~PerunAmplifier() {
	if (initialized) {
		ftdi_close(log, ftdi);
		delete msg;
	}
	log.printf("end ");
	log.timestamp();
	log.printf("\n");
	log.flush();
}
uint PerunAmplifier::set_sampling_rate(uint sampling_rate) {
	auto sampling_rates = description->sampling_rates;
	if (find(sampling_rates.begin(), sampling_rates.end(), sampling_rate)
		!= sampling_rates.end())
		this->sampling_rate = sampling_rate;
	else
		cerr << "Sampling rate: " << sampling_rate << " not available\n";
	return this->sampling_rate;
}

template<typename T> string join(string prefix, T suffix) {
	stringstream s;
	s << prefix << suffix;
	return s.str();
}


//All filters work as intended only with Fs = 500 Hz, all line notches have bandwith = 5 Hz
static vector<double> un50b5_a = { 1.L, -1.568734520361621864736889619962L, 0.939062505817492398918489016069L };
static vector<double> un50b5_b = { 0.969531252908746199459244508034L, -1.568734520361621864736889619962L, 0.969531252908746199459244508034L };
static vector<double> un100b5_a = { 1.L, -0.599203267452875554255342649412L, 0.939062505817492398918489016069 };
static vector<double> un100b5_b = { 0.969531252908746199459244508034L, -0.599203267452875554255342649412L, 0.969531252908746199459244508034L };
static vector<double> un150b5_a = { 1.L, 0.599203267452875332210737724381L, 0.939062505817492398918489016069 };
static vector<double> un150b5_b = { 0.969531252908746199459244508034L, 0.599203267452875332210737724381L, 0.969531252908746199459244508034L };
static vector<double> un200b5_a = { 1.L, 1.568734520361621642692284694931L, 0.939062505817492398918489016069L };
static vector<double> un200b5_b = { 0.969531252908746199459244508034L, 1.568734520361621642692284694931L, 0.969531252908746199459244508034L };
static vector<double> iirp125q25_a = { 1.000000000000000000000000000000e+00L, -1.187333345548019104135238294009e-16L, 9.390625058174923989184890160686e-01L };
static vector<double> iirp125q25_b = { 0.030468747091253800540755491966L, 0., -0.030468747091253800540755491966L };


// iirnotch 125 q: 30 filter for Fs 500 (Marian)
static vector<double> eeg_notch_a = { 1.000000000000000000000000000000e+00L, -1.193396609139492917960121254899e-16L, 9.489645667148798313661473002867e-01L };
static vector<double> eeg_notch_b = { 9.744822833574399156830736501433e-01L, -1.193396609139492917960121254899e-16L, 9.744822833574399156830736501433e-01L };
EEGChannel::EEGChannel(PerunAmplifier * amplifier, int index, string name) :
	Channel(name, amplifier),
	filter(eeg_notch_a, eeg_notch_b),
	un50b5(un50b5_a, un50b5_b),
	un100b5(un100b5_a, un100b5_b),
	un150b5(un150b5_a, un150b5_b),
	un200b5(un200b5_a, un200b5_b),
	iirp125q25(iirp125q25_a, iirp125q25_b)
{
	this->index = index;
	this->gain = VOLTS_PER_BIT;
	this->exp = -6;
	this->impedance = ImpedanceFlag::present;
}


AccChannel::AccChannel(PerunAmplifier * amplifier, int index) :
	Channel(join("ACC_", "xyz"[index]), amplifier) {
	this->index = index;
	this->gain = 4;
	this->exp = -3;
	this->impedance = ImpedanceFlag::not_applicable;
}
DongleTimestampChannel::DongleTimestampChannel(PerunAmplifier * amplifier) :
	Channel("Dongle Timestamp", amplifier) {
	this->gain = 0.001 / RF_TICKS_PER_1MS;
	this->exp = 1;
	this->bit_length = 32;
	this->is_signed = false;
	this->impedance = ImpedanceFlag::not_applicable;
}
HeadTimestampChannel::HeadTimestampChannel(PerunAmplifier * amplifier) : Channel("Head Timestamp", amplifier) {
	this->gain = 0.001 / RF_TICKS_PER_1MS;
	this->exp = 1;
	this->bit_length = 32;
	this->is_signed = false;
	this->impedance = ImpedanceFlag::not_applicable;
}

PerunAmplifierDescription::PerunAmplifierDescription(PerunAmplifier * driver) :
	AmplifierDescription("Perun8", driver) {

	add_channel(make_shared<EEGChannel>(driver, 7, "P3"));
	add_channel(make_shared<EEGChannel>(driver, 4, "Cz"));
	add_channel(make_shared<EEGChannel>(driver, 2, "O2"));
	add_channel(make_shared<EEGChannel>(driver, 0, "P4"));
	add_channel(make_shared<EEGChannel>(driver, 6, "C3"));
	add_channel(make_shared<EEGChannel>(driver, 5, "O1"));
	add_channel(make_shared<EEGChannel>(driver, 3, "Pz"));
	add_channel(make_shared<EEGChannel>(driver, 1, "C4"));

	for (uint i = 0; i < 3; i++)
		add_channel(make_shared<AccChannel>(driver, i));
	add_channel(make_shared<RSSIChannel>(driver));
	add_channel(make_shared<DongleTimestampChannel>(driver));
	add_channel(make_shared<HeadTimestampChannel>(driver));
	add_channel(make_shared<PCTimestampChannel>(driver));
	add_channel(make_shared<SampleCounterChannel>(driver));
	sampling_rates.push_back(500);
}


#if defined(__linux__) || defined(__APPLE__)
#define GET_AVAILABLE "/tmp/getAvailablePerunAmplifiers.log"
#else
#define GET_AVAILABLE ((string(getenv("TEMP")) + "getAvailablePerunAmplifiers.log").c_str())
#endif

vector<string> PerunAmplifier::getAvailable() {
	vector<string> result;
	Logger log(GET_AVAILABLE);
	FTDI ftdi;
	uint index = 0;
	while (ftdi_open(log, ftdi, index, false)) {
		index++;
		result.push_back(join("Perun8 ", index));
		ftdi_close(log, ftdi);
	}
	log.flush();
	remove(GET_AVAILABLE);
	return result;
}

void PerunAmplifier::clear_rat() {
	last_rat_timer = 0;
	rat_period = 0;
}