cmake_minimum_required(VERSION 3.25)
project(InfernuxTweenGpuProbes LANGUAGES CXX)

find_package(Vulkan REQUIRED)
add_executable(infernux_curve_gpu_probe curve_gpu_probe.cpp)
target_compile_features(infernux_curve_gpu_probe PRIVATE cxx_std_20)
target_link_libraries(infernux_curve_gpu_probe PRIVATE Vulkan::Vulkan)
