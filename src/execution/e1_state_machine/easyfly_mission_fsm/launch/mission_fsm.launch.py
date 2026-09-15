"""
mission_fsm.launch.py — 任务状态机节点启动 (Q11/Q26: launch 化 + use_sim_time 注入)

用法:
  ros2 launch easyfly_mission_fsm mission_fsm.launch.py                      # 仿真
  ros2 launch easyfly_mission_fsm mission_fsm.launch.py use_sim_time:=false  # 实机
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    use_sim_time_arg = DeclareLaunchArgument(
        "use_sim_time", default_value="true",
        description="仿真时钟 (实机部署设为 false)")

    mission_fsm = Node(
        package="easyfly_mission_fsm",
        executable="mission_fsm_node",
        name="mission_fsm",
        output="screen",
        parameters=[{
            "use_sim_time": LaunchConfiguration("use_sim_time"),
            # 持续无效/过期的电池遥测在此宽限期后触发空中 RTL+任务中止。
            "battery_invalid_grace_s": 5.0,
        }],
    )

    return LaunchDescription([use_sim_time_arg, mission_fsm])
