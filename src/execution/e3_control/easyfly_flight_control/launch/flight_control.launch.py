"""
flight_control.launch.py — 飞控节点启动 (Q11/Q26: launch 化 + use_sim_time 注入)

用法:
  ros2 launch easyfly_flight_control flight_control.launch.py                      # 仿真 (use_sim_time=true)
  ros2 launch easyfly_flight_control flight_control.launch.py use_sim_time:=false  # 实机
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory

import os


def generate_launch_description():
    use_sim_time_arg = DeclareLaunchArgument(
        "use_sim_time", default_value="true",
        description="仿真时钟 (实机部署设为 false)")

    flight_control = Node(
        package="easyfly_flight_control",
        executable="flight_control_node",
        name="flight_controller",
        output="screen",
        parameters=[
            os.path.join(get_package_share_directory("easyfly_flight_control"),
                         "config", "flight_control.yaml"),
            {
                "use_sim_time": LaunchConfiguration("use_sim_time"),
                # 控制循环节拍用 wall_timer；deadline/进度使用节点 ROS clock。
            },
        ],
    )

    return LaunchDescription([use_sim_time_arg, flight_control])
