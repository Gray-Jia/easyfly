cmake_minimum_required(VERSION 3.8)
project(easyfly_target_tracking)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_components REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(ament_index_cpp REQUIRED)
find_package(easyfly_msgs REQUIRED)
find_package(yaml-cpp REQUIRED)

add_library(${PROJECT_NAME}_nodes SHARED
  src/target_tracking_node.cpp
)
target_compile_options(${PROJECT_NAME}_nodes PRIVATE -Wall -Wextra)
ament_target_dependencies(${PROJECT_NAME}_nodes
  rclcpp rclcpp_components rclcpp_action ament_index_cpp easyfly_msgs)
target_link_libraries(${PROJECT_NAME}_nodes yaml-cpp)

rclcpp_components_register_node(${PROJECT_NAME}_nodes
  PLUGIN "easyfly_target_tracking::TargetTrackingNode"
  EXECUTABLE target_tracking_node)

install(TARGETS ${PROJECT_NAME}_nodes
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin)
install(DIRECTORY config launch
  DESTINATION share/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
