cmake_minimum_required(VERSION 3.8)
project(easyfly_flight_control)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(easyfly_msgs REQUIRED)
find_package(quadrotor_msgs REQUIRED)

add_executable(flight_control_node
  src/flight_control_node.cpp
  src/flight_controller.cpp
)

target_include_directories(flight_control_node
  PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)

ament_target_dependencies(flight_control_node
  rclcpp
  rclcpp_action
  easyfly_msgs
  quadrotor_msgs
)

install(TARGETS flight_control_node
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY launch config
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
endif()

ament_package()
