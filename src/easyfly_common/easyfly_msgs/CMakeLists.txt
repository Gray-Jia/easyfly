cmake_minimum_required(VERSION 3.8)
project(easyfly_msgs)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)

set(msg_files
  "msg/NavigationSession.msg"
  "msg/UAVState.msg"
  "msg/UAVCommand.msg"
  "msg/DetectionInfo.msg"
  "msg/DetectionInfoArray.msg"
  "msg/TrackInfo.msg"
  "msg/TrackInfoArray.msg"
  "msg/Target3D.msg"
  "msg/Target3DArray.msg"
  "msg/ObstacleInfo.msg"
  "msg/ObstacleInfoArray.msg"
  "msg/GimbalState.msg"
  "msg/SwarmInfo.msg"
  "msg/MissionStatus.msg"
)

set(srv_files
  "srv/SetNavigationSession.srv"
  "srv/StopNavigation.srv"
  "srv/ArmMotors.srv"
  "srv/SetFlightMode.srv"
  "srv/GetObstacles.srv"
  "srv/TriggerLanding.srv"
  "srv/SetGimbalAngle.srv"
  "srv/QueryParams.srv"
)

set(action_files
  "action/Takeoff.action"
  "action/Land.action"
  "action/GoToWaypoint.action"
  "action/TrackTarget.action"
  "action/FollowTrajectory.action"
  "action/NavigateTo.action"
  "action/SearchArea.action"
  "action/ExecuteMission.action"
)

rosidl_generate_interfaces(${PROJECT_NAME}
  ${msg_files}
  ${srv_files}
  ${action_files}
  DEPENDENCIES std_msgs
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
