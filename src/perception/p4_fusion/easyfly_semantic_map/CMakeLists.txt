cmake_minimum_required(VERSION 3.8)
project(easyfly_semantic_map)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_components REQUIRED)
find_package(ament_index_cpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(visualization_msgs REQUIRED)
find_package(easyfly_msgs REQUIRED)
find_package(tf2 REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(tf2_eigen REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(PCL REQUIRED COMPONENTS common filters segmentation search)
find_package(pcl_conversions REQUIRED)
find_package(yaml-cpp REQUIRED)

add_library(${PROJECT_NAME}_nodes SHARED
  src/semantic_map_node.cpp
)
target_compile_options(${PROJECT_NAME}_nodes PRIVATE -Wall -Wextra)
target_link_libraries(${PROJECT_NAME}_nodes ${PCL_LIBRARIES} yaml-cpp)
ament_target_dependencies(${PROJECT_NAME}_nodes
  rclcpp rclcpp_components ament_index_cpp sensor_msgs nav_msgs visualization_msgs
  easyfly_msgs tf2 tf2_ros tf2_eigen geometry_msgs pcl_conversions)

rclcpp_components_register_node(${PROJECT_NAME}_nodes
  PLUGIN "easyfly_semantic_map::SemanticMapNode"
  EXECUTABLE semantic_map_node)

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
