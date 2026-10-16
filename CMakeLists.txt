cmake_minimum_required(VERSION 3.20)
project(optimizer_core LANGUAGES CXX)

add_library(optimizer_core SHARED optimizer_core.cpp)
target_compile_features(optimizer_core PRIVATE cxx_std_17)
target_compile_definitions(optimizer_core PRIVATE UNICODE _UNICODE)
target_include_directories(optimizer_core PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}")
target_link_libraries(optimizer_core PRIVATE user32)
