"""
easyfly_sim.launch.py — 一键启动 EasyFly 完整仿真环境

用法:
  ros2 launch easyfly_sim_launcher easyfly_sim.launch.py

启动:
  Gazebo + PX4 SITL → mavros2 + mavlink_bridge + rc_receiver
"""

from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    # ---- px4_sitl (Gazebo + PX4 SITL) ----
    px4_sitl_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            get_package_share_directory("easyfly_px4_sitl"),
            "/launch/px4_sitl.launch.py",
        ]),
    )

    # ---- mavlink_bridge (mavros2 + bridge + rc_receiver) ----
    bridge_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            get_package_share_directory("easyfly_mavlink_bridge"),
            "/launch/mavlink_bridge.launch.py",
        ]),
    )

    return LaunchDescription([
        px4_sitl_launch,
        bridge_launch,
    ])
