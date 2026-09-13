cmake_minimum_required(VERSION 3.8)
project(easyfly_object_detection)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_components REQUIRED)
find_package(ament_index_cpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(easyfly_msgs REQUIRED)
find_package(OpenCV REQUIRED)          # 系统 4.5.4: 仅用 resize/cvtColor/rectangle
find_package(yaml-cpp REQUIRED)

# ---- onnxruntime C++ SDK (third_party, 可用 ORT_ROOT 覆盖) ----
set(ORT_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../../third_party/onnxruntime" CACHE PATH "onnxruntime SDK root")
if(NOT EXISTS "${ORT_ROOT}/include/onnxruntime_cxx_api.h")
  message(FATAL_ERROR "onnxruntime SDK 未找到: ${ORT_ROOT} (请检查 third_party/onnxruntime)")
endif()

add_library(${PROJECT_NAME}_core SHARED
  src/onnx/onnx_backend.cpp
)
target_compile_options(${PROJECT_NAME}_core PRIVATE -Wall -Wextra)
target_include_directories(${PROJECT_NAME}_core PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  ${ORT_ROOT}/include
)
ament_target_dependencies(${PROJECT_NAME}_core
  rclcpp ament_index_cpp sensor_msgs easyfly_msgs)
target_link_libraries(${PROJECT_NAME}_core
  ${OpenCV_LIBS} yaml-cpp
  ${ORT_ROOT}/lib/libonnxruntime.so)

# 节点 (组件库)
add_library(${PROJECT_NAME}_nodes SHARED
  src/detection_node.cpp
)
target_compile_options(${PROJECT_NAME}_nodes PRIVATE -Wall -Wextra)
target_link_libraries(${PROJECT_NAME}_nodes ${PROJECT_NAME}_core)
ament_target_dependencies(${PROJECT_NAME}_nodes
  rclcpp rclcpp_components ament_index_cpp sensor_msgs easyfly_msgs)
target_link_libraries(${PROJECT_NAME}_nodes yaml-cpp)

rclcpp_components_register_node(${PROJECT_NAME}_nodes
  PLUGIN "easyfly_object_detection::DetectionNode"
  EXECUTABLE detection_node)

# RPATH: $ORIGIN (SDK 运行库一并安装到 lib/, 部署自包含)
set_target_properties(${PROJECT_NAME}_core PROPERTIES
  BUILD_RPATH "${ORT_ROOT}/lib"
  INSTALL_RPATH "$ORIGIN")
set_target_properties(${PROJECT_NAME}_nodes PROPERTIES
  BUILD_RPATH "${ORT_ROOT}/lib"
  INSTALL_RPATH "$ORIGIN")

install(TARGETS ${PROJECT_NAME}_core ${PROJECT_NAME}_nodes
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin)

# onnxruntime 运行库随包安装 (providers_*.so 由 libonnxruntime.so 懒加载 dlopen)
# 注意: libonnxruntime.so / .so.1 是符号链接, 只复制实体并用链接还原
install(FILES
  ${ORT_ROOT}/lib/libonnxruntime.so.1.23.2
  ${ORT_ROOT}/lib/libonnxruntime_providers_shared.so
  ${ORT_ROOT}/lib/libonnxruntime_providers_cuda.so
  DESTINATION lib)
install(CODE "
  execute_process(COMMAND ln -sf libonnxruntime.so.1.23.2
    \$ENV{DESTDIR}\${CMAKE_INSTALL_PREFIX}/lib/libonnxruntime.so.1)
  execute_process(COMMAND ln -sf libonnxruntime.so.1
    \$ENV{DESTDIR}\${CMAKE_INSTALL_PREFIX}/lib/libonnxruntime.so)
")
install(DIRECTORY include/
  DESTINATION include/${PROJECT_NAME}
  FILES_MATCHING PATTERN "*.hpp")
install(DIRECTORY config launch
  DESTINATION share/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_export_include_directories(include)
ament_export_dependencies(rclcpp easyfly_msgs OpenCV)

ament_package()
