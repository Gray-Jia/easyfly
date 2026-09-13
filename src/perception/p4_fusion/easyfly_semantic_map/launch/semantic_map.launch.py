"""
semantic_map.launch.py — easyfly_semantic_map 启动

用法:
  ros2 launch easyfly_semantic_map semantic_map.launch.py     # 仿真 (use_sim_time=true)
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
        package="easyfly_semantic_map",
        executable="semantic_map_node",
        name="easyfly_semantic_map",
        output="screen",
        parameters=[{
            "use_sim_time": LaunchConfiguration("use_sim_time"),
            "config_file": os.path.join(
                get_package_share_directory("easyfly_semantic_map"),
                "config", "semantic_map.yaml"),
        }],
    )

    return LaunchDescription([use_sim_time_arg, node])
