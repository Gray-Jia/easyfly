cmake_minimum_required(VERSION 3.8)
project(easyfly_multi_object_tracking)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_components REQUIRED)
find_package(ament_index_cpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(easyfly_msgs REQUIRED)
find_package(OpenCV REQUIRED)
find_package(yaml-cpp REQUIRED)

# SORT 核心为 header-only (include/)
add_library(${PROJECT_NAME}_nodes SHARED
  src/tracking_node.cpp
)
target_include_directories(${PROJECT_NAME}_nodes PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_compile_options(${PROJECT_NAME}_nodes PRIVATE -Wall -Wextra)
ament_target_dependencies(${PROJECT_NAME}_nodes
  rclcpp rclcpp_components ament_index_cpp sensor_msgs easyfly_msgs)
target_link_libraries(${PROJECT_NAME}_nodes ${OpenCV_LIBS} yaml-cpp)
rclcpp_components_register_node(${PROJECT_NAME}_nodes
  PLUGIN "easyfly_multi_object_tracking::TrackingNode"
  EXECUTABLE tracking_node)

install(TARGETS ${PROJECT_NAME}_nodes
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin)
install(DIRECTORY include/
  DESTINATION include/${PROJECT_NAME})
install(DIRECTORY config launch
  DESTINATION share/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_sort test/test_sort.cpp)
  target_include_directories(test_sort PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include)
  ament_add_gtest(test_id_consolidator test/test_id_consolidator.cpp)
  target_include_directories(test_id_consolidator PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include)
endif()

ament_export_include_directories(include)
ament_package()
