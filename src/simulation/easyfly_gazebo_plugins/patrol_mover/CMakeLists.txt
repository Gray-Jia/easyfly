# PatrolMover — 巡航移动目标驱动插件 (M4.1)
# 作为 easyfly_gazebo_plugins 的子目录编译, 不单独成包
# 产物: libpatrol_mover.so (GAZEBO_PLUGIN_PATH 已含本包 lib/)

set(CMAKE_CXX_STANDARD 17)
if(NOT CMAKE_CXX_STANDARD_REQUIRED)
  set(CMAKE_CXX_STANDARD_REQUIRED ON)
endif()

find_package(gazebo_dev REQUIRED)
find_package(gazebo REQUIRED)

add_library(patrol_mover SHARED
  src/patrol_mover.cpp
)

target_include_directories(patrol_mover PRIVATE
  ${GAZEBO_INCLUDE_DIRS}
  ${SDFormat_INCLUDE_DIRS}
)
target_link_libraries(patrol_mover
  gazebo
  ${GAZEBO_LIBRARIES}
)

install(TARGETS patrol_mover
  LIBRARY DESTINATION lib
  ARCHIVE DESTINATION lib
  RUNTIME DESTINATION bin
)
