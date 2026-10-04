cmake_minimum_required(VERSION 3.8)
project(easyfly_mission_scripts)

find_package(ament_cmake REQUIRED)

# Resource package: templates only, no second mission execution engine.
install(DIRECTORY missions DESTINATION share/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
