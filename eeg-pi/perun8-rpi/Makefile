CXX = g++
CXXFLAGS = -O2 -std=c++14 -Wall
INCLUDES = -I./src -I./src/perun -I./src/perun/lib -I/usr/include/libftdi1
LIBS = -lftdi1 -lpthread

# Source files
BASE_SRC = src/Amplifier.cpp src/AmplifierDescription.cpp src/Logger.cpp src/Utils.cpp
PERUN_SRC = src/perun/PerunAmplifier.cpp

all: perun_reader

perun_reader: perun_reader.cpp $(BASE_SRC) $(PERUN_SRC)
	$(CXX) $(CXXFLAGS) $(INCLUDES) -o $@ $^ $(LIBS)

clean:
	rm -f perun_reader

.PHONY: all clean
