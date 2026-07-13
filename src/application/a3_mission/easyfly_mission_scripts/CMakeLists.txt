cmake_minimum_required(VERSION 3.8)
project(easyfly_mission_scripts)

find_package(ament_cmake REQUIRED)

# TODO: add library/executable targets

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
