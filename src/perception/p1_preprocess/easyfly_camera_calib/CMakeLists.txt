cmake_minimum_required(VERSION 3.8)
project(easyfly_camera_calib)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_components REQUIRED)
find_package(ament_index_cpp REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(yaml-cpp REQUIRED)

add_library(${PROJECT_NAME}_nodes SHARED
  src/calib_tf_publisher.cpp
  src/camera_info_checker.cpp
)
target_compile_options(${PROJECT_NAME}_nodes PRIVATE -Wall -Wextra)
ament_target_dependencies(${PROJECT_NAME}_nodes
  rclcpp rclcpp_components ament_index_cpp tf2_ros geometry_msgs sensor_msgs)
target_link_libraries(${PROJECT_NAME}_nodes yaml-cpp)
rclcpp_components_register_node(${PROJECT_NAME}_nodes
  PLUGIN "easyfly_camera_calib::CalibTfPublisher"
  EXECUTABLE calib_tf_publisher)
rclcpp_components_register_node(${PROJECT_NAME}_nodes
  PLUGIN "easyfly_camera_calib::CameraInfoChecker"
  EXECUTABLE camera_info_checker)

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
