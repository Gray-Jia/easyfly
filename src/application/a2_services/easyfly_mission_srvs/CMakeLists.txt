cmake_minimum_required(VERSION 3.8)
project(easyfly_mission_srvs)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(easyfly_msgs REQUIRED)
find_package(easyfly_core REQUIRED)
find_package(easyfly_mission_fsm REQUIRED)
find_package(ament_index_cpp REQUIRED)
set(CMAKE_CXX_STANDARD 17)
add_executable(mission_services src/mission_services.cpp)
ament_target_dependencies(mission_services rclcpp rclcpp_action easyfly_msgs easyfly_mission_fsm ament_index_cpp)
target_link_libraries(mission_services easyfly_mission_fsm::easyfly_mission_format easyfly_core::easyfly_core)
target_compile_options(mission_services PRIVATE -Wall -Wextra)
install(TARGETS mission_services DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY launch DESTINATION share/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_services test/test_services.py TIMEOUT 60
    ENV ROS_DOMAIN_ID=95 ROS_LOG_DIR=/tmp/easyfly_d2_missions)
  ament_add_pytest_test(test_launch test/test_launch.py
    ENV ROS_LOG_DIR=/tmp/easyfly_d2_launch)
  ament_add_pytest_test(test_platform_smoke test/test_platform_smoke.py TIMEOUT 30
    ENV ROS_DOMAIN_ID=97 ROS_LOG_DIR=/tmp/easyfly_d2_platform_smoke)
endif()

ament_package()
