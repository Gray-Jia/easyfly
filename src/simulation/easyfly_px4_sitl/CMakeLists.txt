cmake_minimum_required(VERSION 3.8)

find_package(ament_cmake REQUIRED)
project(easyfly_px4_sitl)

install(DIRECTORY launch models rviz
  DESTINATION share/easyfly_px4_sitl
  PATTERN ".git" EXCLUDE)

ament_package()
