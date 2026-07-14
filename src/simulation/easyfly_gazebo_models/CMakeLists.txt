cmake_minimum_required(VERSION 3.8)

find_package(ament_cmake REQUIRED)
project(easyfly_gazebo_models)

# 纯数据包——只把模型文件安装到 install 目录
install(DIRECTORY . DESTINATION share/easyfly_gazebo_models
  PATTERN ".git" EXCLUDE
  PATTERN "CMakeLists.txt" EXCLUDE
  PATTERN "package.xml" EXCLUDE)

ament_package()
