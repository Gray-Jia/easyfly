# 包成熟度登记（D0 / D1 / D2 / D3 / D4）

登记日期：2026-10-04，D4续批更新2026-10-05；发现方式：`colcon list --base-paths src`，共67包。分类依据源码、CMake及当前开发修改；此清单不是功能完成百分比。

“测试源码存在”只表示文件存在，不代表本轮运行。历史动态列来自schedule-v3/question-v2最终记录；D3新增实际节点软件任务链与相关导航软件闭环，不代表PX4/SITL/实机或G9+复验。各项实际结果以schedule-v4为准。

D0登记时有29个CMake明确TODO骨架；D1为28个，D2为24个，D3为22个，D4七方向第一版落地后为16个。类别副本属于已有semantic_map包的独立节点，不改变其原几何地图。easyfly_params提供配置工具及受约束的本地类型化服务，不代理任意飞行参数写入。下表保留D0范围列，增加D1–D4实现事实；新开发实际验证以schedule-v4为准，不按包数计算完成百分比。

| 包 | 当前实现类别 | 组件验证依据 | 历史集成/动态依据 | D0本轮范围 |
|---|---|---|---|---|
| [bspline_opt](../../src/third_party/planners/ego_planner/bspline_opt) | 第三方实现/集成 | 测试源码存在；是否通过另查执行记录 | G8主链 | 未重新执行该包测试/构建 |
| [easyfly_apriltag_detection](../../src/perception/p2_detection/easyfly_apriltag_detection) | D4独立36h11/IPPE位姿及歧义拒绝、显式尺寸 | 纯几何/字典、真实图像节点与Clock回归；见schedule-v4 | 合成标定图，不是实际相机精度/飞行签收 | D0骨架，D4另有记录 |
| [easyfly_camera_calib](../../src/perception/p1_preprocess/easyfly_camera_calib) | D4首批整份外参/内参加载校验、持续CameraInfo诊断 | 3纯校验组+3真实ROS场景通过 | G6.1历史；本批非在线标定求解/实机签收 | D0未构建，D4另有记录 |
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
| [easyfly_gimbal_control](../../src/execution/e3_control/easyfly_gimbal_control) | D5模拟设备、受限角度/速率、显式目标跟踪 | 19模型＋2真实ROS进程回归，含失联/退出；见schedule-v4第11节 | 无真实设备协议/实机验收；不参与相机外参/飞机控制 | D0骨架；D5另有实际构建/组件证据 |
| [easyfly_global_planner](../../src/execution/e2_planning/easyfly_global_planner) | 已有功能实现（按现有边界） | 测试源码存在；是否通过另查执行记录 | G7-N | 未重新执行该包测试/构建 |
| [easyfly_gps_receiver](../../src/communication/c1_drivers/easyfly_gps_receiver) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_landing_detection](../../src/perception/p2_detection/easyfly_landing_detection) | D4显式标签ID的独立降落感知适配 | 真实ROS选择/失效与Clock回归；见schedule-v4 | 光学Z非离地高度，不含D5降落控制 | D0骨架，D4另有记录 |
| [easyfly_lidar_camera_fusion](../../src/perception/p4_fusion/easyfly_lidar_camera_fusion) | D4双源时间TF/Z-buffer独立着色云/稀疏深度 | 4纯投影、排队失效隔离、3真实ROS及共享Clock回归 | 无真实雷视安全签收，不接地图/飞行 | D0骨架，D4另有记录 |
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
| [easyfly_perception_srvs](../../src/application/a2_services/easyfly_perception_srvs) | D2目标/障碍只读查询；D4降落感知能力动态状态 | 查询、landing正负/年龄及Clock回归；见schedule-v4 | 不表示精准降落动作或飞行签收 | D0未构建，D2/D4另有记录 |
| [easyfly_pixel_to_3d](../../src/perception/p4_fusion/easyfly_pixel_to_3d) | 已有功能实现（按现有边界） | 测试源码存在；是否通过另查执行记录 | G6.4 | 未重新执行该包测试/构建 |
| [easyfly_pointcloud_filter](../../src/perception/p1_preprocess/easyfly_pointcloud_filter) | 已有功能实现（按现有边界） | 测试源码存在；是否通过另查执行记录 | G6/G7主链 | 未重新执行该包测试/构建 |
| [easyfly_precision_landing](../../src/execution/e3_control/easyfly_precision_landing) | D5固定外参转换/纯策略/启动门面；Action在现有飞控 | 组件/生命周期/SDK回归及SITL23正式任务完整链通过；见schedule-v4第11节 | 限定0.2m静止板、30Hz、显式DDS与.6/.5m；无实机/移动板/动态外参/长期验收 | D0骨架；D5另有实际构建/组件/短时仿真证据 |
| [easyfly_px4_sitl](../../src/simulation/easyfly_px4_sitl) | 仿真启动/模型资源 | 测试源码存在；是否通过另查执行记录 | G4/G6-G8组合入口 | D0相关launch/SDF回归/构建 |
| [easyfly_pybind](../../src/application/a1_sdk/easyfly_pybind) | D2绑定同一C++SDK，轮询/等待/取消，无独立飞行FSM | D2 Python ROS mock与真实导航软件plant，见schedule-v4 | 不表示SITL/硬件通过 | D0未构建，D2另有记录 |
| [easyfly_rc_receiver](../../src/communication/c1_drivers/easyfly_rc_receiver) | 已有功能实现（按现有边界） | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_semantic_map](../../src/perception/p4_fusion/easyfly_semantic_map) | 原几何地图不改；D4独立障碍类别副本节点 | 原地图4核心回归、分类4纯+2ROS及共享Clock回归 | G6.5/G7/G8历史；新副本不接占据 | D0未构建，D4另有记录 |
| [easyfly_serial](../../src/communication/c1_drivers/easyfly_serial) | 已有功能实现（按现有边界） | 测试源码存在；是否通过另查执行记录 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_sim_launcher](../../src/application/a3_mission/easyfly_sim_launcher) | 仿真组合启动 | 测试源码存在；是否通过另查执行记录 | 未逐包签收；无独立动态完成结论 | D0离线launch展开/构建 |
| [easyfly_single_object_tracking](../../src/perception/p3_tracking/easyfly_single_object_tracking) | D4独立CSRT/显式ROI、丢失与新身份状态 | 纹理平移核心、真实ROS ROI/竞争及Clock回归 | 输出类型可显式接3D链，未做真实跟随签收 | D0骨架，D4另有记录 |
| [easyfly_swarm_planner](../../src/execution/e2_planning/easyfly_swarm_planner) | 构建骨架，无功能目标 | 未发现test*.cpp/py；不推断无全部验证 | 未逐包签收；无独立动态完成结论 | 未重新执行该包测试/构建 |
| [easyfly_target_prediction](../../src/perception/p3_tracking/easyfly_target_prediction) | D4首批独立有界恒速模型，不接飞行/地图 | 7纯核心单测+5真实ROS场景通过 | 非实际跟随联调/统计校准模型 | D0未构建，D4另有记录 |
| [easyfly_target_tracking](../../src/execution/e3_control/easyfly_target_tracking) | 已有功能实现（按现有边界） | 测试源码存在；是否通过另查执行记录 | G7-F | 未重新执行该包测试/构建 |
| [easyfly_time_sync](../../src/perception/p1_preprocess/easyfly_time_sync) | D4首批软件图像时间配对与丢弃计数，原stamp保留 | 5纯核心单测+3真实ROS场景通过 | 非硬件同步/空间配准 | D0未构建，D4另有记录 |
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
- D0profile声明是静态能力元数据，不是运行时健康状态；D4标签/降落感知需显式尺寸/ID及有效输入，既有profile不自动开启；精准降落控制仍未实现。
