cmake_minimum_required(VERSION 3.8)
project(easyfly_mavlink_bridge)

include(CTest)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(easyfly_msgs REQUIRED)
find_package(mavros_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)

# ---- mavlink_bridge 节点 ----
add_executable(mavlink_bridge_node
  src/mavlink_bridge_node.cpp
  src/mavlink_bridge.cpp
)

target_include_directories(mavlink_bridge_node
  PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)

ament_target_dependencies(mavlink_bridge_node
  rclcpp
  easyfly_msgs
  mavros_msgs
  geometry_msgs
  sensor_msgs
)

install(TARGETS mavlink_bridge_node
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY launch config
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_cmake_cppcheck REQUIRED)
  find_package(ament_cmake_cpplint REQUIRED)
  find_package(ament_cmake_uncrustify REQUIRED)
  ament_cppcheck(include src test LIBRARIES googletest)
  # This small package is checked, not skipped by Humble's cppcheck 2.x guard.
  set_tests_properties(cppcheck PROPERTIES ENVIRONMENT "AMENT_CPPCHECK_ALLOW_SLOW_VERSIONS=1")
  ament_cpplint(include src test)
  ament_uncrustify(include src test)
  find_package(ament_cmake_gtest REQUIRED)
  find_package(ament_cmake_pytest REQUIRED)
  find_package(Python3 REQUIRED COMPONENTS Interpreter)
  ament_add_gtest(test_bridge_freshness
    test/test_bridge_freshness.cpp src/mavlink_bridge.cpp TIMEOUT 40)
  target_include_directories(test_bridge_freshness PRIVATE include)
  ament_target_dependencies(test_bridge_freshness
    rclcpp easyfly_msgs mavros_msgs geometry_msgs sensor_msgs)
  set_tests_properties(test_bridge_freshness PROPERTIES ENVIRONMENT "ROS_DOMAIN_ID=197")
  ament_add_pytest_test(test_bridge_shutdown test/test_bridge_shutdown.py TIMEOUT 20)
  set_tests_properties(test_bridge_shutdown PROPERTIES ENVIRONMENT "ROS_DOMAIN_ID=195")
  ament_add_pytest_test(test_bridge_fault_ros test/test_bridge_fault_ros.py TIMEOUT 65)
  set_tests_properties(test_bridge_fault_ros PROPERTIES ENVIRONMENT "ROS_DOMAIN_ID=210")
  add_test(
    NAME mavlink_bridge_sim_time_contract
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_CURRENT_SOURCE_DIR}/test/test_mavlink_bridge_sim_time_contract.py)
endif()

ament_package()
