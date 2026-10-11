cmake_minimum_required(VERSION 3.8)
project(easyfly_sim_launcher)

find_package(ament_cmake REQUIRED)

install(DIRECTORY launch
  DESTINATION share/${PROJECT_NAME})
install(PROGRAMS scripts/d5_simulation DESTINATION lib/${PROJECT_NAME})
install(PROGRAMS scripts/navigation_sitl.py
  DESTINATION lib/${PROJECT_NAME} RENAME navigation_sitl)
install(PROGRAMS scripts/battery_sitl.py
  DESTINATION lib/${PROJECT_NAME} RENAME battery_sitl)

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_profile_launch test/test_profile_launch.py)
  ament_add_pytest_test(test_navigation_sitl test/test_navigation_sitl.py TIMEOUT 15)
  ament_add_pytest_test(test_battery_sitl test/test_battery_sitl.py TIMEOUT 15)
endif()

ament_package()
