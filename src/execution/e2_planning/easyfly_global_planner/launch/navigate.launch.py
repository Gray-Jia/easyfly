"""
navigate.launch.py — easyfly_global_planner 启动 (M4.2)

用法:
  ros2 launch easyfly_global_planner navigate.launch.py   # 仿真 (use_sim_time=true)

节点常驻 (idle 无副作用), 导航经 /navigate action 发起。
"""

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import os


def generate_launch_description():
    use_sim_time_arg = DeclareLaunchArgument(
        "use_sim_time", default_value="true", description="仿真时钟 (实机设 false)")

    node = Node(
        package="easyfly_global_planner",
        executable="global_planner_node",
        name="easyfly_global_planner",
        output="screen",
        parameters=[{
            "use_sim_time": LaunchConfiguration("use_sim_time"),
            "config_file": os.path.join(
                get_package_share_directory("easyfly_global_planner"),
                "config", "navigate.yaml"),
        }],
    )

    return LaunchDescription([use_sim_time_arg, node])
