#ifndef _PERUNAMPLIFIER_H_
#define _PERUNAMPLIFIER_H_

#include <queue>
#include <deque>
#include <array>
#include <math.h>
#include <string.h>
#include <thread>
#include "Amplifier.h"
#include "SynchronizedQueue.hpp"
typedef Logger AmplifierLogger;

using namespace std;

#define Logger PerunampLogger
#include "lib/Logger.h"

#if defined(__linux__) || defined(__APPLE__)
#include "FTDI_linux.h"
#define LOG_FILE "/tmp/Perun.log"
#else
#include "FTDI_win.h"
#define LOG_FILE ((string(getenv("TEMP")) + "Perun.log").c_str())
#endif


#define ADC_CHANNELS 8
template<typename T> class Window : public deque<T> {
public:
    Window(unsigned size, double val) {
        for (unsigned int i = 0; i < size; ++i) this->push_back(val);
    }
    T put(T x) {
        this->push_front(x);
        this->pop_back();
        return x;
    }
};
class Msg;
class PerunAmplifierOptions: public AmplifierOptions{
public:
    // Perun Amplifier supports sampling rate of 500 only
    int sampling_rate = 500;	
	uint8_t device_index=0;
	bool measure_impedance = true;
};
class PerunAmplifier;
class PerunAmpLogger: public Logger{
	ostringstream buffer;
	bool skip_line = false;
public:
	uint verbosity = 2;
	AmplifierLogger * logger;
	PerunAmpLogger(AmplifierLogger *logger):Logger(LOG_FILE),buffer(""){
		this->logger = logger;
	}
	virtual int printf(const char *format, ...);
	void flush(){
		logger->log(buffer.str());
		buffer.str("");
		buffer.clear();
	}
};
class PerunAmpSample {
public:
	array<int32_t, ADC_CHANNELS> adc_data;
	int16_t acc_data[3];
	int8_t rssi;
	int8_t sample_in_packet;
	uint32_t dongle_time;
	uint32_t head_time;
	double pc_time;
	double timestamp;	
};
class PerunAmplifier: public Amplifier
{
	friend class RSSIChannel;
	friend class EEGChannel;
	friend class AccChannel;
	friend class DongleTimestampChannel;
	friend class HeadTimestampChannel;
	friend class PCTimestampChannel;
private:
	PerunAmpLogger log;
	FTDI ftdi;
	Msg * msg;
	void init_radio();
	void start_data_transfer();
	//void time_sync();
	bool receive_packet();
	void receive_packets();
	PerunAmpSample current_sample;
	SynchronizedQueue<PerunAmpSample> sample_queue;
    vector<Window<int32_t>> past_adc_data;		
	double last_timestamp;
	double sample_duration;
	double last_synchronization_time;
	uint32_t samples_since_synchronization;		
	bool verbose = false;
	uint32_t current_time = 0;
	uint32_t start_time = 0;
	uint32_t rat_period = 0;
	uint32_t last_rat_timer = 0;	
	uint32_t packets_received = 0;
	bool write_data(const uint8_t * data, unsigned length, PerunAmpSample &);
	uint64_t get_rat_timer(uint32_t current_rat_timer);
	bool initialized = false;
	int64_t time_offset;
	void synchronize_time(unsigned num=500);
	double calculate_timestamp(PerunAmpSample &);
	thread sampling_thread;
	void clear_rat();
	

public:
    PerunAmplifier();
    double next_samples(bool synchronize = true);
    void init(AmplifierOptions & options);
    void start_sampling();
    void stop_sampling(bool disconnecting = false);
    virtual ~PerunAmplifier();
    static vector<string> getAvailable();
    uint set_sampling_rate(uint sampling_rate);
	bool  measure_impedance = true;
};

class RMSWindow {
    const unsigned window_size = 8;
    Window<double> squares = Window<double>(window_size, 1);
    double sum = window_size;
public:
    double get(double x) {
        double square = x * x;
        sum += square;
        sum -= squares.back();
        squares.put(square);
        return sqrt(sum / window_size * 2);
    }
};

template<typename T> string get_vec_json(const vector<T> &v) {
    stringstream out;
    out.precision(std::numeric_limits<T>::digits10 + 2);  // https://stackoverflow.com/questions/554063/how-do-i-print-a-double-value-with-full-precision-using-cout
    out << '[';
    for(uint i = 0; i < v.size(); i++) out << (i ? "," : "") << fixed << v[i];
    out << ']';
    return out.str();
}

class IIRFilter {
    const vector<double> a; // past filter output coefficients
    const vector<double> b; // filter input coefficients
public:
    Window<double> y; // filter output history
    IIRFilter(vector<double> a, vector<double> b) : a(a), b(b), y(Window<double>(b.size(), 1)){}
    template<typename NUM> double get(deque<NUM> &x) {
        double out = 0;
        for (unsigned int i = 0; i < b.size(); ++i) out += x[i] * b[i];
        for (unsigned int i = 1; i < a.size(); ++i) out -= y[i-1] * a[i];
        return y.put(out / a[0]);
    }
    string get_json() {
        stringstream out;
        out <<  "{\"a\":" << get_vec_json(a) << ",\"b\":" << get_vec_json(b) << '}';
        return out.str();
    }
};

class EEGChannel : public Channel {
private:
	int index;
    IIRFilter filter;
    IIRFilter un50b5, un100b5, un150b5, un200b5, // universal notch X hz, bandwidth Y
        iirp125q25; //iirpeak 125 q: 25
    RMSWindow amplitude;
    static constexpr int MAX_VOLTAGE = 8350000;
    static constexpr  float VOLTS_PER_BIT = 0.04466f; //In uV
    static constexpr  float IMPEDANCE_CURRENT = 6; //nA
    static constexpr  float BIT_TO_KOHM = (VOLTS_PER_BIT / IMPEDANCE_CURRENT); // (V^-6)/(A^-9)=Ohm^3
public:
	EEGChannel(PerunAmplifier * amplifier, int index, string name);

	int get_raw_sample(){
        return filter.get(((PerunAmplifier *)amplifier)->past_adc_data[index]);
	}

	float get_impedance()
	{
        // cascade of filters + amplitude/rms; https://redmine.titanis.pl/issues/38448
        auto signal_history = (((PerunAmplifier*)amplifier)->past_adc_data[index]);
        un50b5.get(signal_history);
        un100b5.get(un50b5.y);
        un150b5.get(un100b5.y);
        un200b5.get(un150b5.y);
        double impedance_voltage = amplitude.get(iirp125q25.get(un200b5.y));
        // if electrode is disconnected ADC returns flat signal at level higher than MAX_VOLTAGE
        // no 125 Hz signal is observed, so calculated impedance would return 0
        // here we force maximum "measurable" impedance
        return float((signal_history.front() > MAX_VOLTAGE) ? MAX_VOLTAGE : impedance_voltage) * BIT_TO_KOHM; // basic unit is kOhm
	}

	string get_type() {
		return "EXG EEG";
	}
	string get_unit() {
		return "Volt";
	}
    string get_filters_json() {
        stringstream out;
        out << '[' << filter.get_json() << ']';
        return out.str();
    }
};


class AccChannel : public Channel {
private:
	int index;
public:
	AccChannel(PerunAmplifier * amplifier, int index);
	int get_raw_sample(){
		return ((PerunAmplifier *)amplifier)->current_sample.acc_data[index];
	}
	string get_type() {
			return "ACC";
		}
	string get_unit() {
		return "g";
	}
};
class RSSIChannel : public Channel {

public:
	RSSIChannel(PerunAmplifier * amplifier):Channel("RSSI",amplifier){
		this->gain = 1;
		this->exp = 1;
		this->bit_length = 8;
		this->is_signed = true;
    	this->impedance = ImpedanceFlag::not_applicable;
	}
	int get_raw_sample(){
		return ((PerunAmplifier *)amplifier)->current_sample.rssi;
	}
	string get_type() {
		return "RSSI";
	}
	string get_unit() {
		return "dB";
	}
};
class DongleTimestampChannel : public Channel {
public:
	DongleTimestampChannel(PerunAmplifier * amplifier);
	int get_raw_sample(){
		return ((PerunAmplifier *)amplifier)->current_sample.dongle_time;
	}
	string get_type() {
		return "Integer";
	}
	string get_unit() {
		return "Second";
	}
};
class HeadTimestampChannel : public Channel {
public:
	HeadTimestampChannel(PerunAmplifier *amplifier);
	int get_raw_sample() {
		return ((PerunAmplifier *)amplifier)->current_sample.head_time;
	}
	string get_type() {
		return "Integer";
	}
	string get_unit() {
		return "Second";
	}
};
class PCTimestampChannel : public Channel {
public:
	PCTimestampChannel(PerunAmplifier *amplifier) :Channel("PC Timestamp", amplifier) {
		gain = 1;
		exp = 1;
		bit_length = 64;
	}
	double get_sample() {
		return ((PerunAmplifier *)amplifier)->current_sample.pc_time;
	}
	int get_raw_sample() {
		return ((PerunAmplifier *)amplifier)->current_sample.pc_time;
	}
	string get_type() {
		return "Integer";
	}
	string get_unit() {
		return "Second";
	}
};

class PerunAmplifierDescription : public AmplifierDescription
{
public:
	PerunAmplifierDescription(PerunAmplifier * driver);
};

#endif
