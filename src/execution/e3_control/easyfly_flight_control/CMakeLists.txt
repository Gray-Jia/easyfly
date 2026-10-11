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
find_package(easyfly_precision_landing REQUIRED)

add_executable(flight_control_node
  src/flight_control_node.cpp
  src/flight_controller.cpp
  src/precision_controller.cpp
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
  easyfly_precision_landing
)

install(TARGETS flight_control_node
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
  # Scope the slow-version override to this bounded test, never the workspace.
  set_tests_properties(cppcheck PROPERTIES ENVIRONMENT "AMENT_CPPCHECK_ALLOW_SLOW_VERSIONS=1")
  ament_cpplint(include src test)
  ament_uncrustify(include src test)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_trajectory_startup_timeout
    test/test_trajectory_startup_timeout.cpp)
  target_include_directories(test_trajectory_startup_timeout PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include)
  ament_add_gtest(test_navigation_session test/test_navigation_session.cpp
    src/flight_controller.cpp src/precision_controller.cpp)
  target_include_directories(test_navigation_session PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)
  ament_target_dependencies(test_navigation_session rclcpp rclcpp_action easyfly_msgs quadrotor_msgs easyfly_precision_landing)
  ament_add_gtest(test_flight_safety test/test_flight_safety.cpp
    src/flight_controller.cpp src/precision_controller.cpp TIMEOUT 60)
  target_include_directories(test_flight_safety PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)
  ament_target_dependencies(test_flight_safety rclcpp rclcpp_action easyfly_msgs quadrotor_msgs easyfly_precision_landing)
  set_tests_properties(test_flight_safety PROPERTIES ENVIRONMENT "ROS_DOMAIN_ID=198")
  ament_add_gtest(test_precision_landing test/test_precision_landing.cpp
    src/flight_controller.cpp src/precision_controller.cpp TIMEOUT 30)
  target_include_directories(test_precision_landing PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)
  ament_target_dependencies(test_precision_landing rclcpp rclcpp_action easyfly_msgs quadrotor_msgs easyfly_precision_landing)
  set_tests_properties(test_precision_landing PROPERTIES ENVIRONMENT "ROS_DOMAIN_ID=190")
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_mode_wait_shutdown test/test_mode_wait_shutdown.py TIMEOUT 30)
  set_tests_properties(test_mode_wait_shutdown PROPERTIES ENVIRONMENT "ROS_DOMAIN_ID=199")
  ament_add_pytest_test(test_stop_stream_chain test/test_stop_stream_chain.py TIMEOUT 30)
  set_tests_properties(test_stop_stream_chain PROPERTIES ENVIRONMENT "ROS_DOMAIN_ID=196")
  ament_add_pytest_test(test_precision_ros test/test_precision_ros.py TIMEOUT 75)
  set_tests_properties(test_precision_ros PROPERTIES ENVIRONMENT "ROS_DOMAIN_ID=191")
  find_package(std_msgs REQUIRED)
  ament_add_gtest(test_precision_queue test/test_precision_queue.cpp
    src/flight_controller.cpp src/precision_controller.cpp TIMEOUT 30)
  target_include_directories(test_precision_queue PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)
  ament_target_dependencies(test_precision_queue rclcpp rclcpp_action easyfly_msgs quadrotor_msgs easyfly_precision_landing std_msgs)
  set_tests_properties(test_precision_queue PROPERTIES ENVIRONMENT "ROS_DOMAIN_ID=203")
  ament_add_pytest_test(test_precision_receiver_chain test/test_precision_receiver_chain.py TIMEOUT 30)
  set_tests_properties(test_precision_receiver_chain PROPERTIES ENVIRONMENT "ROS_DOMAIN_ID=204")
endif()

ament_package()
