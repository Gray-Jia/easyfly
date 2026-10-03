# 包成熟度登记（D0）

登记日期：2026-10-04；发现方式：`colcon list --base-paths src`，共67包。分类依据源码、CMake及当前开发修改；此清单不是功能完成百分比。

“测试源码存在”只表示文件存在，不代表本轮运行。历史动态列来自schedule-v3/question-v2最终记录；本轮仅做离线/组件/相关构建，不做全链动态复验。各项实际结果以schedule-v4为准。

当前类别中仍有29个CMake明确TODO骨架；easyfly_params本轮从配置占位推进到可解析/导出的开发profile工具，不代表D2参数SDK已完成。

| 包 | 当前实现类别 | 组件验证依据 | 历史集成/动态依据 | D0本轮范围 |
|---|---|---|---|---|
| [bspline_opt](../../src/third_party/planners/ego_planner/bspline_opt) | 第三方实现/集成 | 测试源码存在；是否通过另查执行记录 | G8主链 | 未重新执行该包测试/构建 |
| [easyfly_apriltag_detection](../../src/perception/p2_detection/easyfly_apriltag_detection) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_camera_calib](../../src/perception/p1_preprocess/easyfly_camera_calib) | 已有功能实现（按现有边界） | 未发现test*.cpp/py；不推断无全部验证 | G6.1（非完整标定工具） | 未重新执行该包测试/构建 |
| [easyfly_color_line_detection](../../src/perception/p2_detection/easyfly_color_line_detection) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_coord_transform](../../src/perception/p1_preprocess/easyfly_coord_transform) | 已有功能实现（按现有边界） | 未发现test*.cpp/py；不推断无全部验证 | G6.1 | 未重新执行该包测试/构建 |
| [easyfly_core](../../src/application/a1_sdk/easyfly_core) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_demos](../../src/application/a3_mission/easyfly_demos) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
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
| [easyfly_mission_fsm](../../src/execution/e1_state_machine/easyfly_mission_fsm) | 已有功能实现（按现有边界） | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_mission_scripts](../../src/application/a3_mission/easyfly_mission_scripts) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_mission_srvs](../../src/application/a2_services/easyfly_mission_srvs) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_msgs](../../src/easyfly_common/easyfly_msgs) | 消息/服务/动作接口 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_multi_object_tracking](../../src/perception/p3_tracking/easyfly_multi_object_tracking) | 已有功能实现（按现有边界） | 测试源码存在；是否通过另查执行记录 | G6.4 | 未重新执行该包测试/构建 |
| [easyfly_object_detection](../../src/perception/p2_detection/easyfly_object_detection) | 已有功能实现（按现有边界） | 测试源码存在；是否通过另查执行记录 | G6.2 | 未重新执行该包测试/构建 |
| [easyfly_obstacle_avoidance](../../src/execution/e3_control/easyfly_obstacle_avoidance) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_params](../../src/application/a1_sdk/easyfly_params) | D0配置与离线工具 | 测试源码存在；是否通过另查执行记录 | 未逐包签收；无独立动态完成结论 | D0配置行为测试/构建 |
| [easyfly_perception_srvs](../../src/application/a2_services/easyfly_perception_srvs) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_pixel_to_3d](../../src/perception/p4_fusion/easyfly_pixel_to_3d) | 已有功能实现（按现有边界） | 测试源码存在；是否通过另查执行记录 | G6.4 | 未重新执行该包测试/构建 |
| [easyfly_pointcloud_filter](../../src/perception/p1_preprocess/easyfly_pointcloud_filter) | 已有功能实现（按现有边界） | 测试源码存在；是否通过另查执行记录 | G6/G7主链 | 未重新执行该包测试/构建 |
| [easyfly_precision_landing](../../src/execution/e3_control/easyfly_precision_landing) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_px4_sitl](../../src/simulation/easyfly_px4_sitl) | 仿真启动/模型资源 | 测试源码存在；是否通过另查执行记录 | G4/G6-G8组合入口 | D0相关launch/SDF回归/构建 |
| [easyfly_pybind](../../src/application/a1_sdk/easyfly_pybind) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
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
- semantic_map以几何障碍为主；GPS/UDP/Mesh/视频、其余检测/跟踪/融合、SDK/服务/UI骨架仍待相应D批次实现。
- ego_to_mavros为上游示例，不应与EasyFly统一控制出口同时启用。
- realsense2_camera与Livox的代码集成/构建不等于本轮真实设备联调；传感器固件和外参尚未冻结。
- 资源与接口包不以“没有.cpp”判为骨架；生成接口、配置和模型是其真实职责。
- D0profile声明是静态能力元数据，不是运行时健康状态；未实现标签/精准降落保持不可用。
