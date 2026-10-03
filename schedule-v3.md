# EasyFly 项目交接说明与当前进度（schedule-v3）

> 更新日期：2026-10-04
>
> 交接范围：`/home/jia/easyfly_ws` 当前 Git 工作树
>
> 功能基线：`0724742`（G8 / V2-19 收口提交）
>
> 交接提交：以包含本文件的提交为准，可执行 `git show --stat HEAD` 确认
>
> 当前决策：暂停 G9 及之后的开发和验收，先保留一个能够重新构建、能够继续追溯的交接基线

## 1. 先读结论

EasyFly 是一个以 ROS 2 Humble、PX4 1.16、MAVROS 2、Gazebo Classic 为基础的自主无人机平台。项目最终希望把驱动、飞控协议、感知、定位、地图、规划、控制、任务编排和应用接口组织成一套边界清楚、可替换、可仿真验收、可逐步迁移到实机的统一平台。

截至本次交接：

- `src` 中 67 个 ROS/CMake 包可以从清理后的工作区完整构建；2026-10-04 实测 `67 packages finished`，无构建失败。
- 核心仿真链已经完成 G0-G8 阶段性验收：PX4/MAVROS、基础飞控、传感器与 TF、检测、FAST-LIO、跟踪与 3D 融合、语义地图、目标跟随、A* 导航、EGO 局部规划均已有历史动态证据。
- G8 的 V2-19 是目前最复杂的一次收口，最终基线记录为连续两轮完整门禁通过；它覆盖了 EGO 轨迹时间基、碰撞准入、动态障碍、轨迹 ACK、断流急停、外部接管等安全问题。
- 项目还不是“完整产品”：大量通信、感知算法、SDK、服务、任务和 UI 包只是可构建的骨架；G9 稳定性、G10 台架/HIL、G11 实机飞行没有完成。
- 当前基线只能表述为“仿真核心链阶段性可用”，不能表述为“可直接上实机”，更不能带桨自由飞行。
- 本次按项目所有者要求删除了复验期原始日志、顶层验收脚本和旧 P0 文档。历史结论仍保存在 Git 提交与 `question-v2.md` 中，但原始运行日志已不在当前工作树。

接手者应先理解第 4-8 节的系统契约，再决定是否恢复验收工具。不要因为 67 个包都能编译，就把所有包判断为功能已完成。

## 2. 项目的目标、思路与边界

### 2.1 总体目标

EasyFly 的目标不是简单拼接几个 ROS 节点，而是形成以下能力：

1. 用同一套消息、Action 和服务屏蔽 PX4、MAVROS、传感器和上层算法之间的差异。
2. 建立从传感器到环境理解，再到规划和控制的闭环。
3. 使任务层只依赖稳定的动作接口，而不直接操作 MAVROS 或具体规划器。
4. 仿真与实机尽量复用同一业务链，只在驱动、时钟、参数和安全边界上切换。
5. 所有会影响飞行的链路都具备明确的准入、超时、取消、接管、急停和终态语义。
6. 通过分阶段门禁验证，而不是一次性拉起全系统后凭现象判断。

### 2.2 设计原则

- **分层隔离**：通信、感知、执行、应用四层；层间通过 ROS 2 接口连接。
- **统一控制出口**：EasyFly 业务链中由 `easyfly_flight_control -> easyfly_mavlink_bridge -> MAVROS` 下发控制，避免多个节点同时争夺 PX4 setpoint。
- **本地坐标统一**：核心飞行链使用 `odom`、ENU/FLU、Z 向上；任何跨坐标系数据必须先变换并保持 header 与数值含义一致。
- **ROS 时间统一**：仿真时使用 `/clock` 与 `use_sim_time`；不可混用裸墙钟、PX4 时间和 ROS 仿真时间做新鲜度判断。
- **失败关闭**：状态无效、TF 缺失、地图过期、轨迹非法、数据超时或下游失活时，不继续发出未经验证的飞行命令。
- **动作有终态**：被接受的 Action 必须最终 `SUCCEEDED`、`ABORTED` 或 `CANCELED`，不能永久悬挂。
- **证据驱动验收**：构建成功、节点存在、话题发布、动作成功和安全接管是不同层级的证据，不相互替代。

### 2.3 当前明确不应承诺的内容

- 未完成实机级安全认证或航空法规合规。
- 未完成长期稳定性、资源泄漏、反复重启与压力测试。
- 未完成全部规划器的统一对外入口。
- 未完成完整 SDK、服务层、任务库和 UI 产品化。
- 未冻结所有第三方源码的可复现来源。

## 3. 仓库结构与资料可信度

```text
easyfly_ws/
├── src/                    # 当前实际产品源码与随仓库管理的第三方包
│   ├── communication/      # C1 驱动、C2 协议、C3 媒体
│   ├── perception/         # P1 预处理、P2 检测、P3 跟踪、P4 融合
│   ├── execution/          # E1 状态机、E2 规划、E3 控制
│   ├── application/        # A1 SDK、A2 服务、A3 任务
│   ├── easyfly_common/     # 消息与公共工具
│   ├── simulation/         # PX4 SITL、Gazebo 世界/模型/插件
│   ├── easyfly_ui/         # 桌面、Web、UI bridge
│   └── third_party/        # EGO、FAST-LIO、Livox SDK、librealsense 等
├── Platform/               # 设计时参考的三个外部工程，不属于 EasyFly 构建输入
├── models/                 # 推理模型，例如 yolo11n.onnx
├── plan.md                 # 最初愿景和开发阶段规划，仅作历史参考
├── schedule-v2.md          # 暂停复验前的阶段盘点，内容早于 G8 收口
├── test-v2.md              # G0-G11 验收方法和依赖版本基线
├── question-v2.md          # V2-01 至 V2-19 的问题、修复和动态验收主记录
└── schedule-v3.md          # 当前交接事实入口
```

资料使用优先级：

1. 当前源码、参数和 launch 文件；
2. 当前 Git 历史及本文件；
3. `question-v2.md` 中对应问题的最终一轮记录；
4. `test-v2.md` 的方法与门禁；
5. `schedule-v2.md`、`plan.md` 的历史规划。

`question-v2.md` 是过程型日志，同一问题可能经历多次被后续证据推翻的中间判断。阅读 V2-19 时必须一直读到 r29 收尾，不能停在早期“待修复”标题。

## 4. 当前架构

### 4.1 四层十三子层

| 层 | 子层 | 当前职责 | 当前成熟度 |
|---|---|---|---|
| 通信层 | C1 驱动 | RealSense、Livox、RC、串口、GPS | RealSense/Livox 有集成；其他多为骨架 |
| 通信层 | C2 协议 | MAVLink bridge、UDP、Mesh | MAVLink 核心可用；UDP/Mesh 待实现 |
| 通信层 | C3 媒体 | 视频推流、录像 | 骨架 |
| 感知层 | P1 预处理 | 标定、坐标变换、点云过滤、时间同步 | 点云/坐标主链可用；其余不完整 |
| 感知层 | P2 检测 | 通用目标、AprilTag、降落标志、线/椭圆、ReID | 通用目标检测已验收；其余多为骨架 |
| 感知层 | P3 跟踪 | FAST-LIO、单/多目标跟踪、目标预测 | FAST-LIO 与多目标主链已验收；其余不完整 |
| 感知层 | P4 融合 | 像素转 3D、语义地图、深度、雷视融合 | 像素转 3D/语义地图已验收；其余不完整 |
| 执行层 | E1 状态机 | 任务状态、动作编排 | 基础任务 FSM 已实现，复杂任务待扩展 |
| 执行层 | E2 规划 | 全局 A*、本地 EGO、集群、轨迹优化 | A* 与 EGO 分别已验收，尚未完全统一 |
| 执行层 | E3 控制 | 飞行、跟随、云台、避障、精准降落 | 飞控与目标跟随核心可用；其余待实现 |
| 应用层 | A1 SDK | C++ core、参数、Python binding | 骨架 |
| 应用层 | A2 服务 | 感知与任务服务 | 骨架/少量接口 |
| 应用层 | A3 任务 | 仿真入口、任务脚本、示例 | 仿真入口可用；任务产品化待完成 |

### 4.2 核心控制流

```text
PX4 SITL / 实机 PX4
        ↕ MAVLink
MAVROS
        ↕ state / pose / velocity / imu / setpoint / arm / mode
easyfly_mavlink_bridge
        ↕ /uav_state, /uav_command, arm/mode services
easyfly_flight_control
        ↕ Takeoff / Land / GoToWaypoint / FollowTrajectory
mission_fsm / global_planner / target_tracking / traj_server
```

职责边界：

- `easyfly_mavlink_bridge` 负责 MAVROS 状态聚合、EasyFly 命令到 MAVROS setpoint 的转换、解锁和模式服务。
- `easyfly_flight_control` 负责动作生命周期、轨迹接收、状态有效性、超时、外部接管和飞行命令生成。
- `easyfly_mission_fsm` 只通过动作接口编排起飞、航点、降落，不应绕开控制层直接控制 PX4。
- 仓库中存在上游 `ego_to_mavros`，但 EasyFly 正常架构不应让它与自身控制链同时向 MAVROS 发 setpoint。

### 4.3 感知、地图与规划流

```text
camera image ─> object_detection ─> /detections
                                      ├─> multi_object_tracking ─> /tracks
depth + tracks + TF ─> pixel_to_3d ──┴─> /target_positions (odom)
                                                └─> target_tracking
                                                     └─> GoToWaypoint

LiDAR ─> pointcloud_filter / FAST-LIO ─> odom + registered cloud
                    └─> semantic_map ─> /obstacles
                                      ├─> /occupancy_grid ─> global_planner
                                      └─> /pointcloud_nonground ─> EGO local planner

EGO ─> planning/bspline ─> traj_server ─> /position_cmd
                                           └─> FollowTrajectory
                                                └─> flight_control
```

注意：当前全局 A* 的执行方式仍是把路径拆成 `GoToWaypoint` 段；EGO 则通过 B-spline、`traj_server` 和 `FollowTrajectory` 执行。两者已经分别可用，但尚未形成一个自动选择全局/局部规划的统一 `NavigateTo` 端到端产品入口。

### 4.4 公共接口

`easyfly_msgs` 当前包含：

- 13 个消息：`DetectionInfo`、`DetectionInfoArray`、`GimbalState`、`MissionStatus`、`ObstacleInfo`、`ObstacleInfoArray`、`SwarmInfo`、`Target3D`、`Target3DArray`、`TrackInfo`、`TrackInfoArray`、`UAVCommand`、`UAVState`。
- 6 个服务：`ArmMotors`、`GetObstacles`、`QueryParams`、`SetFlightMode`、`SetGimbalAngle`、`TriggerLanding`。
- 8 个动作：`ExecuteMission`、`FollowTrajectory`、`GoToWaypoint`、`Land`、`NavigateTo`、`SearchArea`、`Takeoff`、`TrackTarget`。

修改这些接口会影响大量包。任何字段或语义变更都应先写迁移说明，再同时修改生产者、消费者、测试与配置。

## 5. 必须保持的关键契约

### 5.1 坐标和时间

- 本地飞行、目标位置、地图和轨迹的默认工作坐标系是 `odom`。
- ROS 局部坐标采用 ENU/FLU、Z 向上；与 PX4 NED/FRD 的转换集中在协议边界处理。
- header 中的 `frame_id` 必须与数据数值实际所在坐标系一致。V2-16 就是因标签与数值坐标不一致而产生。
- 仿真必须令相关节点使用 `use_sim_time=true`，新鲜度和 deadline 使用同一 ROS 时钟域。
- SITL 中 MAVROS timesync 采用仿真配置，避免 PX4/MAVROS 时间写入污染 ROS 时间戳；实机配置不能照搬 SITL 的 timesync 设置。

### 5.2 状态和动作生命周期

- `UAVState` 的 pose、velocity、FCU connected 等有效标志必须被实际检查，不能只看消息是否到达。
- Action server 接受目标前应完成输入和资源准入；同类动作使用单 Goal reservation，避免并发目标争夺控制权。
- 取消、抢占、外部 RTL/LAND 和节点退出必须传播到子动作/控制输出，并为每个已接受目标设置终态。
- PX4 外部 RTL/LAND 优先级高于 EasyFly 动作；检测到接管后，当前动作应 `ABORTED`，不能把接管误报为成功或继续抢回 OFFBOARD。

### 5.3 FollowTrajectory 与轨迹身份

- 新目标只绑定其准入水位之后出现的新轨迹 ID，不能消费上一目标残留轨迹。
- 拒绝时间逆序、非有限数、坐标系错误、过期、持续时间非法或身份不匹配的轨迹。
- 启动阶段允许有限宽限等待首条有效轨迹；当前历史实现采用约 8 秒启动宽限。
- 轨迹启动后必须使用更短的流 watchdog；历史验收中断流约 0.5 秒后进入安全悬停并结束目标。
- `TrajectoryAck` 不只是诊断信息，它是规划器、轨迹服务器和动作层之间的准入/急停证据，修改时必须保持身份匹配和一次性语义。

### 5.4 地图、点云和 EGO 安全边界

- EGO 应消费可信的去地面点云，不得把地面整体当作障碍输入。
- 点云、odom、栅格均有新鲜度、尺寸、点数和边界预算，避免陈旧数据或异常消息触发大内存分配。
- 轨迹验证必须覆盖完整时间区间和终点，不能只检查控制点或遗漏采样末端。
- 静态和动态障碍采用不同证据链；动态确认要依赖持续实测证据，并限制历史、预测点数量与寿命。
- 碰撞、非法轨迹、odom 超时或轨迹断流触发安全停止时，规划器、traj_server 和 FollowTrajectory 对急停状态的理解必须一致。
- 保留虚拟高度上限和规划边界。不要为了“规划能过”而绕开净空和边界门禁。

## 6. 已完成工作与验收状态

### 6.1 G0-G3：基线、构建和纯逻辑门禁

- 建立版本基线和分阶段验收方法，详见 `test-v2.md`。
- 处理 `test_sort` 测试注册问题（V2-04）。
- 核心接口、控制、感知基础、规划和驱动包可构建。
- 完成 FlightController mock、坐标/安全契约等一批单元与静态回归。
- 已知 lint 债务没有完全清零；构建通过不等于 lint 全绿。

### 6.2 G4：PX4 / Gazebo / MAVROS 最小稳定链

已解决并动态验证的关键问题：

- V2-07：PX4 SITL 默认目录与实际安装目录漂移，改为可解析/可配置的路径逻辑。
- V2-09：周期性 timesync time jump，统一仿真时钟域。
- V2-10：`easyfly_iris` 新增 D435i 后模型惯量、质量和传感器安装方式破坏飞行动力学；最终采用不引入错误相机刚体动力学的稳定模型方案。
- V2-11：仿真钟下坏 timesync 导致 MAVROS 时间戳清零，修正 SITL 与实机时间同步配置边界。

结果：最小 PX4/MAVROS/EasyFly 控制链可在 Gazebo 中稳定建立连接、解锁、进入 OFFBOARD 和飞行。

### 6.3 G5：基础飞行控制 T1-T9

历史验收覆盖：

- 起飞、降落、航点、取消、抢占和异常状态。
- 轨迹跟随的轨迹 ID 准入、旧轨迹拒绝、预热污染隔离和流超时。
- 外部模式接管以及动作终态。

需要保留的事实边界：G5 的记录由 T1-T8 两轮和修复后独立 T9 共同签收，并非两次从 T1 到 T9 的完全相同整轮执行。后续 G8 又覆盖了轨迹执行和断流/接管链，但如果将来做正式发布，仍建议恢复工具后重跑完整 G5。

### 6.4 G6：完整感知主链

- G6.1 传感器与 TF 通过。
- G6.2 YOLO 目标检测通过；V2-15 修正输入 QoS 契约和测试吞吐测量后，吞吐恢复正常。
- G6.3 FAST-LIO 定位与点云通过。
- G6.4 多目标跟踪、深度/点云辅助的 3D 目标定位通过；V2-16 修复 `/target_positions` 坐标系标签错误。
- G6.5 语义地图、障碍物、占据栅格和去地面点云通过。
- V2-14 处理 FastDDS 陈旧共享内存导致的间歇性数据断流。

### 6.5 G7：目标跟随与 A* 导航

- G7-F 目标跟随完成连续两轮动态验收。
- G7-N 全局 A* 导航完成连续两轮动态验收。
- V2-17 修复了语义地图地面平面随飞行高度失效、invalid-map 协议、局部切片安全裕量和 teardown 生命周期等问题。
- V2-18 修复 FAST-LIO 嵌套 launch 时 yaml 参数丢失、错误参数进入节点导致启动段错误的问题；静态、单元和启动上下文门禁已通过。

V2-18 的独立完整 SITL/RViz 长时间动态复验记录弱于 G7 其余项目。恢复工作后如首先使用 FAST-LIO 组合 launch，应将它列为快速冒烟项。

### 6.6 G8：EGO 局部规划与轨迹执行

V2-19 从 r1 到 r29 逐步处理了以下类别：

- B-spline 时间基错误以及 traj_server 永久扣发。
- EGO 输入未去地面、栅格膨胀与规划边界不安全。
- 异常点云/栅格触发 `std::bad_alloc` 的尺寸和预算问题。
- 完整轨迹碰撞采样、非法时间、终点和弦长遗漏。
- odom、点云、栅格 freshness 与启动时序。
- 动态障碍确认、关联、历史隔离、短时预测和证据预算。
- 规划器、traj_server、FollowTrajectory 间的 ACK、轨迹身份和原子提交。
- 急停、恢复稳定门、轨迹断流和下游存活判断。
- 外部接管与 E3 kill 前 active 状态门。
- 测试桩隔离与负向契约回归。

最终历史结果：

- 静态/单元回归：66/66 通过。
- r29 完整门禁：25/25，通过并正常退出。
- r29-review-next-1 第二轮：25/25，通过并正常退出。
- E1 静态障碍准入、E2 动态障碍、E4 外部接管均通过。
- E3 轨迹断流分别约 0.61 秒和 0.56 秒被检测，并进入安全悬停。

这些结果已进入 `0724742` 的提交说明和 `question-v2.md` 最终记录。原始 `log-v2-*` 证据目录已按所有者要求删除，因此本节是历史签收结论，不是当前工作树内可直接审计的原始证据。

## 7. 本次交接前清理与重建结果

### 7.1 已清理内容

按项目所有者要求，当前提交删除：

- `log-v2-r6*` 等复验构建/运行日志目录；
- 顶层 `test/` 复验工具和验收脚本；
- `test-guide.md`；
- 旧的 `codex-P0.md`。

没有删除各功能包内部的 `src/**/test`，这些属于源码级单元/集成测试，仍应随源码维护。

生成目录 `build/`、`install/`、`log/` 已重新产生但由 Git 忽略，不进入提交。

如未来确需恢复旧的顶层验收工具，可从功能基线取回：

```bash
git restore --source=0724742 -- test test-guide.md
```

如只需查看旧 P0 文档而不恢复到工作树：

```bash
git show 0724742:codex-P0.md
```

旧原始运行日志不要假定可由 Git 完整恢复；其中许多内容本来就是忽略项或符号链接。需要可审计证据时应重新执行验收并把摘要、环境元数据和必要原始结果归档到明确位置。

### 7.2 从 `src` 重新构建结果

本次清理后执行：

```bash
source /opt/ros/humble/setup.bash
colcon build --base-paths src --symlink-install --event-handlers console_direct+
```

结果：

- 67 个包完成；
- 0 个构建失败；
- 9 个包产生 stderr 警告；
- `easyfly_core`、`ego_planner` 均能由新的 `install` 前缀解析；
- `install/ego_planner/lib/ego_planner/ego_planner_node` 已生成且可执行。

构建警告主要来自第三方 CMake 兼容性、librealsense 的非特权 `ldconfig`、上游/集成代码的未使用变量等。特别需要优先检查 EGO 中 `flag_too_far may be used uninitialized`；它目前没有阻塞构建，但属于控制流未定义风险，不应长期忽略。

这次只验证了干净重建，没有在清理后重新运行 PX4/SITL 动态验收。当前动态结论来自清理前的 G0-G8 记录。

## 8. 依赖和环境基线

以下是 `test-v2.md` 最后冻结的开发机环境，换机或升级后应重新执行该文档第 5 节的版本快照命令：

| 类别 | 当前记录 |
|---|---|
| OS / 内核 | Ubuntu 22.04.5，Linux 6.8.0-138，x86_64 |
| 编译工具 | GCC 11.4，CMake 3.22.1，Python 3.10.12，colcon-core 0.20.1 |
| ROS | ROS 2 Humble，rclcpp 16.0.19，FastRTPS 6.2.10 |
| 飞控/仿真 | MAVROS 2.14.0，Gazebo 11.10.2，gazebo_ros 3.9.0 |
| PX4 | `/home/jia/PX4-Autopilot-1.16.2`，v1.16.2-dirty，记录 commit `54f0455...` |
| ROS 感知 | tf2_ros 0.25.20，cv_bridge 3.2.1，image_transport 3.1.12，pcl_ros 2.4.5 |
| 数学/视觉 | OpenCV 4.5.4，PCL 1.12.1，Eigen 3.4，yaml-cpp 0.7 |
| GPU | RTX 5060 Ti 16 GB，驱动 595.91.07，CUDA Toolkit 12.8，cuDNN 9.8 |
| 推理 | ONNX Runtime 1.23.2，`models/yolo11n.onnx`（hash 见 `test-v2.md`） |
| RealSense | realsense-ros `4.56.4-1-gd69f05c1`，librealsense API 2.56.5 |
| Livox | livox_ros_driver2 包 1.0.0；SDK 记录约 1.2.5，来源仍需正式冻结 |

FAST-LIO、EGO-Planner、Livox SDK 的上游仓库、fork、补丁基点没有完全形成机器可重建的 provenance；RealSense 的嵌套仓库/子模块信息也应在后续整理。当前最可靠的事实是“它们与 EasyFly 当前 Git 提交绑定”，而不是只看包版本号。

## 9. 尚未完成的工作

### 9.1 已暂停的验收阶段

项目所有者已明确暂停 G9 及后续工作。以下内容未完成，除非项目所有者重新启动，不应擅自继续：

- **G9 稳定性与重复性**：30 分钟以上持续运行、10 次冷启动/重启循环、CPU/GPU/内存/磁盘资源趋势、DDS 与进程残留、时钟暂停/恢复、节点 kill/restart、压力和边界输入。
- **G10 台架/HIL/系留**：真实飞控、传感器、RC、失联保护、急停和有限空间验证。
- **G11 自由飞行**：逐级扩大包线的实机飞行验证。

### 9.2 功能尚未实现或只具备骨架

主要包括：

- 通信：GPS receiver、UDP、Mesh、视频 streamer/recorder。
- 感知预处理：完整 time sync、通用标定工作流。
- 检测：AprilTag、降落标志、椭圆、色线、Vehicle ReID。
- 跟踪/融合：单目标跟踪、目标预测、深度估计、雷视融合。
- 执行：swarm planner、独立轨迹优化器、通用 obstacle avoidance、gimbal control、precision landing。
- 应用：`easyfly_core` SDK、参数 SDK、Python binding、感知/任务服务、任务脚本、示例体系。
- UI：desktop、web、ui_bridge 的完整产品能力。

这些包中的很多已经有 `package.xml`、CMake 和占位节点，所以能被 colcon 计入 67 个包。判断完成度时必须查看实现和运行证据。

### 9.3 架构待收口事项

1. 将全局 A*、局部 EGO 和飞控动作组织成一个明确的 `NavigateTo` 产品级入口，定义切换、重规划、失败回退和终态。
2. 明确规划器到控制器的唯一生产路径，隔离或禁用上游示例节点对 MAVROS 的直接控制。
3. 为 frame、clock、QoS、trajectory ID、ACK 与 emergency state 建立集中契约文档和跨包契约测试。
4. 将节点参数从分散 yaml/launch 组合收口为按仿真、实机、传感器组合区分的可追溯配置集。
5. 完成第三方依赖的版本、来源、许可证和本地补丁清单。
6. 明确 SDK/API 的稳定边界后，再大规模开发应用层和 UI，避免绑定内部话题细节。

### 9.4 技术债和已知风险

- 构建仍有编译警告；优先审计 EGO `flag_too_far` 未初始化风险。
- V2-05 中记录的 lint 债务没有完整清零。
- 当前没有顶层端到端验收脚本；若继续迭代核心链，应先恢复或重建最小门禁。
- V2-19 的动态结果已经通过，但修复跨度大、耦合深；任何 EGO、semantic_map、traj_server、flight_control 改动都应做跨层回归。
- `build_all.bash` 和环境脚本不应被盲目信任为唯一入口；交接时已验证的明确命令是 `colcon build --base-paths src --symlink-install`。
- 真实传感器固件、外参、网络、时间同步、飞控参数和失效模式尚未冻结。
- 目前的“安全”是软件行为和仿真门禁意义上的安全，不替代实机风险评估。

## 10. 建议的恢复顺序

当前暂停状态下只需保留本节；正式恢复开发时按以下顺序执行。

### 第 0 步：确认基线，不立即升级依赖

```bash
cd /home/jia/easyfly_ws
git status --short
git log -5 --oneline
source /opt/ros/humble/setup.bash
colcon list --base-paths src | wc -l
```

预期包数为 67。先记录实际 OS、ROS、PX4、MAVROS、Gazebo、GPU、驱动和传感器版本，再决定是否升级。不要同时升级 PX4、ROS 驱动和感知库。

### 第 1 步：建立可重复的构建和证据目录

- 使用隔离或明确的 `build/install/log`。
- 构建命令显式限定 `--base-paths src`，不要把 `Platform` 参考项目扫入工作区。
- 保存 colcon summary、失败包和编译警告。
- 修复或显式登记 EGO 未初始化警告后再进行长期动态运行。

### 第 2 步：恢复最小测试门禁

从 `0724742` 恢复旧顶层测试只能作为起点。恢复后先审阅脚本对路径、进程名、超时和当前接口的假设；不要直接把历史绿色结果当作当前结果。

建议的最小门禁集合：

1. 接口生成、坐标变换和纯逻辑单元测试；
2. FlightController 无 PX4 mock 故障注入；
3. PX4/MAVROS 最小起飞、悬停、降落；
4. G5 轨迹 ID、断流、取消、抢占和外部接管；
5. G6 FAST-LIO 组合 launch、TF 和语义地图冒烟；
6. G7 跟随与 NavigateTo；
7. G8 E1-E4 两次完整独立运行。

### 第 3 步：再进入 G9

只有前述最小门禁在当前提交、当前环境上重新通过，才开始 G9。G9 的目标不是增加功能，而是证明重复运行、资源使用、重启恢复和失效处理稳定。

### 第 4 步：实机前单独评审

进入 G10/G11 前必须单独检查：

- PX4 参数和 failsafe；
- RC/人工接管和物理急停；
- 坐标系、外参和时间同步；
- 速度、高度、地理围栏和电池门限；
- 推进系统、桨叶、系留与场地风险；
- 每个 Action 在传感器断流、MAVLink 断开和节点崩溃时的行为。

## 11. 接手者第一天应做的事情

1. 阅读本文件，再阅读 `question-v2.md` 的索引、G5-G8 最终记录和 V2-17/V2-18/V2-19。
2. 执行 `git status`，确认没有把旧生成物或个人配置误认为源码。
3. 使用第 7.2 节命令从 `src` 构建，确认仍是 67 包。
4. 查看 `src/execution/e3_control/easyfly_flight_control`、`src/communication/c2_protocol/easyfly_mavlink_bridge`、`src/execution/e2_planning`、`src/perception/p4_fusion/easyfly_semantic_map` 和 `src/third_party/planners/ego_planner`，对应第 4-5 节的契约。
5. 在修改代码前写清受影响的数据流、frame、clock、Action 终态和失败模式。
6. 如果恢复动态验收，先创建新的带日期证据目录，不复用已删除的 `log-v2-*` 名称作为唯一证据。

## 12. 修改与验收纪律

- 每次只解决一个明确问题，先保存失败证据，再修改，再运行最小回归与跨层回归。
- 不用延长 timeout 掩盖时钟、死锁、线程饥饿或数据不新鲜问题。
- 不用放宽碰撞距离、关闭 freshness、跳过 ACK 或删除急停来让测试变绿。
- 对仿真专用参数和实机参数进行显式分组，禁止依赖“默认值刚好可用”。
- 运行结束后确认 PX4、Gazebo、MAVROS、ROS 节点和 DDS 残留已清理，再开始下一轮。
- 验收记录至少包含：Git commit、环境版本、完整命令、开始/结束时间、结果矩阵、关键 topic/action 证据和失败日志位置。
- 代码评审重点不是格式，而是 frame、time、QoS、状态有效性、边界预算、并发、生命周期和安全终态。

## 13. 关键入口索引

| 目的 | 入口 |
|---|---|
| 项目概览 | `README.md` |
| 原始路线 | `plan.md` |
| 验收体系与版本 | `test-v2.md` |
| 问题与修复历史 | `question-v2.md` |
| 消息/服务/动作 | `src/easyfly_common/easyfly_msgs` |
| MAVROS 边界 | `src/communication/c2_protocol/easyfly_mavlink_bridge` |
| 飞行动作与轨迹控制 | `src/execution/e3_control/easyfly_flight_control` |
| 任务状态机 | `src/execution/e1_state_machine/easyfly_mission_fsm` |
| 全局规划 | `src/execution/e2_planning/easyfly_global_planner` |
| EGO 集成 | `src/execution/e2_planning/easyfly_local_planner`、`src/third_party/planners/ego_planner` |
| 定位 | `src/perception/p3_tracking/easyfly_fast_lio_integration`、`src/third_party/slam/fast_lio` |
| 检测与跟踪 | `src/perception/p2_detection/easyfly_object_detection`、`src/perception/p3_tracking/easyfly_multi_object_tracking` |
| 3D 目标 | `src/perception/p4_fusion/easyfly_pixel_to_3d` |
| 地图 | `src/perception/p4_fusion/easyfly_semantic_map` |
| 仿真 | `src/simulation`、`src/application/a3_mission/easyfly_sim_launcher` |

## 14. 最终交接状态

EasyFly 已经越过“只有目录和接口”的阶段：核心 SITL、感知、导航和局部规划闭环确实完成过系统级动态验收，也围绕飞行安全修复了大量真实的跨层问题。但它仍处于研究/开发平台而不是可交付飞行产品阶段。

最合适的下一目标不是继续扩展功能，而是在项目所有者决定恢复后，先重建精简且可长期维护的自动验收门禁，确认当前基线可重复，再完成 G9 稳定性。只有 G9 稳定通过且实机配置经过单独安全评审，才应进入 G10/G11。

在此之前，请保持当前提交可回溯，不要批量升级依赖或同时重构多条主链。
