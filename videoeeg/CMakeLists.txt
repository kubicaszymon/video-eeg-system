cmake_minimum_required(VERSION 3.21)

# ---------------------------------------------------------------------------
# vcpkg toolchain. Must be set BEFORE project() so vcpkg can configure the
# triplet and register its install paths.
#
# We *prefer* a standalone clone at C:/vcpkg over Visual Studio's bundled
# vcpkg (the latter is a frozen snapshot whose ports baseline may be older
# than vcpkg.json's `builtin-baseline`; this would cause "baseline not found"
# errors). Override via -DCMAKE_TOOLCHAIN_FILE=... if you want a different one.
# ---------------------------------------------------------------------------
if(NOT DEFINED CMAKE_TOOLCHAIN_FILE)
    if(EXISTS "C:/vcpkg/scripts/buildsystems/vcpkg.cmake")
        set(CMAKE_TOOLCHAIN_FILE "C:/vcpkg/scripts/buildsystems/vcpkg.cmake"
            CACHE STRING "vcpkg toolchain file (standalone)")
    elseif(DEFINED ENV{VCPKG_ROOT})
        set(CMAKE_TOOLCHAIN_FILE "$ENV{VCPKG_ROOT}/scripts/buildsystems/vcpkg.cmake"
            CACHE STRING "vcpkg toolchain file (from VCPKG_ROOT)")
    endif()
    if(DEFINED CMAKE_TOOLCHAIN_FILE)
        message(STATUS "Using vcpkg toolchain: ${CMAKE_TOOLCHAIN_FILE}")
    endif()
endif()

project(veeg_app
    VERSION 0.1.0
    DESCRIPTION "NeuroSync VEEG - research video-EEG monitoring prototype"
    LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC OFF)

set(CMAKE_INCLUDE_CURRENT_DIR ON)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

find_package(Qt6 6.5 REQUIRED COMPONENTS Core Gui Widgets Network)

# ---------------------------------------------------------------------------
# vcpkg-provided third-party libraries.
#   - liblsl  : LSL C++ headers + LSL::lsl target  (EEG / video streams)
#   - FFmpeg  : avcodec (H.264 decode) + swscale (YUV->BGR) for video
#
# liblsl uses normal find_package(CONFIG). For FFmpeg we deliberately bypass
# find_package(FFMPEG) because Qt6 ships its own FindFFMPEG.cmake which gets
# picked up before vcpkg's wrapper and demands libavformat -- which we don't
# need (H.264 NAL units arrive over LSL as raw bytes, not via a container).
# Use pkg-config directly against the .pc files vcpkg installs alongside
# avcodec / avutil / swscale; clean and minimal.
# ---------------------------------------------------------------------------
find_package(LSL CONFIG REQUIRED)

find_package(PkgConfig REQUIRED)
pkg_check_modules(LIBAV REQUIRED IMPORTED_TARGET
    libavcodec
    libavutil
    libswscale
)

qt_standard_project_setup()

# ---------------------------------------------------------------------------
# Source files — organised in subdirectories:
#   core/    : plain data model, formatting helpers (no Qt UI)
#   theme/   : colour tokens, fonts, global stylesheet
#   ui/      : reusable widgets (canvases, button/label helpers)
#   screens/ : top-level screens (welcome, monitor view with sidebar/topbar)
#   dialogs/ : modal overlays, filters popover, save toast
#   control/ : Pi remote-control HTTP client + poller + dock widgets
#   lsl/     : LSL stream receivers (EEG samples, H.264 video) -- background
#              QThreads that pull samples and feed the canvases
#   src/     : application entry point + MainWindow controller
# ---------------------------------------------------------------------------
set(VEEG_SOURCES
    src/main.cpp
    src/mainwindow.cpp
    src/theme/theme.cpp
    src/ui/uihelpers.cpp
    src/ui/canvases.cpp
    src/ui/videodock.cpp
    src/screens/welcomescreen.cpp
    src/screens/monitorview.cpp
    src/dialogs/overlays.cpp
    src/control/picontrolclient.cpp
    src/control/picontrolpoller.cpp
    src/control/eegcontroldock.cpp
    src/control/videocontroldock.cpp
    src/lsl/lsleegreceiver.cpp
    src/lsl/lslvideoreceiver.cpp
    src/lsl/sessionrecorder.cpp
)

set(VEEG_HEADERS
    src/mainwindow.h
    src/core/appmodel.h
    src/core/format.h
    src/theme/theme.h
    src/ui/uihelpers.h
    src/ui/canvases.h
    src/ui/videodock.h
    src/screens/welcomescreen.h
    src/screens/monitorview.h
    src/dialogs/overlays.h
    src/control/picontrolclient.h
    src/control/picontrolpoller.h
    src/control/eegcontroldock.h
    src/control/videocontroldock.h
    src/lsl/lsleegreceiver.h
    src/lsl/lslvideoreceiver.h
)

qt_add_executable(veeg_app WIN32 ${VEEG_SOURCES} ${VEEG_HEADERS})

# All subdirectories are on the include path so every #include "foo.h"
# resolves without changing any existing include directive.
target_include_directories(veeg_app PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${CMAKE_CURRENT_SOURCE_DIR}/src/core
    ${CMAKE_CURRENT_SOURCE_DIR}/src/theme
    ${CMAKE_CURRENT_SOURCE_DIR}/src/ui
    ${CMAKE_CURRENT_SOURCE_DIR}/src/screens
    ${CMAKE_CURRENT_SOURCE_DIR}/src/dialogs
    ${CMAKE_CURRENT_SOURCE_DIR}/src/control
    ${CMAKE_CURRENT_SOURCE_DIR}/src/lsl
)

target_link_libraries(veeg_app PRIVATE
    Qt6::Core Qt6::Gui Qt6::Widgets Qt6::Network
    LSL::lsl
    PkgConfig::LIBAV
)

target_compile_options(veeg_app PRIVATE
    $<$<CXX_COMPILER_ID:GNU>:-Wall;-Wextra;-Wpedantic>
    $<$<CXX_COMPILER_ID:Clang>:-Wall;-Wextra;-Wpedantic>
    $<$<CXX_COMPILER_ID:MSVC>:/W4;/permissive->
)

set_target_properties(veeg_app PROPERTIES
    WIN32_EXECUTABLE TRUE
    OUTPUT_NAME "NeuroSyncVEEG"
)
