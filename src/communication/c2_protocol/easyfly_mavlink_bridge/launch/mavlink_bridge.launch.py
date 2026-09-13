"""
mavlink_bridge.launch.py — 启动 mavros2 + easyfly_mavlink_bridge

用法:
  # 仿真 (UDP 连接 PX4 SITL)
  ros2 launch easyfly_mavlink_bridge mavlink_bridge.launch.py fcu_url:=udp://:14540@127.0.0.1:14555

  # 真机 (串口连接飞控)
  ros2 launch easyfly_mavlink_bridge mavlink_bridge.launch.py fcu_url:=/dev/ttyUSB0:921600
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory

import os


def generate_launch_description():
    # ---- mavros2 launch ----
    mavros_launch_dir = os.path.join(
        get_package_share_directory("mavros"), "launch")

    fcu_url_arg = DeclareLaunchArgument(
        "fcu_url",
        default_value="udp://:14540@127.0.0.1:14555",
        description="MAVLink connection: udp://... for SITL, serial:///dev/... for real")

    fcu_url = LaunchConfiguration("fcu_url")

    mavros_node = Node(
        package="mavros",
        executable="mavros_node",
        output="screen",
        parameters=[{
            "fcu_url": fcu_url,
            "gcs_url": "",
            "tgt_system": 1,
        }],
        ros_arguments=["--params-file",
            os.path.join(get_package_share_directory("mavros"),
                         "launch", "px4_config.yaml")],
    )

    # ---- easyfly_mavlink_bridge ----
    # use_sim_time: /uav_state.header.stamp 是下游 TF (odom→base_link) 的时间戳来源,
    # 仿真中必须用 sim 时钟, 否则 TF 时间戳超前于 /clock → RViz/查询 extrapolation 失败
    bridge_node = Node(
        package="easyfly_mavlink_bridge",
        executable="mavlink_bridge_node",
        output="screen",
        name="mavlink_bridge",
        parameters=[{"use_sim_time": True}],
    )

    # ---- easyfly_rc_receiver ----
    rc_node = Node(
        package="easyfly_rc_receiver",
        executable="rc_receiver_node",
        output="screen",
        name="rc_receiver",
    )

    return LaunchDescription([
        fcu_url_arg,
        mavros_node,
        bridge_node,
        rc_node,
    ])
