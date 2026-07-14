cmake_minimum_required(VERSION 3.8)

find_package(ament_cmake REQUIRED)
project(easyfly_gazebo_worlds)

install(DIRECTORY . DESTINATION share/easyfly_gazebo_worlds
  PATTERN ".git" EXCLUDE
  PATTERN "CMakeLists.txt" EXCLUDE
  PATTERN "package.xml" EXCLUDE)

ament_package()
