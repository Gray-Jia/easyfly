# Project-local, independently named camera plugin; never replaces /opt/ros.
find_package(camera_info_manager REQUIRED)
find_package(gazebo_dev REQUIRED)
find_package(gazebo_plugins REQUIRED)
find_package(gazebo_ros REQUIRED)
find_package(image_transport REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)

add_library(easyfly_gazebo_ros_camera SHARED src/safe_camera.cpp)
target_compile_features(easyfly_gazebo_ros_camera PRIVATE cxx_std_17)
target_include_directories(easyfly_gazebo_ros_camera PRIVATE
  include ${gazebo_plugins_INCLUDE_DIRS})
ament_target_dependencies(easyfly_gazebo_ros_camera
  camera_info_manager gazebo_dev gazebo_ros image_transport rclcpp sensor_msgs std_msgs)
find_library(EASYFLY_MULTI_CAMERA_LIB multi_camera_plugin
  HINTS ${gazebo_plugins_LIBRARY_DIRS} /opt/ros/humble/lib REQUIRED)
find_library(EASYFLY_CAMERA_BASE_LIB CameraPlugin
  HINTS ${GAZEBO_LIBRARY_DIRS}/gazebo-${GAZEBO_MAJOR_VERSION}/plugins
  /usr/lib/x86_64-linux-gnu/gazebo-11/plugins REQUIRED)
find_library(EASYFLY_DEPTH_BASE_LIB DepthCameraPlugin
  HINTS ${GAZEBO_LIBRARY_DIRS}/gazebo-${GAZEBO_MAJOR_VERSION}/plugins
  /usr/lib/x86_64-linux-gnu/gazebo-11/plugins REQUIRED)
target_link_libraries(easyfly_gazebo_ros_camera
  ${EASYFLY_CAMERA_BASE_LIB} ${EASYFLY_DEPTH_BASE_LIB} ${EASYFLY_MULTI_CAMERA_LIB})
install(TARGETS easyfly_gazebo_ros_camera LIBRARY DESTINATION lib)
install(FILES README.md LICENSE DESTINATION share/${PROJECT_NAME}/safe_camera)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_camera_patch_contract test/test_patch_contract.py TIMEOUT 15)
  ament_add_gtest(test_camera_duplicate test/test_camera_duplicate.cpp TIMEOUT 15)
  target_include_directories(test_camera_duplicate PRIVATE
    include ${gazebo_plugins_INCLUDE_DIRS})
  ament_target_dependencies(test_camera_duplicate gazebo_dev gazebo_ros rclcpp)
  target_link_libraries(test_camera_duplicate easyfly_gazebo_ros_camera)
endif()
