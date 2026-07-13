cmake_minimum_required(VERSION 3.8)
project(easyfly_serial)

# 默认 C++17
if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

find_package(ament_cmake REQUIRED)

# ============================================================
# 静态库 libeasyfly_serial — 零 ROS2 依赖
# ============================================================
add_library(easyfly_serial STATIC
  src/serial_port.cpp
)

target_include_directories(easyfly_serial
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)

# ============================================================
# 安装
# ============================================================
install(
  DIRECTORY include/
  DESTINATION include
)

install(
  TARGETS easyfly_serial
  ARCHIVE DESTINATION lib
)

# ============================================================
# 测试（阶段一：自发自收验证）
# ============================================================
if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)

  add_executable(test_loopback test/test_loopback.cpp)
  target_link_libraries(test_loopback easyfly_serial)
  target_include_directories(test_loopback PRIVATE include)

  ament_add_test(
    test_loopback
    GENERATE_RESULT_FOR_RETURN_CODE_ZERO
    COMMAND "$<TARGET_FILE:test_loopback>"
  )
endif()

ament_package()
