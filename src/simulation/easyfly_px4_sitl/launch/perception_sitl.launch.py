"""
perception_sitl.launch.py — 阶段三感知调试启动（Gazebo + PX4 + RViz2）

用法:
  ros2 launch easyfly_px4_sitl perception_sitl.launch.py

内容:
  - Gazebo Classic (perception_demo.world: 行人/车辆/纸箱验收场景)
  - PX4 SITL + easyfly_iris (D435i 深度相机 + MID-360)
  - RViz2 (相机图像 / 深度点云可视化)

验证话题:
  /camera/color/image_raw             前视彩色图像 (30 Hz)
  /camera/color/camera_info           彩色相机内参
  /camera/aligned_depth_to_color/image_raw   深度图 (30 Hz)
  /camera/aligned_depth_to_color/points      深度点云 (M0 验收用, M1 后可关)
  /livox/lidar                        MID-360 点云 (livox CustomMsg, 10 Hz)
  /livox/imu                          MID-360 内置 IMU (200 Hz)

PX4 路径按 PX4_DIR > ~/PX4-Autopilot-1.16.2 > ~/PX4-Autopilot-1.16.1
> ~/PX4-Autopilot 解析；不使用模糊版本匹配。
"""

import os
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    GroupAction,
    IncludeLaunchDescription,
    SetEnvironmentVariable,
    TimerAction,
)
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def _resolve_px4_dir():
    """按 PX4_DIR > ~/PX4-Autopilot-1.16.2 > ~/PX4-Autopilot-1.16.1 >
    ~/PX4-Autopilot 选择目录。"""
    env = os.environ.get("PX4_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    for candidate in ("PX4-Autopilot-1.16.2", "PX4-Autopilot-1.16.1",
                      "PX4-Autopilot"):
        default = Path.home() / candidate
        if default.exists():
            return default
    return Path.home() / "PX4-Autopilot"


def generate_launch_description():
    # 默认保持历史交互行为；G6 自动验收可使用 headless:=true，或分别
    # 设置 gzclient:=false rviz:=false debug_image:=false。
    headless_arg = DeclareLaunchArgument(
        "headless", default_value="false",
        description="无界面验收模式：关闭 gzclient、RViz 和 robot_state_publisher")
    gzclient_arg = DeclareLaunchArgument(
        "gzclient", default_value="true",
        description="是否启动 Gazebo GUI（headless=true 时强制关闭）")
    rviz_arg = DeclareLaunchArgument(
        "rviz", default_value="true",
        description="是否启动 RViz2（headless=true 时强制关闭）")
    debug_image_arg = DeclareLaunchArgument(
        "debug_image", default_value="auto",
        description="检测调试图像：auto 跟随 detection.yaml，false 关闭")
    detection_use_gpu_arg = DeclareLaunchArgument(
        "detection_use_gpu", default_value="auto",
        description="检测执行提供者：auto 跟随 YAML，false 强制 CPU，true 请求 CUDA")
    detection_perf_period_arg = DeclareLaunchArgument(
        "detection_performance_log_period_s", default_value="auto",
        description="检测 steady_clock 性能窗口（秒）；auto 跟随 YAML")
    detection_qos_reliability_arg = DeclareLaunchArgument(
        "detection_input_qos_reliability", default_value="auto",
        description="检测输入 QoS：auto 跟随 YAML，或 reliable/best_effort")
    detection_qos_depth_arg = DeclareLaunchArgument(
        "detection_input_qos_depth", default_value="auto",
        description="检测输入 QoS KeepLast 深度：auto 跟随 YAML，范围 1..100")

    pkg_px4_sitl       = get_package_share_directory("easyfly_px4_sitl")
    pkg_gazebo_models  = get_package_share_directory("easyfly_gazebo_models")
    pkg_gazebo_worlds  = get_package_share_directory("easyfly_gazebo_worlds")
    pkg_gazebo_plugins = get_package_share_directory("easyfly_gazebo_plugins")

    px4_dir = _resolve_px4_dir()
    px4_build = str(px4_dir / "build" / "px4_sitl_default")
    px4_bin   = str(px4_dir / "build" / "px4_sitl_default" / "bin" / "px4")

    model_dir  = pkg_px4_sitl + "/models"
    world_file = pkg_gazebo_worlds + "/perception_demo.world"
    model_name = "easyfly_iris"
    model_sdf  = model_dir + "/" + model_name + "/" + model_name + ".sdf"

    px4_models_dir = str(
        px4_dir / "Tools" / "simulation" / "gazebo-classic" /
        "sitl_gazebo-classic" / "models")
    gazebo_model_path = ":".join([
        model_dir,
        pkg_gazebo_models,
        px4_models_dir,
    ])
    gazebo_plugin_dir = str(px4_dir / "build" / "px4_sitl_default" / "build_gazebo-classic")

    set_model_path = SetEnvironmentVariable("GAZEBO_MODEL_PATH", gazebo_model_path)
    # /opt/ros/humble/lib 必须包含: libgazebo_ros_init.so / libgazebo_ros_camera.so 等系统插件
    set_plugin_path = SetEnvironmentVariable(
        "GAZEBO_PLUGIN_PATH",
        gazebo_plugin_dir + ":" + pkg_gazebo_plugins + "/lib:/opt/ros/humble/lib:" + os.environ.get("GAZEBO_PLUGIN_PATH", ""))
    # PX4 gazebo 插件依赖 libmav_msgs.so / libsensor_msgs.so 等, 位于 PX4 build_gazebo-classic
    set_ld_library_path = SetEnvironmentVariable(
        "LD_LIBRARY_PATH",
        gazebo_plugin_dir + ":" + os.environ.get("LD_LIBRARY_PATH", ""))

    # ---- Gazebo + 模型 + PX4 (复用 px4_sitl.launch.py 的启动逻辑, 固定 perception_demo.world) ----
    # -s libgazebo_ros_init.so: 加载 ROS2 时钟插件(SystemPlugin, 发布 /clock), 必须用 -s 方式加载
    gzserver = ExecuteProcess(
        cmd=["gzserver", "--verbose", "-s", "libgazebo_ros_init.so", world_file],
        output="screen",
        name="gzserver",
    )

    spawn_model = ExecuteProcess(
        cmd=[
            "gz", "model",
            "--spawn-file=" + model_sdf,
            "--model-name=" + model_name,
            "-x", "0.0", "-y", "0.0", "-z", "0.83",
        ],
        output="screen",
        name="spawn_model",
    )

    gzclient = ExecuteProcess(
        cmd=["gzclient"],
        output="screen",
        name="gzclient",
        condition=IfCondition(LaunchConfiguration("gzclient")),
    )

    sitl_env = {
        "PX4_SIM_MODEL": "gazebo-classic_iris",
        # 注意: 不要设置 PX4_HOME_LAT/LON — 自定义经纬度(如武汉)与 PX4 SITL 默认
        # home(苏黎世)的磁偏角差异会让 EKF local frame 相对 Gazebo 世界旋转 ~90°,
        # 导致 mavros 位置与 Gazebo/SLAM 坐标系不一致 (M6 踩坑: 航点(x,0)被飞成(0,x))
    }
    sitl_env.update(os.environ)

    px4_sitl = ExecuteProcess(
        cmd=[px4_bin, "-d"],
        cwd=px4_build,
        env=sitl_env,
        output="screen",
        name="px4_sitl",
    )

    # ---- RViz2 感知调试视图 ----
    rviz_config = pkg_px4_sitl + "/rviz/perception.rviz"
    rviz2 = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        arguments=["-d", rviz_config],
        output="screen",
        parameters=[{"use_sim_time": True}],
        condition=IfCondition(LaunchConfiguration("rviz")),
    )

    # ---- URDF 机体可视化: robot_state_publisher (RViz RobotModel 显示飞机) ----
    # iris 是 Gazebo SDF 模型, RViz 不认; 提供 visual-only URDF (easyfly_iris.urdf)
    urdf_file = model_dir + "/" + model_name + "/" + model_name + ".urdf"
    with open(urdf_file, "r") as f:
        robot_desc = f.read()
    robot_state_pub = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        output="screen",
        parameters=[{
            "robot_description": robot_desc,
            "use_sim_time": True,
        }],
        condition=IfCondition(LaunchConfiguration("rviz")),
    )

    # ---- P1 感知预处理 (M1): 静态外参 TF + 内参校验 + odom 动态 TF ----
    calib_tf = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            get_package_share_directory("easyfly_camera_calib") + "/launch/calib_tf.launch.py"))
    coord_tf = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            get_package_share_directory("easyfly_coord_transform") + "/launch/coord_tf.launch.py"))

    # ---- P2 目标检测 (M2): YOLO11 OnnxRuntime GPU ----
    # A headless run must not create the optional debug-image publisher even
    # when the interactive YAML default is true.  Keep explicit debug_image
    # overrides intact for non-headless diagnostics.
    effective_debug_image = PythonExpression([
        "'false' if '", LaunchConfiguration("headless"),
        "'.lower() == 'true' else '", LaunchConfiguration("debug_image"), "'"
    ])
    detection = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            get_package_share_directory("easyfly_object_detection") + "/launch/detection.launch.py"),
        launch_arguments={
            "use_sim_time": "true",
            "publish_debug_image": effective_debug_image,
            "use_gpu": LaunchConfiguration("detection_use_gpu"),
            "performance_log_period_s": LaunchConfiguration(
                "detection_performance_log_period_s"),
            "input_qos_reliability": LaunchConfiguration(
                "detection_input_qos_reliability"),
            "input_qos_depth": LaunchConfiguration("detection_input_qos_depth"),
        }.items())

    # ---- P4 多目标跟踪 (M4): SORT ----
    tracking = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            get_package_share_directory("easyfly_multi_object_tracking") + "/launch/tracking.launch.py"))

    # ---- P5 像素转 3D (M5): 目标世界系定位 ----
    pixel_to_3d = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            get_package_share_directory("easyfly_pixel_to_3d") + "/launch/pixel_to_3d.launch.py"))

    # ---- P3 SLAM (M3): fast_lio + map→odom TF ----
    fastlio_include = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            get_package_share_directory("easyfly_fast_lio_integration") + "/launch/fastlio.launch.py"),
        launch_arguments={
            "use_sim_time": "true",
            "fastlio_config_file": "mid360.yaml",
            # Explicitly clear the legacy alias inside the scoped child.
            "config_file": "",
        }.items())
    fastlio = GroupAction(
        scoped=True,
        forwarding=False,
        launch_configurations={
            "use_sim_time": "true",
            "fastlio_config_file": "mid360.yaml",
            "config_file": "",
        },
        actions=[fastlio_include])

    # ---- C2 通信桥接 (mavros + mavlink_bridge): 提供 /uav_state (P1/P3 依赖) ----
    mavlink_bridge = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            get_package_share_directory("easyfly_mavlink_bridge") + "/launch/mavlink_bridge.launch.py"),
        launch_arguments={"use_sim_time": "true"}.items())

    # ---- E 执行层 (Q26): 飞控 + 任务状态机, 一键可飞 ----
    flight_control = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            get_package_share_directory("easyfly_flight_control") + "/launch/flight_control.launch.py"),
        launch_arguments={"use_sim_time": "true"}.items())
    mission_fsm = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            get_package_share_directory("easyfly_mission_fsm") + "/launch/mission_fsm.launch.py"),
        launch_arguments={"use_sim_time": "true"}.items())

    # ---- M4.0 规划基础设施: 点云滤波 (P1) + 障碍表征 (P4) ----
    pcf = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            get_package_share_directory("easyfly_pointcloud_filter") + "/launch/pcf.launch.py"))
    semantic_map = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            get_package_share_directory("easyfly_semantic_map") + "/launch/semantic_map.launch.py"))

    spawn_delayed = TimerAction(period=3.0, actions=[spawn_model])
    px4_delayed = TimerAction(period=6.0, actions=[px4_sitl])
    gui_only = TimerAction(period=6.0, actions=[gzclient, rviz2, robot_state_pub])
    gui_group = GroupAction(
        condition=UnlessCondition(LaunchConfiguration("headless")),
        actions=[gui_only])
    bridge_delayed = TimerAction(period=8.0, actions=[mavlink_bridge])
    p1_nodes = TimerAction(period=12.0, actions=[calib_tf, coord_tf])
    p2_nodes = TimerAction(period=14.0, actions=[detection, fastlio])
    p4_nodes = TimerAction(period=16.0, actions=[tracking])
    p5_nodes = TimerAction(period=18.0, actions=[pixel_to_3d])
    exec_nodes = TimerAction(period=10.0, actions=[flight_control, mission_fsm])
    # M4.0: 依赖 P1 静态 TF (12s) 与雷达数据, 20s 启动足够稳
    m40_nodes = TimerAction(period=20.0, actions=[pcf, semantic_map])
    # M4.1: 跟随节点 (常驻 idle 无副作用, 经 /track_target action 发起)
    follow = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            get_package_share_directory("easyfly_target_tracking") + "/launch/follow.launch.py"))
    m41_nodes = TimerAction(period=22.0, actions=[follow])
    # M4.2: 全局规划节点 (常驻 idle 无副作用, 经 /navigate action 发起)
    navigate = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            get_package_share_directory("easyfly_global_planner") + "/launch/navigate.launch.py"))
    m42_nodes = TimerAction(period=24.0, actions=[navigate])
    # M4.3: EGO-Planner 局部规划 (ego_planner_node + traj_server)。
    # position_cmd 是飞控指令流；急停恢复使用 traj_server 专用 trajectory_ack。
    local_planner = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            get_package_share_directory("easyfly_local_planner") + "/launch/local_planner.launch.py"))
    m43_nodes = TimerAction(period=26.0, actions=[local_planner])

    return LaunchDescription([
        set_model_path,
        set_plugin_path,
        set_ld_library_path,
        headless_arg,
        gzclient_arg,
        rviz_arg,
        debug_image_arg,
        detection_use_gpu_arg,
        detection_perf_period_arg,
        detection_qos_reliability_arg,
        detection_qos_depth_arg,
        gzserver,
        spawn_delayed,
        px4_delayed,
        gui_group,
        bridge_delayed,
        exec_nodes,
        p1_nodes,
        p2_nodes,
        p4_nodes,
        p5_nodes,
        m40_nodes,
        m41_nodes,
        m42_nodes,
        m43_nodes,
    ])
