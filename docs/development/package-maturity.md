# 包成熟度登记（D0 / D1 / D2 / D3）

登记日期：2026-10-04；发现方式：`colcon list --base-paths src`，共67包。分类依据源码、CMake及当前开发修改；此清单不是功能完成百分比。

“测试源码存在”只表示文件存在，不代表本轮运行。历史动态列来自schedule-v3/question-v2最终记录；D3新增实际节点软件任务链与相关导航软件闭环，不代表PX4/SITL/实机或G9+复验。各项实际结果以schedule-v4为准。

D0登记时有29个CMake明确TODO骨架；D1为28个，D2为24个，D3将mission_scripts模板资源与demos真实示例落地后为22个。easyfly_params提供配置工具及受约束的本地类型化服务，不代理任意飞行参数写入。下表保留D0范围列，增加D1/D2/D3实现事实；新开发实际验证以schedule-v4为准，不按包数计算完成百分比。

| 包 | 当前实现类别 | 组件验证依据 | 历史集成/动态依据 | D0本轮范围 |
|---|---|---|---|---|
| [bspline_opt](../../src/third_party/planners/ego_planner/bspline_opt) | 第三方实现/集成 | 测试源码存在；是否通过另查执行记录 | G8主链 | 未重新执行该包测试/构建 |
| [easyfly_apriltag_detection](../../src/perception/p2_detection/easyfly_apriltag_detection) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_camera_calib](../../src/perception/p1_preprocess/easyfly_camera_calib) | 已有功能实现（按现有边界） | 未发现test*.cpp/py；不推断无全部验证 | G6.1（非完整标定工具） | 未重新执行该包测试/构建 |
| [easyfly_color_line_detection](../../src/perception/p2_detection/easyfly_color_line_detection) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_coord_transform](../../src/perception/p1_preprocess/easyfly_coord_transform) | 已有功能实现（按现有边界） | 未发现test*.cpp/py；不推断无全部验证 | G6.1 | 未重新执行该包测试/构建 |
| [easyfly_core](../../src/application/a1_sdk/easyfly_core) | D2异步SDK；D3新增Search及递归UUID排空 | D3真实ROS 9场景及相关软件plant，见schedule-v4 | 无新增PX4/硬件签收 | D0未构建，D2/D3另有记录 |
| [easyfly_demos](../../src/application/a3_mission/easyfly_demos) | D3安装C++/Python校验与显式执行/取消示例 | D3真实任务链3场景及安装示例 | 软件闭环，不是SITL/实机 | D0未构建，D3另有记录 |
| [easyfly_depth_estimation](../../src/perception/p4_fusion/easyfly_depth_estimation) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_desktop](../../src/easyfly_ui/easyfly_desktop) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_ellipse_detection](../../src/perception/p2_detection/easyfly_ellipse_detection) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_fast_lio_integration](../../src/perception/p3_tracking/easyfly_fast_lio_integration) | SLAM/TF集成 | 测试源码存在；是否通过另查执行记录 | G6.3；V2-18组合启动记录较弱 | 未重新执行该包测试/构建 |
| [easyfly_flight_control](../../src/execution/e3_control/easyfly_flight_control) | 已有功能实现（按现有边界） | 测试源码存在；是否通过另查执行记录 | G5；轨迹链G8 | 未重新执行该包测试/构建 |
| [easyfly_gazebo_models](../../src/simulation/easyfly_gazebo_models) | 模型资源 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_gazebo_plugins](../../src/simulation/easyfly_gazebo_plugins) | 已有功能实现（按现有边界） | 未发现test*.cpp/py；不推断无全部验证 | G6传感器/场景集成 | 未重新执行该包测试/构建 |
| [easyfly_gazebo_worlds](../../src/simulation/easyfly_gazebo_worlds) | 场景资源 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_gimbal_control](../../src/execution/e3_control/easyfly_gimbal_control) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_global_planner](../../src/execution/e2_planning/easyfly_global_planner) | 已有功能实现（按现有边界） | 测试源码存在；是否通过另查执行记录 | G7-N | 未重新执行该包测试/构建 |
| [easyfly_gps_receiver](../../src/communication/c1_drivers/easyfly_gps_receiver) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_landing_detection](../../src/perception/p2_detection/easyfly_landing_detection) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_lidar_camera_fusion](../../src/perception/p4_fusion/easyfly_lidar_camera_fusion) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_local_planner](../../src/execution/e2_planning/easyfly_local_planner) | EGO启动适配 | 未发现test*.cpp/py；不推断无全部验证 | G8 | 未重新执行该包测试/构建 |
| [easyfly_mavlink_bridge](../../src/communication/c2_protocol/easyfly_mavlink_bridge) | 已有功能实现（按现有边界） | 测试源码存在；是否通过另查执行记录 | G4-G5 | 未重新执行该包测试/构建 |
| [easyfly_mesh_comm](../../src/communication/c2_protocol/easyfly_mesh_comm) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_mission_fsm](../../src/execution/e1_state_machine/easyfly_mission_fsm) | D3版本化/旧任务解析、7类顺序步骤与弓字搜索 | D3 6个行为CTest；任务13场景、搜索8场景 | D3真实节点软件任务链；无硬件签收 | D0未构建，D3另有记录 |
| [easyfly_mission_scripts](../../src/application/a3_mission/easyfly_mission_scripts) | D3四类版本化任务模板资源，不复制执行器 | 安装校验与四模板任务链执行 | 软件闭环，不保证真实视觉/绕障场景 | D0未构建，D3另有记录 |
| [easyfly_mission_srvs](../../src/application/a2_services/easyfly_mission_srvs) | D2门面；D3接入正式格式与递归排空 | 行为3 CTest通过、服务9场景；4项lint欠账见schedule-v4 | D3真实任务服务链，不是实机 | D0未构建，D2/D3另有记录 |
| [easyfly_msgs](../../src/easyfly_common/easyfly_msgs) | 消息/服务/动作接口 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_multi_object_tracking](../../src/perception/p3_tracking/easyfly_multi_object_tracking) | 已有功能实现（按现有边界） | 测试源码存在；是否通过另查执行记录 | G6.4 | 未重新执行该包测试/构建 |
| [easyfly_object_detection](../../src/perception/p2_detection/easyfly_object_detection) | 已有功能实现（按现有边界） | 测试源码存在；是否通过另查执行记录 | G6.2 | 未重新执行该包测试/构建 |
| [easyfly_obstacle_avoidance](../../src/execution/e3_control/easyfly_obstacle_avoidance) | D1查询/Goal关联停止监督；不生成轨迹或setpoint | D1真实ROS查询/停止测试通过 | 无实机安全签收；自动监督默认关闭 | D0为骨架；D1构建和组件测试见schedule-v4 |
| [easyfly_params](../../src/application/a1_sdk/easyfly_params) | D0配置与离线工具 | 测试源码存在；是否通过另查执行记录 | 未逐包签收；无独立动态完成结论 | D0配置行为测试/构建 |
| [easyfly_perception_srvs](../../src/application/a2_services/easyfly_perception_srvs) | D2只读目标/障碍快照、有效性与能力服务 | D2查询/范围/空/过期/非法输入回归，见schedule-v4 | 不表示真实感知链本次重新签收 | D0未构建，D2另有记录 |
| [easyfly_pixel_to_3d](../../src/perception/p4_fusion/easyfly_pixel_to_3d) | 已有功能实现（按现有边界） | 测试源码存在；是否通过另查执行记录 | G6.4 | 未重新执行该包测试/构建 |
| [easyfly_pointcloud_filter](../../src/perception/p1_preprocess/easyfly_pointcloud_filter) | 已有功能实现（按现有边界） | 测试源码存在；是否通过另查执行记录 | G6/G7主链 | 未重新执行该包测试/构建 |
| [easyfly_precision_landing](../../src/execution/e3_control/easyfly_precision_landing) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_px4_sitl](../../src/simulation/easyfly_px4_sitl) | 仿真启动/模型资源 | 测试源码存在；是否通过另查执行记录 | G4/G6-G8组合入口 | D0相关launch/SDF回归/构建 |
| [easyfly_pybind](../../src/application/a1_sdk/easyfly_pybind) | D2绑定同一C++SDK，轮询/等待/取消，无独立飞行FSM | D2 Python ROS mock与真实导航软件plant，见schedule-v4 | 不表示SITL/硬件通过 | D0未构建，D2另有记录 |
| [easyfly_rc_receiver](../../src/communication/c1_drivers/easyfly_rc_receiver) | 已有功能实现（按现有边界） | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_semantic_map](../../src/perception/p4_fusion/easyfly_semantic_map) | 已有功能实现（按现有边界） | 测试源码存在；是否通过另查执行记录 | G6.5/G7/G8 | 未重新执行该包测试/构建 |
| [easyfly_serial](../../src/communication/c1_drivers/easyfly_serial) | 已有功能实现（按现有边界） | 测试源码存在；是否通过另查执行记录 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_sim_launcher](../../src/application/a3_mission/easyfly_sim_launcher) | 仿真组合启动 | 测试源码存在；是否通过另查执行记录 | 未逐包签收；无独立动态完成结论 | D0离线launch展开/构建 |
| [easyfly_single_object_tracking](../../src/perception/p3_tracking/easyfly_single_object_tracking) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_swarm_planner](../../src/execution/e2_planning/easyfly_swarm_planner) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_target_prediction](../../src/perception/p3_tracking/easyfly_target_prediction) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_target_tracking](../../src/execution/e3_control/easyfly_target_tracking) | 已有功能实现（按现有边界） | 测试源码存在；是否通过另查执行记录 | G7-F | 未重新执行该包测试/构建 |
| [easyfly_time_sync](../../src/perception/p1_preprocess/easyfly_time_sync) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_trajectory_optimizer](../../src/execution/e2_planning/easyfly_trajectory_optimizer) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_udp_protocol](../../src/communication/c2_protocol/easyfly_udp_protocol) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_ui_bridge](../../src/easyfly_ui/easyfly_ui_bridge) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_utils](../../src/easyfly_common/easyfly_utils) | 头文件工具库 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_vehicle_reid](../../src/perception/p2_detection/easyfly_vehicle_reid) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_video_recorder](../../src/communication/c3_media/easyfly_video_recorder) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_video_streamer](../../src/communication/c3_media/easyfly_video_streamer) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_web](../../src/easyfly_ui/easyfly_web) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [ego_planner](../../src/third_party/planners/ego_planner/plan_manage) | 第三方实现/集成 | 测试源码存在；是否通过另查执行记录 | G8 | D0采样/5个CTests/单包构建 |
| [ego_to_mavros](../../src/third_party/planners/ego_planner/ego_to_mavros) | 第三方实现/集成 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [fast_lio](../../src/third_party/slam/fast_lio) | 第三方实现/集成 | 测试源码存在；是否通过另查执行记录 | G6.3 | 未重新执行该包测试/构建 |
| [librealsense2](../../src/third_party/librealsense) | 第三方实现/集成 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [livox_ros_driver2](../../src/communication/c1_drivers/livox_ros_driver2) | 第三方实现/集成 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [livox_sdk2](../../src/third_party/livox_sdk2) | 第三方实现/集成 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [path_searching](../../src/third_party/planners/ego_planner/path_searching) | 第三方实现/集成 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [plan_env](../../src/third_party/planners/ego_planner/plan_env) | 第三方实现/集成 | 测试源码存在；是否通过另查执行记录 | G8主链 | 未重新执行该包测试/构建 |
| [quadrotor_msgs](../../src/third_party/planners/ego_planner/quadrotor_msgs) | 第三方实现/集成 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [realsense2_camera](../../src/communication/c1_drivers/realsense_ros/realsense2_camera) | 第三方实现/集成 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [realsense2_camera_msgs](../../src/communication/c1_drivers/realsense_ros/realsense2_camera_msgs) | 第三方实现/集成 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [traj_utils](../../src/third_party/planners/ego_planner/traj_utils) | 第三方实现/集成 | 未发现test*.cpp/py；不推断无全部验证 | G8主链 | 未重新执行该包测试/构建 |
| [traj_utils_so](../../src/third_party/planners/ego_planner/traj_utils_so) | 第三方实现/集成 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |

## 特别边界

- easyfly_rc_receiver是MAVROS RC通道转发，非直连SBUS驱动；easyfly_serial是库，不能推断所有设备协议可用。
- semantic_map以几何障碍为主；GPS/UDP/Mesh/视频、其余检测/跟踪/融合及UI骨架仍待相应D批次实现。D3已实现第一版顺序任务、弓字搜索与模板；分支/重试、其他搜索模式和实机联调仍不在其交付范围。
- ego_to_mavros为上游示例，不应与EasyFly统一控制出口同时启用。
- realsense2_camera与Livox的代码集成/构建不等于本轮真实设备联调；传感器固件和外参尚未冻结。
- 资源与接口包不以“没有.cpp”判为骨架；生成接口、配置和模型是其真实职责。
- D0profile声明是静态能力元数据，不是运行时健康状态；未实现标签/精准降落保持不可用。
