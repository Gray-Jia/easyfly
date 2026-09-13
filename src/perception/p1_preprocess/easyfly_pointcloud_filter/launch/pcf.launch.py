"""
pcf.launch.py — easyfly_pointcloud_filter 启动

用法:
  ros2 launch easyfly_pointcloud_filter pcf.launch.py            # 仿真 (use_sim_time=true)
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
        package="easyfly_pointcloud_filter",
        executable="pointcloud_filter_node",
        name="easyfly_pointcloud_filter",
        output="screen",
        parameters=[{
            "use_sim_time": LaunchConfiguration("use_sim_time"),
            "config_file": os.path.join(
                get_package_share_directory("easyfly_pointcloud_filter"),
                "config", "pointcloud_filter.yaml"),
        }],
    )

    return LaunchDescription([use_sim_time_arg, node])
