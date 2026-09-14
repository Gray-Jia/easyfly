"""
local_planner.launch.py — easyfly_local_planner: EGO-Planner 适配启动 (M4.3)

用途: 把 third_party EGO-Planner 接入 easyfly 数据链, 只起规划所需的两个节点,
      绕开上游 single_run_in_sim.launch.py 的 map_generator / pcl_render_node / rviz。

数据接线 (无 drone_id 前缀, 显式 remap):
  grid_map/cloud  <- /pointcloud_filtered   (P1 点云, 已变换到 odom 世界系)
  grid_map/odom   <- /odom                  (P1 coord_transform 由 /uav_state 生成)
  odom_world      <- /odom                  (EGO FSM 自身状态反馈)
  planning/bspline: 内部话题 (ego_planner_node -> traj_server), 保持默认名
  /position_cmd   : traj_server 输出 (quadrotor_msgs/PositionCommand), 默认即此名

坐标系: EGO grid_map 对点云做零变换 (plan_env/grid_map.cpp cloudCallback 直接用原始
        xyz), 故点云必须已在 odom 系 —— 见 easyfly_pointcloud_filter 的 output_frame。

参数来源: 上游 plan_manage/launch/advanced_param.launch.py (内联), 按 MID-360 重调:
  obstacles_inflation 0.099->0.35 / max_ray_length 4.5->20 / local_update_range 5.5->15
  use_depth_filter True->False (否则点云被 depth_filter_maxdist=5.0 裁到 5m)

注意 (任务书侦察勘误): ego_replan_fsm.h 中 MANUAL_TARGET=1, PRESET_TARGET=2
  (任务书写的 "2=MANUAL_TARGET" 有误)。默认 flight_type=1 → 订 /move_base_simple/goal。

用法:
  ros2 launch easyfly_local_planner local_planner.launch.py
  # 之后 RViz 用 "2D Goal Pose" 发 /move_base_simple/goal; EGO 航线高度硬编码 1.0m
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    use_sim_time = LaunchConfiguration('use_sim_time')
    # flight_type: 1=MANUAL_TARGET(/move_base_simple/goal) 2=PRESET_TARGET(waypoint 列表)
    flight_type = LaunchConfiguration('flight_type')

    declare_sim = DeclareLaunchArgument('use_sim_time', default_value='true')
    declare_ft = DeclareLaunchArgument(
        'flight_type', default_value='1',
        description='1=MANUAL_TARGET(默认, 订 /move_base_simple/goal) 2=PRESET_TARGET')

    ego_params = {
        'use_sim_time': use_sim_time,
        # ---- FSM ----
        'fsm/flight_type': flight_type,
        'fsm/thresh_replan_time': 1.0,
        'fsm/thresh_no_replan_meter': 1.0,
        'fsm/planning_horizon': 7.5,
        'fsm/planning_horizen_time': 3.0,
        'fsm/emergency_time': 1.0,
        'fsm/realworld_experiment': False,   # False => have_trigger_ 初始 true, 无需 /traj_start_trigger
        'fsm/fail_safe': True,
        'fsm/waypoint_num': 0,               # MANUAL_TARGET 模式不用 waypoint 列表
        # ---- grid_map (按 MID-360 重调) ----
        'grid_map/resolution': 0.1,
        'grid_map/map_size_x': 50.0,
        'grid_map/map_size_y': 25.0,
        'grid_map/map_size_z': 3.0,
        'grid_map/local_update_range_x': 8.0,
        'grid_map/local_update_range_y': 8.0,
        'grid_map/local_update_range_z': 3.0,
        'grid_map/obstacles_inflation': 0.35,
        'grid_map/local_map_margin': 10,
        # 地面在 odom 系的高度每会话不同 (-0.98 ~ -0.06, schedule.md M4.0 踩坑), 而 EGO
        # 的 grid_map 无地面剔除 (cloudCallback 把图内所有点膨胀为障碍)。取高于地面带的值
        # 让地面回波落到图外被忽略 —— 否则 (a) 地面成为"地板"障碍, (b) 大量地面点 raycast
        # 拖垮 CPU 引发 RTF 崩/EKF 退化 (实测两次飞行中 time jump + attitude failsafe)。
        # 地面带最高 -0.06 → 取 0.5; 机体飞行高度 ~1.0-1.5 (odom) 仍在地图 [0.5,3.5] 内。
        'grid_map/ground_height': 0.5,
        'grid_map/cx': 321.04638671875,
        'grid_map/cy': 243.44969177246094,
        'grid_map/fx': 387.229248046875,
        'grid_map/fy': 387.229248046875,
        'grid_map/use_depth_filter': False,  # 关键: True 会把点云裁到 depth_filter_maxdist=5m
        'grid_map/depth_filter_tolerance': 0.15,
        'grid_map/depth_filter_maxdist': 5.0,
        'grid_map/depth_filter_mindist': 0.2,
        'grid_map/depth_filter_margin': 2,
        'grid_map/k_depth_scaling_factor': 1000.0,
        'grid_map/skip_pixel': 2,
        'grid_map/p_hit': 0.65,
        'grid_map/p_miss': 0.35,
        'grid_map/p_min': 0.12,
        'grid_map/p_max': 0.90,
        'grid_map/p_occ': 0.80,
        'grid_map/min_ray_length': 0.1,
        'grid_map/max_ray_length': 10.0,
        'grid_map/virtual_ceil_height': 3.2,
        'grid_map/visualization_truncate_height': 3.0,
        'grid_map/show_occ_time': False,
        'grid_map/pose_type': 1,
        'grid_map/frame_id': 'odom',
        # ---- manager / optimization ----
        'manager/max_vel': 2.0,
        'manager/max_acc': 6.0,
        'manager/max_jerk': 4.0,
        'manager/control_points_distance': 0.4,
        'manager/feasibility_tolerance': 0.05,
        'manager/planning_horizon': 7.5,
        'manager/use_distinctive_trajs': True,
        'manager/drone_id': 0,
        'optimization/lambda_smooth': 1.0,
        'optimization/lambda_collision': 0.5,
        'optimization/lambda_feasibility': 0.1,
        'optimization/lambda_fitness': 1.0,
        'optimization/dist0': 0.5,
        'optimization/swarm_clearance': 0.5,
        'optimization/max_vel': 2.0,
        'optimization/max_acc': 6.0,
        'bspline/limit_vel': 2.0,
        'bspline/limit_acc': 6.0,
        'bspline/limit_ratio': 1.1,
        'prediction/obj_num': 10,
        'prediction/lambda': 1.0,
        'prediction/predict_rate': 1.0,
    }

    ego_node = Node(
        package='ego_planner',
        executable='ego_planner_node',
        name='ego_planner_node',
        output='screen',
        parameters=[ego_params],
        remappings=[
            ('grid_map/cloud', '/pointcloud_filtered'),
            ('grid_map/odom', '/odom'),
            ('odom_world', '/odom'),
            ('planning/bspline', '/planning/bspline'),
            ('planning/data_display', '/planning/data_display'),
            ('grid_map/occupancy_inflate', '/grid_map/occupancy_inflate'),
        ],
    )

    traj_node = Node(
        package='ego_planner',
        executable='traj_server',
        name='traj_server',
        output='screen',
        parameters=[{'use_sim_time': use_sim_time}],
        remappings=[
            ('planning/bspline', '/planning/bspline'),
            # position_cmd 默认即 /position_cmd (traj_server.cpp 用绝对名)
        ],
    )

    return LaunchDescription([declare_sim, declare_ft, ego_node, traj_node])
