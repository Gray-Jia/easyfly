cmake_minimum_required(VERSION 3.8)
project(easyfly_mavlink_bridge)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(easyfly_msgs REQUIRED)
find_package(mavros_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)

# ---- mavlink_bridge 节点 ----
add_executable(mavlink_bridge_node
  src/mavlink_bridge_node.cpp
  src/mavlink_bridge.cpp
)

target_include_directories(mavlink_bridge_node
  PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)

ament_target_dependencies(mavlink_bridge_node
  rclcpp
  easyfly_msgs
  mavros_msgs
  geometry_msgs
  sensor_msgs
)

install(TARGETS mavlink_bridge_node
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY launch config
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  # TODO: 添加单元测试
endif()

ament_package()
