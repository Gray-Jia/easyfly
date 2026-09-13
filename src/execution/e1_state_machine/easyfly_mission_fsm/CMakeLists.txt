cmake_minimum_required(VERSION 3.8)
project(easyfly_mission_fsm)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(easyfly_msgs REQUIRED)

add_executable(mission_fsm_node
  src/mission_fsm_node.cpp
  src/mission_fsm.cpp
)

target_include_directories(mission_fsm_node
  PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)

ament_target_dependencies(mission_fsm_node
  rclcpp
  rclcpp_action
  easyfly_msgs
)

install(TARGETS mission_fsm_node
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY missions launch
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
endif()

ament_package()
