"""
control_regression.launch.py — 控制链回归测试专用一键启动 (test/ 自有, 不参与 colcon 构建)

内容 = test-guide.md 方式 B (纯控制仿真, 不含感知层):
  t=0s   gzserver(empty.world) + PX4 SITL  (px4_sitl.launch.py 内部自带 3s spawn / 6s px4 延时)
  t=8s   mavros + mavlink_bridge + rc_receiver   (bridge 内部 use_sim_time=true)
  t=10s  flight_control + mission_fsm            (use_sim_time=true, 与 perception_sitl 同参)

用法:
  ros2 launch test/control_regression.launch.py
  (通常通过编排器运行: bash test/run_control_regression.sh)

注意:
  - 无显示器环境下 px4_sitl.launch.py 里的 gzclient 启动失败属正常现象, 不影响
    gzserver/PX4/测试 (日志中有 Gazebo GUI 报错可忽略);
  - 感知链回归 (检测/跟踪/SLAM) 不在本套件范围, 用 perception_sitl.launch.py 手动验证。
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource


def _inc(pkg: str, name: str, **kwargs) -> IncludeLaunchDescription:
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(get_package_share_directory(pkg), "launch", name)),
        **kwargs)


def generate_launch_description():
    sim = _inc("easyfly_px4_sitl", "px4_sitl.launch.py")

    bridge = TimerAction(period=8.0, actions=[
        # V2-09/11: 桥链与 flight_control/mission_fsm 统一仿真时基,
        # timesync_mode 由此自动取 NONE (仿真钟下 TIMESYNC 会污染时间戳)
        _inc("easyfly_mavlink_bridge", "mavlink_bridge.launch.py",
             launch_arguments={"use_sim_time": "true"}.items())])

    control = TimerAction(period=10.0, actions=[
        _inc("easyfly_flight_control", "flight_control.launch.py"),
        _inc("easyfly_mission_fsm", "mission_fsm.launch.py"),
    ])

    return LaunchDescription([sim, bridge, control])
