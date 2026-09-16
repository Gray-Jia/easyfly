cmake_minimum_required(VERSION 3.8)

find_package(ament_cmake REQUIRED)
project(easyfly_px4_sitl)

include(CTest)
if(BUILD_TESTING)
  find_package(Python3 REQUIRED COMPONENTS Interpreter)
  add_test(
    NAME easyfly_iris_sdf_physics_and_camera_contract
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_CURRENT_SOURCE_DIR}/test/validate_easyfly_iris_sdf.py)
endif()

install(DIRECTORY launch models rviz
  DESTINATION share/easyfly_px4_sitl
  PATTERN ".git" EXCLUDE)

ament_package()
