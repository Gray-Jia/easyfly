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
install(DIRECTORY include/ DESTINATION include)
ament_export_include_directories(include)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_legacy_mission test/test_legacy_mission.cpp)
  target_include_directories(test_legacy_mission PRIVATE include)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_prevalidation test/test_prevalidation.py TIMEOUT 30
    ENV ROS_DOMAIN_ID=96 ROS_LOG_DIR=/tmp/easyfly_d2_prevalidation)
endif()

ament_package()
