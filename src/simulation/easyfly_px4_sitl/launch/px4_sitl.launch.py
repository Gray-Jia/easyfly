"""
px4_sitl.launch.py — 启动 Gazebo Classic + PX4 SITL

用法:
  ros2 launch easyfly_px4_sitl px4_sitl.launch.py

架构:
  gzserver (empty.world)  →  gz model spawn (easyfly_iris)
  gzclient (GUI)
  px4 (simulator_mavlink ↔ Gazebo mavlink_interface plugin via TCP 4560)

环境要求:
  - PX4-Autopilot 已编译
  - Gazebo Classic 11 已安装 (gzserver / gzclient)
"""

import os
import signal
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    ExecuteProcess,
    RegisterEventHandler,
    SetEnvironmentVariable,
    TimerAction,
)
from launch.event_handlers import OnProcessExit


def generate_launch_description():
    # ---- 路径 ----
    pkg_px4_sitl      = get_package_share_directory("easyfly_px4_sitl")
    pkg_gazebo_models = get_package_share_directory("easyfly_gazebo_models")
    pkg_gazebo_worlds = get_package_share_directory("easyfly_gazebo_worlds")

    px4_dir     = Path.home() / "PX4-Autopilot"
    px4_build   = str(px4_dir / "build" / "px4_sitl_default")
    px4_bin     = str(px4_dir / "build" / "px4_sitl_default" / "bin" / "px4")

    model_dir   = pkg_px4_sitl + "/models"
    world_file  = pkg_gazebo_worlds + "/empty.world"
    model_name  = "easyfly_iris"
    model_sdf   = model_dir + "/" + model_name + "/" + model_name + ".sdf"

    # ---- GAZEBO_MODEL_PATH ----
    px4_models_dir = str(
        px4_dir / "Tools" / "simulation" / "gazebo-classic" /
        "sitl_gazebo-classic" / "models")
    gazebo_model_path = ":".join([
        model_dir,
        pkg_gazebo_models,
        px4_models_dir,
    ])

    # ---- 插件路径 ----
    gazebo_plugin_dir = str(px4_dir / "build" / "px4_sitl_default" / "build_gazebo-classic")

    # ---- 1. Gazebo 环境变量 ----
    set_model_path = SetEnvironmentVariable(
        "GAZEBO_MODEL_PATH", gazebo_model_path)
    set_plugin_path = SetEnvironmentVariable(
        "GAZEBO_PLUGIN_PATH",
        gazebo_plugin_dir + ":" + os.environ.get("GAZEBO_PLUGIN_PATH", ""))
    set_ld_path = SetEnvironmentVariable(
        "LD_LIBRARY_PATH",
        gazebo_plugin_dir + ":" + os.environ.get("LD_LIBRARY_PATH", ""))

    # ---- 2. gzserver ----
    gzserver = ExecuteProcess(
        cmd=["gzserver", "--verbose", world_file],
        output="screen",
        name="gzserver",
    )

    # ---- 3. 生成 SDF 并生成模型（使用 spawn_model 风格） ----
    # 注意：这里直接用已编译的 SDF，不需要 jinja 模板生成
    spawn_model = ExecuteProcess(
        cmd=[
            "gz", "model",
            "--spawn-file=" + model_sdf,
            "--model-name=" + model_name,
            "-x", "0.0",
            "-y", "0.0",
            "-z", "0.83",
        ],
        output="screen",
        name="spawn_model",
    )

    # ---- 4. gzclient（GUI） ----
    gzclient = ExecuteProcess(
        cmd=["gzclient"],
        output="screen",
        name="gzclient",
    )

    # ---- 5. PX4 SITL ----
    # 使用 SYS_AUTOSTART=10015（gazebo-classic iris），
    # simulator_mavlink 通过 TCP 4560 与 Gazebo mavlink 插件通信
    sitl_env = {
        "PX4_SIM_MODEL": "gazebo-classic_iris",   # PX4 standard airframe (10015_gazebo-classic_iris)
        "PX4_HOME_LAT":  "30.5123",
        "PX4_HOME_LON":  "114.4218",
        "PX4_HOME_ALT":  "50.0",
    }
    # 继承当前环境
    sitl_env.update(os.environ)

    px4_sitl = ExecuteProcess(
        cmd=[px4_bin, "-d"],
        cwd=px4_build,
        env=sitl_env,
        output="screen",
        name="px4_sitl",
    )

    # ---- 启动顺序 ----
    # gzserver 先启动 → 3s 后 spawn 模型 → 再 3s 后 gzclient + px4
    spawn_delayed = TimerAction(
        period=3.0,
        actions=[spawn_model],
    )

    gui_and_px4 = TimerAction(
        period=6.0,
        actions=[gzclient, px4_sitl],
    )

    return LaunchDescription([
        set_model_path,
        set_plugin_path,
        set_ld_path,
        gzserver,
        spawn_delayed,
        gui_and_px4,
    ])
