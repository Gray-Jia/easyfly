"""
ego_acceptance.launch.py — M4.3 EGO-Planner 验收专用轻链启动 (test/ 自有, 不参与 colcon 构建)

内容 (perception_demo.world, 含 3m 立柱 + patrol 行人):
  t=0s   px4_sitl.launch.py (world:=perception_demo.world)  gzserver + 模型 + PX4
  t=8s   mavlink_bridge                                     /uav_state + setpoint encoder
  t=10s  flight_control                                     /takeoff /land /goto_waypoint /follow_trajectory
  t=12s  camera_calib(calib_tf) + coord_transform           base_link→livox_frame, /odom
  t=14s  pointcloud_filter                                  /livox/lidar → /pointcloud_filtered (odom 系)
  t=16s  local_planner (EGO)                                ego_planner_node + traj_server → /position_cmd
  t=18s  semantic_map                                       /obstacles + /occupancy_grid (验收自锚定用)

不含 YOLO/SLAM/跟踪 (轻链); 这是 E1-E4 的编排目标。
用法 (通常经 bash test/run_ego_acceptance.sh):
  ros2 launch test/ego_acceptance.launch.py
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def _inc(pkg: str, name: str, args: dict | None = None) -> IncludeLaunchDescription:
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(get_package_share_directory(pkg), "launch", name)),
        launch_arguments=(args or {}).items())


def generate_launch_description():
    use_ego = LaunchConfiguration('use_ego')
    declare_ego = DeclareLaunchArgument(
        'use_ego', default_value='true',
        description='是否启动 EGO local_planner (false=仅其余链, 用于 A/B 定位)')

    sim = _inc("easyfly_px4_sitl", "px4_sitl.launch.py",
               {"world": "perception_demo.world"})

    bridge = TimerAction(period=8.0, actions=[
        _inc("easyfly_mavlink_bridge", "mavlink_bridge.launch.py")])

    control = TimerAction(period=10.0, actions=[
        _inc("easyfly_flight_control", "flight_control.launch.py")])

    p1 = TimerAction(period=12.0, actions=[
        _inc("easyfly_camera_calib", "calib_tf.launch.py"),
        _inc("easyfly_coord_transform", "coord_tf.launch.py")])

    pcf = TimerAction(period=14.0, actions=[
        _inc("easyfly_pointcloud_filter", "pcf.launch.py")])

    ego = TimerAction(period=16.0, actions=[
        _inc("easyfly_local_planner", "local_planner.launch.py")],
        condition=IfCondition(use_ego))

    semantic = TimerAction(period=18.0, actions=[
        _inc("easyfly_semantic_map", "semantic_map.launch.py")])

    return LaunchDescription([declare_ego, sim, bridge, control, p1, pcf, ego, semantic])
