cmake_minimum_required(VERSION 3.8)
project(easyfly_rc_receiver)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(mavros_msgs REQUIRED)
find_package(std_msgs REQUIRED)

add_executable(rc_receiver_node
  src/rc_receiver_node.cpp
)

ament_target_dependencies(rc_receiver_node
  rclcpp
  mavros_msgs
  std_msgs
)

install(TARGETS rc_receiver_node
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY launch
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
