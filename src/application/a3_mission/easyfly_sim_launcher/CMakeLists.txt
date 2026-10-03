cmake_minimum_required(VERSION 3.8)
project(easyfly_sim_launcher)

find_package(ament_cmake REQUIRED)

install(DIRECTORY launch
  DESTINATION share/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_profile_launch test/test_profile_launch.py)
endif()

ament_package()
