cmake_minimum_required(VERSION 3.24)

project(openhdo VERSION 0.1.0 LANGUAGES NONE)

include(CTest)

find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)

add_custom_target(openhdo-python-check ALL
    COMMAND ${Python3_EXECUTABLE} -m compileall -q
        "${CMAKE_CURRENT_SOURCE_DIR}/python/openhdo_server"
    COMMENT "Checking Python server runtime syntax"
    VERBATIM
)

if(BUILD_TESTING)
    add_test(
        NAME openhdo-python-tests
        COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -v
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/python"
    )
endif()
