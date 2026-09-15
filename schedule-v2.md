# EasyFly 当前工作盘点与暂停期计划

> 盘点日期：2026-09-15
> 整理起点：master / 94c70cd 加 P0 工作树改动
> 本文依据当前源码、Git 历史、现有测试脚本和 2026-09-14 的 P0 审查结果整理。旧版 schedule.md、question.md 和过程文档仅作为历史证据，不再直接代表当前验收状态。

## 1. 当前结论

EasyFly 已经形成可运行的 ROS 2 无人机平台主链，通信、仿真、基础感知、任务控制、目标跟随、A* 全局规划以及 EGO 局部规划接入均已有代码。但是项目目前不适合继续叠加功能，原因不是目录架构需要推倒重来，而是：

1. 当前工作树包含一批尚未提交的 P0 安全修复，基线还没有冻结。
2. 大量“完成”结论来自此前某次仿真，尚未在同一个干净版本、同一套环境中重新连续验收。
3. 完整 EGO/PX4 SITL 被 PX4 的 Attitude failure (roll) 和 failsafe 阻塞。
4. 全量构建仍受 librealsense2 联网 FetchContent 影响。
5. 外部源码的版本来源不完整，FAST-LIO、EGO-Planner、Livox SDK2 缺少可追溯的上游 tag/commit。
6. 历史测试结果中功能单测通过，但 lint 存在大量失败，不能继续用“colcon 全绿”概括。

因此项目从现在进入“暂停功能开发、重新测试验收、冻结可复现基线”阶段。

## 2. 状态定义

| 状态 | 含义 |
|---|---|
| A：本轮已复验 | 当前工作树上已有近期构建、测试和 Review 证据 |
| B：已有实现，待重验 | 代码存在，历史上通过过，但尚未在冻结基线上重新验收 |
| C：部分完成或受阻 | 主体代码存在，但验收不完整或存在明确阻塞 |
| D：仅骨架 | 基本只有 package.xml、CMakeLists.txt、配置或占位目录，没有业务实现 |
| E：未开始 | 规划中的功能尚未进入有效实现 |

“已有实现”不等于“可上实机”；只有完成 test-v2.md 中对应门禁后，才能升级为已验收。

## 3. 当前基线状态

| 项目 | 当前状态 |
|---|---|
| Git 分支与提交 | master / 94c70cd |
| 工作树 | dirty；P0 修改尚未提交 |
| ROS 包数量 | colcon 当前识别 67 个包，包含 EasyFly 包和第三方包 |
| EasyFly 接口 | 13 msg、6 srv、8 action |
| RealSense 嵌套仓库 | 由 4.56.4 上新增本地提交 d69f05c1；根仓库缺少 .gitmodules，需补远程可获取方案 |
| 当前最高可信结论 | P0 代码及组件级验收通过；完整飞行链未通过 |
| 放飞结论 | 当前禁止据此直接实机放飞 |

当前未提交 P0 修改主要涉及：

- UAVState/UAVCommand 与 Action 接口契约；
- MAVLink Bridge 遥测有效性、命令校验、watchdog 和并发快照；
- FlightController Action 状态机、轨迹首帧、轨迹 ID、取消和降落事务；
- MissionFSM 并发、worker 生命周期、电池失效处理；
- EGO traj_server 时钟、轨迹输入和时间跳变保护；
- PixelTo3D、局部规划 launch、测试脚本和清理脚本。

详细整改内容见 codex-P0.md。

## 4. 已完成且本轮已有证据的工作

### 4.1 P0 控制与轨迹安全整改 — A

已完成：

- 局部控制契约统一为 odom、ENU、Z-Up 和 ROS time。
- UAVState 增加 pose、velocity、attitude、battery、GPS 有效性。
- MAVLink Bridge 对 UAVCommand 做 frame、时间戳、有限值和推力范围校验。
- Bridge 的遥测与命令分别使用短锁快照，DDS publish 在锁外执行。
- MissionStatus 只由 MissionFSM 发布。
- FlightController 使用单 Goal reservation，补齐所有已接受 Action 的终态。
- Takeoff、Land、Waypoint、FollowTrajectory 的取消、超时和接管语义收敛。
- Land 的 AUTO.LAND 与取消恢复 OFFBOARD 事务串行化，准备阶段持续悬停。
- FollowTrajectory 等待首条合法新轨迹时保持原悬停点。
- 轨迹 ID 使用接单时水位绑定；旧 ID、旧时间帧和 ACTIVE 回退 ID 被拒绝。
- EGO traj_server 使用节点 ROS clock，校验 B-spline 并防御时间跳变。

本轮证据：

- easyfly_msgs、easyfly_mavlink_bridge、easyfly_flight_control、easyfly_mission_fsm、easyfly_pixel_to_3d 构建通过。
- EGO traj_server 单目标构建通过。
- easyfly_msgs 测试结果为 5 项、0 失败。
- p0_flight_controller_mock.py 共 14 项断言全部通过。
- Python 语法检查和 git diff --check 通过。
- easyfly_reviewer 最终结论：没有残留 P0/P1 阻塞项。

验收边界：这里只证明接口、状态机和组件行为；没有证明当前 SITL 或实机飞行稳定。

### 4.2 已有基础架构 — B

- 四层十三子层目录结构已建立。
- easyfly_msgs 和 easyfly_utils 已建立。
- 仿真模型、world、Gazebo 插件、PX4 SITL 启动入口已存在。
- easyfly_serial、easyfly_rc_receiver、easyfly_mavlink_bridge 已有实现。
- Livox ROS 驱动、RealSense ROS 驱动和底层 SDK 已放入工作区。

这些内容需要在新的隔离构建目录中重新构建和冒烟，不沿用旧 build/install 目录作为通过证据。

## 5. 已有实现但必须重新验收的工作

### 5.1 感知链 M0-M6 — B

当前已有代码：

- Gazebo 深度相机与 Livox/MID-360 仿真；
- camera_calib 和静态 TF；
- coord_transform 的 odom→base_link 与 /odom；
- YOLO11 ONNX 目标检测；
- FAST-LIO 与 map→odom 集成；
- SORT 多目标跟踪和世界坐标 ID consolidation；
- pixel_to_3d 与目标 Marker；
- pointcloud_filter；
- semantic_map、障碍物服务和 occupancy_grid。

历史记录包含检测性能、SLAM 漂移、目标定位误差等数据，但这些数据均应视为“历史基准”，需要按 test-v2.md 在冻结版本上重新采集。

重点重验项：

- TF 树、时间戳和 QoS；
- RealSense/Livox 实际驱动与仿真话题是否仍一致；
- ONNX Runtime CUDA EP 是否真正启用，而不是静默回退 CPU；
- FAST-LIO 静止初始化、点云频率和 map→odom 连续性；
- 跟踪 ID 稳定性和深度同步；
- pixel_to_3d 的 frame 已从 map 默认值改为 odom 后，全链消费者是否一致。

### 5.2 目标跟随 M4.1 — B

easyfly_target_tracking 已实现 TrackTarget Action、目标重捕获、跳变保护、断流检测、接管传播和高度限制。历史 F1-F5 曾通过，但当前脚本和注释存在语义漂移：

- 文件头仍描述 F5 为 RTL 接管；
- 当前实现实际检查用户取消后 CANCELED 和悬停。

验收前必须先冻结 F1-F5 的正式定义，再执行，不能只看脚本退出码。

### 5.3 全局规划 M4.2 — B

easyfly_global_planner 已实现：

- 2D A*、8 连通和禁止穿角；
- 起点脱困；
- LOS 路径简化；
- NavigateTo Action；
- 分段 GoToWaypoint 执行、取消和接管传播。

历史 N1-N5 曾通过，A* gtest 8/8 也有记录。需要在新构建目录中重跑单测和 SITL 导航验收。

## 6. 部分完成或受阻的工作

### 6.1 EGO-Planner M4.3 — C

已经完成：

- FAST-LIO 和 EGO 第三方源码归档到 third_party；
- EGO 相关 8 个 ROS 包已可被 colcon 识别；
- easyfly_local_planner launch 已接入点云、里程计、EGO planner 和 traj_server；
- UAVCommand TRAJECTORY 编码与 FollowTrajectory Action 已实现；
- 合成 PositionCommand 的组件级安全测试已通过；
- EGO 数据链历史上出现过 planning/bspline 和 /position_cmd。

仍未完成：

- T9a 真实 SITL 轨迹到达未通过；
- E1-E4 EGO 验收没有取得同一会话全绿；
- 完整 EGO 动态避障效果未可靠量化；
- 通用地面处理仍使用 ground_height 经验值规避，不能直接泛化到实机或起伏地形；
- NavigateTo→EGO 的统一导航入口尚未完成。

当前阻塞：PX4/Gazebo 会话在进入 EGO 轨迹前出现 Attitude failure (roll)、time jump 或 failsafe。该问题需要先按 test-v2.md 的最小 SITL 隔离流程定位。

### 6.2 全量构建 — C

受影响组件可以构建，但完整 colcon build 尚不能标记通过：

- librealsense2 会尝试通过 FetchContent 获取 curl，历史上长时间阻塞；
- install/librealsense2 当前不存在；
- 现有 build/install 包含多轮旧产物，不能证明干净构建可复现；
- 当前 test-result 是跨多轮运行积累的旧结果：共 131 项、84 项失败；当前可见失败主要来自 lint。它不是一次干净基线测试，功能 gtest 与 lint 必须分开重新统计。

### 6.3 第三方版本可追溯性 — C

已能确认二进制或源码版本的组件见 test-v2.md。以下源码没有保存独立上游 commit/tag：

- FAST-LIO；
- EGO-Planner ROS 2 移植；
- Livox SDK2；
- 部分仿真插件移植。

这些目录属于 EasyFly 主仓库的一部分，git describe 只能返回主仓库提交，不能代表上游版本。

## 7. 仅有骨架或尚未形成可验收功能

### 7.1 通信与媒体 — D

- easyfly_gps_receiver
- easyfly_udp_protocol
- easyfly_mesh_comm
- easyfly_video_streamer
- easyfly_video_recorder

### 7.2 感知扩展 — D

- easyfly_landing_detection
- easyfly_apriltag_detection
- easyfly_ellipse_detection
- easyfly_color_line_detection
- easyfly_vehicle_reid
- easyfly_single_object_tracking
- easyfly_target_prediction
- easyfly_lidar_camera_fusion
- easyfly_depth_estimation
- easyfly_time_sync

### 7.3 规划与控制扩展 — D

- easyfly_swarm_planner
- easyfly_trajectory_optimizer
- easyfly_obstacle_avoidance
- easyfly_gimbal_control
- easyfly_precision_landing

easyfly_local_planner 不是完整自研规划器；它目前主要是 EGO 的适配和启动层，应与第三方 EGO 一起验收。

### 7.4 应用层与 UI — D

- easyfly_core
- easyfly_params
- easyfly_pybind
- easyfly_mission_srvs
- easyfly_perception_srvs
- easyfly_mission_scripts
- easyfly_demos
- easyfly_ui_bridge
- easyfly_desktop
- easyfly_web

easyfly_sim_launcher 有启动骨架，但不能据此认为应用层 SDK 已完成。

## 8. 明确未完成的里程碑

1. 冻结并提交当前 P0 基线。
2. 从零构建全部必需包，并解决或隔离 librealsense2 的联网构建。
3. 清零功能相关测试失败，并单独建立 lint 债务清单。
4. 定位 PX4 Attitude failure (roll) 的根因。
5. 取得控制 T1-T9 同一冻结基线全绿。
6. 取得感知链 M0-M6 的可重复验收数据。
7. 取得跟随 F1-F5、导航 N1-N5 和 EGO E1-E4 的连续全绿。
8. 建立 EGO 通用地面处理和动态障碍直接测量方法。
9. 完成 NavigateTo→EGO、reactive avoidance 和轨迹优化策略整合。
10. 完成精确降落、应用 SDK、服务层、任务脚本、UI 和媒体。
11. 完成真实传感器台架、HIL 和受控实机飞行验收。

## 9. 暂停期执行顺序

暂停期只允许做“记录、修复阻塞验收的问题、补测试、提升可复现性”，不新增业务功能。

建议严格按以下顺序：

1. 保存当前 Git 状态、依赖版本和 P0 diff，建立不可变基线编号。
2. 使用独立 build-v2/install-v2/log-v2 目录做分层构建。
3. 运行接口检查、纯逻辑单测和 P0 mock，不启动飞行仿真。
4. 启动最小 PX4/Gazebo/MAVROS/Bridge 链，先定位姿态故障。
5. 通过最小控制 T1-T9。
6. 逐段恢复传感器、TF、检测、SLAM、跟踪和 3D 融合。
7. 依次运行 F1-F5、N1-N5、E1-E4。
8. 做 30 分钟以上稳定性和重复启停测试。
9. 完成台架/HIL 后，才讨论低风险实机飞行。

每一级失败都应停在该级定位，不允许通过重跑整套全链掩盖不稳定问题。

## 10. 下一次恢复开发的准入条件

满足以下条件后，才建议恢复 M4.4 或其他新功能：

- 当前 P0 diff 已审查、提交并有明确 tag 或 commit；
- 关键外部依赖版本已冻结；
- 干净构建可重复；
- P0 mock、功能单测、T1-T9 全绿；
- F1-F5、N1-N5、E1-E4 至少连续两轮全绿；
- PX4 姿态故障有根因和可复现解决方案；
- 测试报告包含日志、版本、配置、起止时间和失败分类；
- 没有未解释的飞行 failsafe、坐标跳变或 Action 悬挂。

在这些条件满足前，当前项目状态应标记为：

**功能覆盖较广，但仍处于重新基线化和系统验收阶段。**
