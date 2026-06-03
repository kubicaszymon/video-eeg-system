# -*- coding: utf-8 -*-
# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.
#set( CMAKE_BUILD_TYPE Release )
set( CMAKE_BUILD_TYPE Debug )

set( BUILD_TESTS True )
set( BUILD_PYTHON_MODULE True )

set( CMAKE_VERBOSE_MAKEFILE True )
set( Boost_USE_STATIC_LIBS ON )
IF (WIN32)
set( Boost_DEBUG ON )
set( Boost_ADDITIONAL_VERSIONS "1.65.1")
set( Boost_COMPILER "-vc140")
ENDIF(WIN32)
##
## Usually you do not need to modify anything below this line
##
cmake_minimum_required( VERSION 3.5 )

project( amplifiers )

IF(NOT CMAKE_BUILD_TYPE)
  SET(CMAKE_BUILD_TYPE Debug CACHE STRING
      "Choose the type of build, options are: None Debug Release RelWithDebInfo MinSizeRel."
      FORCE)
ENDIF(NOT CMAKE_BUILD_TYPE)

## Use C++14
set( CMAKE_CXX_STANDARD 14 )

## C++ compiler options 
if (CMAKE_CXX_COMPILER_ID MATCHES "GNU")
	set( CMAKE_CXX_FLAGS "-Wall -Wextra" )
	set( CMAKE_CXX_FLAGS_DEBUG "-g3 -Og" )
	set( CMAKE_CXX_FLAGS_RELEASE "-g0 -O2" ) 
endif()

## Load CMAKE configuration from environment variables
set( CMAKE_MODULE_PATH $ENV{CMAKE_MODULE_PATH} ) 
set( CMAKE_PREFIX_PATH $ENV{CMAKE_PREFIX_PATH} ) 
set(CMAKE_MODULE_PATH ${CMAKE_MODULE_PATH} "${CMAKE_SOURCE_DIR}/cmake/")

## Sources and headers
include_directories( src src/dummy src/tmsi src/perun src/perun/lib)

## Find all source files to be compiled into object files
set( SRC_LOGGER src/Logger.cpp
                src/Logger.h )

set( SRC_AMPLIFIER_BASE src/Amplifier.cpp
                        src/Amplifier.h
                        src/AmplifierDescription.cpp
                        src/AmplifierDescription.h
                        src/Utils.h
                        ${SRC_LOGGER} )

set( SRC_AMPLIFIER_DUMMY src/dummy/DummyAmplifier.cpp
                         src/dummy/DummyAmplifier.h
                         ${SRC_AMPLIFIER_BASE} )

set( SRC_AMPLIFIER_TMSI src/tmsi/TmsiAmplifier.cpp
                        src/tmsi/TmsiAmplifier.h
                        src/tmsi/TmsiAmplifierDesc.cpp
                        src/tmsi/TmsiAmplifierDesc.h
                        src/tmsi/TmsiChannels.cpp
                        src/tmsi/TmsiChannels.h
                        src/tmsi/nexus.c
                        src/tmsi/nexus.h
                        ${SRC_AMPLIFIER_BASE} )

file(GLOB PERUNAMP_LIB "src/perun/lib/*.h")

set( SRC_AMPLIFIER_BAMP src/perun/PerunAmplifier.cpp
                        src/perun/PerunAmplifier.h
                        ${PERUNAMP_LIB}
                        ${SRC_AMPLIFIER_BASE} )



set( SRC_AMPLIFIER_TEST tests/amplifier_tester.cpp
                        tests/amplifier_tester.h )

find_package(FTDI REQUIRED)
if (WIN32)
	#set(LIBUSB_LIBRARY "${CMAKE_SOURCE_DIR}/win_libs/libusb-1.0.lib")
	set(FTDI_LIBRARY "${CMAKE_SOURCE_DIR}/win_libs/ftd2xx.lib")
	include_directories("${CMAKE_SOURCE_DIR}/win_libs")
endif()
set(FTDI_LIBRARIES ${FTDI_LIBRARY} ${LIBUSB_LIBRARY} )
if( BUILD_TESTS ) 

    find_package( Boost REQUIRED COMPONENTS program_options date_time )
    
	include_directories( "${Boost_INCLUDE_DIRS}" )
	link_directories(${Boost_LIBRARY_DIRS})
    set( TEST_LOGGER test_logger )
    set( TEST_DUMMY_AMPLIFIER test_dummy_amplifier )
    set( TEST_TMSI_AMPLIFIER test_tmsi_amplifier )
    set( TEST_PERUN_AMPLIFIER test_perun_amplifier )
    set( TEST_PERUN_DEMO test_perun_demo )

    add_executable( ${TEST_LOGGER} tests/test_logger.cpp ${SRC_LOGGER} )
    add_executable( ${TEST_DUMMY_AMPLIFIER} tests/test_dummy_amplifier.cpp ${SRC_AMPLIFIER_DUMMY} ${SRC_AMPLIFIER_TEST} )
    add_executable( ${TEST_TMSI_AMPLIFIER} tests/test_tmsi_amplifier.cpp ${SRC_AMPLIFIER_TMSI} ${SRC_AMPLIFIER_TEST} )
    add_executable( ${TEST_PERUN_AMPLIFIER} tests/test_perun_amplifier.cpp ${SRC_AMPLIFIER_BAMP} ${SRC_AMPLIFIER_TEST} )
    add_executable( ${TEST_PERUN_DEMO} tests/test_perun_demo.cpp ${PERUNAMP_LIB})

    # target_compile_definitions( ${TEST_TMSI_AMPLIFIER} PRIVATE AMP_DEBUG=1 BLUETOOTH=1 )
    target_compile_definitions( ${TEST_TMSI_AMPLIFIER} PRIVATE BLUETOOTH=1 )


    target_link_libraries( ${TEST_LOGGER} )
    target_link_libraries( ${TEST_DUMMY_AMPLIFIER} ${Boost_PROGRAM_OPTIONS_LIBRARY} ${Boost_DATE_TIME_LIBRARY} )
    target_link_libraries( ${TEST_TMSI_AMPLIFIER} ${Boost_PROGRAM_OPTIONS_LIBRARY} ${Boost_DATE_TIME_LIBRARY} -lbluetooth )
	if (WIN32)
	target_link_libraries(${TEST_TMSI_AMPLIFIER} "Ws2_32")
	endif()
    target_link_libraries( ${TEST_PERUN_AMPLIFIER} ${Boost_PROGRAM_OPTIONS_LIBRARY} ${Boost_DATE_TIME_LIBRARY} ${FTDI_LIBRARIES})
    target_link_libraries( ${TEST_PERUN_DEMO} ${FTDI_LIBRARIES})
endif()

## testing -- do not use
if( BUILD_PYTHON_MODULE )
    find_package(PythonInterp 3.5 REQUIRED )
    # ensure PythonLibs version match PythonInterp
    find_package(PythonLibs ${PYTHON_VERSION_STRING} REQUIRED )

	find_package(NumPy)

    # event if Python versions are the same ABIs still can be different
    # but we don't know how to test this, so just be careful

    include_directories("${PYTHON_INCLUDE_DIRS}" "${PYTHON_NUMPY_INCLUDE_DIR}") 
	
    set( PY_MODULE_NAME obci_cpp_amplifiers )

    add_library( ${PY_MODULE_NAME} MODULE
                 cython/_amplifiers.cpp                 
				 ${SRC_AMPLIFIER_DUMMY}
                 ${SRC_AMPLIFIER_TMSI}
				 ${SRC_AMPLIFIER_BAMP}				 
			 )
	
    target_link_libraries( ${PY_MODULE_NAME} ${PYTHON_LIBRARIES} ${FTDI_LIBRARIES})
	if (WIN32)
	    target_link_libraries( ${PY_MODULE_NAME} "Ws2_32")
	endif()
    set_target_properties( ${PY_MODULE_NAME} PROPERTIES INTERPROCEDURAL_OPTIMIZATION True )

    # see: https://www.python.org/dev/peps/pep-3149/
    # EXT_SUFFIX should be always defined
    # SHLIBS: not defined on Windows (on Ubuntu 16.04: '-lpthread -ldl  -lutil')
    # LDFLAGS: not defined on Windows (on Ubuntu 16.04: '-E -Wl,-Bsymbolic-functions -Wl,-z,relro')
    execute_process( COMMAND ${PYTHON_EXECUTABLE} -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX'))"
                     OUTPUT_VARIABLE MODULE_SUFFIX OUTPUT_STRIP_TRAILING_WHITESPACE)

    # proper .so or .pyd extension
    set_target_properties( ${PY_MODULE_NAME} PROPERTIES SUFFIX ${MODULE_SUFFIX} )	
    # no 'lib' prefix
    set_target_properties( ${PY_MODULE_NAME} PROPERTIES PREFIX "" )
endif()
