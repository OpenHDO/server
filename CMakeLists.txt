cmake_minimum_required(VERSION 3.24)

project(openhdo VERSION 0.1.0 LANGUAGES CXX)

include(GNUInstallDirs)
include(CTest)

option(OPENHDO_BUILD_TESTS "Build OpenHDO tests" ${BUILD_TESTING})
option(OPENHDO_WARNINGS_AS_ERRORS "Treat compiler warnings as errors" OFF)

set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/generated/openhdo")
configure_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/cmake/config.hpp.in"
    "${CMAKE_CURRENT_BINARY_DIR}/generated/openhdo/config.hpp"
    @ONLY
)

add_library(openhdo_core STATIC
    src/core/configuration.cpp
    src/core/control_plane.cpp
    src/core/domain.cpp
    src/core/logging.cpp
    src/core/messaging.cpp
    src/core/registry.cpp
    src/core/runtime.cpp
)

target_compile_features(openhdo_core PUBLIC cxx_std_20)
target_include_directories(openhdo_core
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<BUILD_INTERFACE:${CMAKE_CURRENT_BINARY_DIR}/generated>
        $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
)

if(MSVC)
    target_compile_options(openhdo_core PRIVATE /W4)
else()
    target_compile_options(openhdo_core PRIVATE -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion)
endif()

if(OPENHDO_WARNINGS_AS_ERRORS)
    target_compile_options(openhdo_core PRIVATE $<$<CXX_COMPILER_ID:MSVC>:/WX> $<$<NOT:$<CXX_COMPILER_ID:MSVC>>:-Werror>)
endif()

function(openhdo_add_executable target source)
    add_executable(${target} ${source})
    target_link_libraries(${target} PRIVATE openhdo_core)
    if(MSVC)
        target_compile_options(${target} PRIVATE /W4)
    else()
        target_compile_options(${target} PRIVATE -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion)
    endif()
    if(OPENHDO_WARNINGS_AS_ERRORS)
        target_compile_options(${target} PRIVATE $<$<CXX_COMPILER_ID:MSVC>:/WX> $<$<NOT:$<CXX_COMPILER_ID:MSVC>>:-Werror>)
    endif()
endfunction()

openhdo_add_executable(openhdo-server src/server/main.cpp)
openhdo_add_executable(ohdocli src/cli/main.cpp)

if(OPENHDO_BUILD_TESTS)
    openhdo_add_executable(openhdo-smoke tests/smoke.cpp)
    openhdo_add_executable(openhdo-core-tests tests/core.cpp)
    add_test(NAME openhdo-smoke COMMAND openhdo-smoke)
    add_test(NAME openhdo-core-tests COMMAND openhdo-core-tests)
endif()

install(
    TARGETS openhdo_core openhdo-server ohdocli
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)
install(DIRECTORY include/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/generated/openhdo/config.hpp" DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/openhdo)
