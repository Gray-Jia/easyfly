cmake_minimum_required(VERSION 3.8)
project(easyfly_gazebo_plugins)

find_package(ament_cmake REQUIRED)

# 阶段一：不编译任何插件（传感器仿真在阶段三启用）
# 阶段三启用时，取消下方注释并添加 gazebo_dev / gazebo_ros 依赖：
#   add_subdirectory(livox_laser_plugin)
#   add_subdirectory(realsense_plugin)
#   add_subdirectory(velodyne_plugin)

ament_package()
