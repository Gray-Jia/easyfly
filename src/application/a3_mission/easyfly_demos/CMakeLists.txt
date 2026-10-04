cmake_minimum_required(VERSION 3.8)
project(easyfly_demos)

find_package(ament_cmake REQUIRED)

find_package(easyfly_core REQUIRED)
find_package(easyfly_mission_fsm REQUIRED)
find_package(ament_index_cpp REQUIRED)
set(CMAKE_CXX_STANDARD 17)
add_executable(sdk_mission_demo src/sdk_mission_demo.cpp)
ament_target_dependencies(sdk_mission_demo ament_index_cpp)
target_link_libraries(sdk_mission_demo easyfly_core::easyfly_core easyfly_mission_fsm::easyfly_mission_format)
install(TARGETS sdk_mission_demo DESTINATION lib/${PROJECT_NAME})
install(PROGRAMS scripts/sdk_mission_demo.py DESTINATION lib/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_task_chain test/test_task_chain.py TIMEOUT 120
    ENV ROS_DOMAIN_ID=103 ROS_LOG_DIR=/tmp/easyfly_d3_task_chain)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
