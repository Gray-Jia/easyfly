cmake_minimum_required(VERSION 3.8)
project(easyfly_utils)

find_package(ament_cmake REQUIRED)

# Header-only library — 安装头文件即可
install(DIRECTORY include/
  DESTINATION include/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
