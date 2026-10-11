cmake_minimum_required(VERSION 3.8)
project(easyfly_target_prediction)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(easyfly_msgs REQUIRED)

add_executable(target_prediction_node src/target_prediction_node.cpp)
target_compile_features(target_prediction_node PRIVATE cxx_std_17)
target_include_directories(target_prediction_node PRIVATE include)
ament_target_dependencies(target_prediction_node rclcpp easyfly_msgs)
install(TARGETS target_prediction_node DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY include/ DESTINATION include)
install(DIRECTORY launch DESTINATION share/${PROJECT_NAME})
ament_export_include_directories(include)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_predictor test/test_predictor.cpp)
  target_compile_features(test_predictor PRIVATE cxx_std_17)
  target_include_directories(test_predictor PRIVATE include)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_prediction_ros test/test_prediction_ros.py TIMEOUT 60
    ENV ROS_DOMAIN_ID=104 ROS_LOG_DIR=/tmp/easyfly_d4_prediction)
endif()

ament_package()
