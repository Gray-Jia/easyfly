# EasyFly 任务书：M4.3 EGO-Planner 集成（含项目交接）

> **本文档用途**：上下文交接 + M4.3 执行任务书。新会话从这里接手即可，**无需追问历史**。
> **生成时间**：2026-09-14（M4.2 完成后）
> **权威文档**：`plan.md`（总体设计）、`schedule.md`（进度，**始终最新**）、`question.md`（问题账本 Q1-Q36）、`test-guide.md`（操作手册）。本文档是它们之上的"执行交接包"，冲突时以 schedule.md/question.md 为准。

---

## 1. 项目速览

**EasyFly**：自主无人机开源平台。技术栈：ROS2 Humble + PX4 1.16.1 + Gazebo Classic 11 + Ubuntu 22.04。

- 工作区：`/home/jia/easyfly_ws`（git 分支 `master`，远程 `github.com/Gray-Jia/easyfly.git`）
- 四层 13 子层：通信层 C1-C3（驱动/协议/媒体）、感知层 P1-P4（预处理/检测/跟踪/融合）、执行层 E1-E3（状态机/规划/控制）、应用层 A1-A3（SDK/服务/任务）；另有 `easyfly_ui/`、`simulation/`、`third_party/`
- 设计蓝本（`Platform/` 下三工程，**不参与编译**）：Prometheus（控制/架构）、AstraDroneOpen（驱动/仿真）、SpireCV（感知 SDK）
- 编译：`colcon_defaults.yaml` 限定 `base-paths: ["src"]`（Platform 内 ROS1 包会冲突）；`bash build_all.bash` 或 `colcon build --symlink-install`

### 目录规范（本次会话确立，务必遵守）

| 位置 | 放什么 |
|------|--------|
| `src/third_party/<类别>/<算法名>/` | **上游算法原样**（保留上游包名，便于 diff/同步/替换）。如 `third_party/slam/fast_lio/`、`third_party/planners/ego_planner/`；底层 SDK（librealsense/livox_sdk2/onnxruntime）直接在 `third_party/` 下 |
| `src/<层>/<子层>/easyfly_*` | **easyfly 自己的包**；适配/集成知识集中在 `easyfly_*_integration`、`easyfly_local_planner` 这类包里 |

---

## 2. 当前状态（截至交接）

### 已完成并验证

| 阶段/里程碑 | 内容 | 关键提交 |
|-------------|------|----------|
| 〇 基础设施 | 13 子层骨架 + easyfly_msgs(13msg/6srv/6action) + easyfly_utils | 早期 |
| 一 通信+仿真 | serial/rc_receiver/mavlink_bridge/livox 驱动/realsense/仿真体系 | c707cd3 等 |
| 二 控制闭环 | flight_control(3 action) + mission_fsm(YAML 任务) | 68751ad + 后续修复 |
| 三 感知 M0-M6 | 仿真传感器/P1 TF/检测/SLAM/SORT/pixel_to_3d/全链路验收 | aa8e18e, 9dfd638, a9e0319 |
| **Q19 专项** | 世界系 id 整合器（轻量 ReID）：`/tracks` 稳定 id + `/tracks_raw`；飞行 unique id 26→19 | 2afa61c |
| **M4.0** | `easyfly_pointcloud_filter`（CustomMsg→滤波→PointCloud2）+ `easyfly_semantic_map`（逐帧 RANSAC 地面剔除 + 累积聚类 + 两段式持久栅格 → `/obstacles` + `/get_obstacles` + `/occupancy_grid` + markers） | a9e0319 |
| **M4.1** | `easyfly_target_tracking`（TrackTarget 航点重发式跟随：跳变拒绝/断流丢失判定/id 轮换重捕获/接管传播/高度 clamp）+ `patrol_mover` 巡航插件 | 6c974d9 |
| **M4.2** | `easyfly_global_planner`（`astar.hpp` 2D A*+LOS 剪枝，单测 8/8；`NavigateTo.action`；逐段 GoToWaypoint 执行）+ semantic_map 两段式栅格 | 4ef96d4, 2748d6f |

### 回归/验收套件（硬门禁，改代码后必跑）

| 脚本 | 用例 | 说明 |
|------|------|------|
| `bash test/run_control_regression.sh` | T1-T8 | 控制链：就绪/起飞/航点/航点取消/降落取消/连续起降/坏任务文件/低电量RTL |
| `bash test/run_follow_acceptance.sh` | F1-F5 | 跟随：就绪/静态跟随 4±1m/移动跟随/丢失悬停/取消语义 |
| `bash test/run_navigate_acceptance.sh` | N1-N5 | 导航：就绪/绕障(min>0.9m)/返程/目标在障碍内/取消语义 |

### 未完成

- **M4.3 EGO-Planner 集成（本任务）**
- M4.4 导航栈整合（NavigateTo→EGO）+ reactive 避障 + 轨迹优化评估
- M4.5 精确降落（下视相机 + AprilTag + TriggerLanding 闭环）
- 阶段五 应用层（SDK/服务/任务引擎）、阶段六 UI+媒体
- 云台（已移出阶段四，等实机型号）

---

## 3. 执行约定（必须遵守）

1. **每里程碑**：开工简报（改什么）→ 实现 → 验收数据 → **控制回归全绿** → `schedule.md` 更新 → 立即 commit。
2. **重要改动立即 commit** —— 本机存在**外部进程周期性还原工作区文件**（实测三次：world 立柱编辑消失、`phase3_plan.md` 被删、验收脚本补丁被回滚）。对策：改完文件先 `grep` 确认内容，再跑测试；改完立刻提交。
3. **验证代码改动必须看全量编译输出**——曾用 `grep "error|Finished"` 过滤吞掉编译错误，导致连跑两轮旧二进制，现象与代码对不上浪费大量排查。
4. 单测运行：`cmake --build build/<pkg> --target <test> && ./build/<pkg>/<test>`（gtest 目标默认 EXCLUDE_FROM_ALL，`colcon test` 可能不触发）。
5. 仿真启停：`bash easyfly_clean.sh`（杀 gzserver/px4/mavros/fastlio_mapping 等）；验收编排脚本已内建清理 + headless 保护（杀 gzclient/rviz2），**不要删**。
6. 首次起飞前等 EKF：**30s settle + arm 失败重试一次（20s）**——SITL 感知负载下收敛慢，测试脚本已有此模式。
7. 用户偏好：直接、要实测数据、**有不清楚的先停下来问**、重大决策先给方案再动工。

---

## 4. 环境坑账本（相关条目）

| 编号 | 现象 | 解法 |
|------|------|------|
| Q36 | X/GLX 资源耗尽：高频启停仿真 ~10 次后 gzserver 报 `GLX CreateContext` 失败 → 世界不初始化 → PX4 等 4560 超时 exit 255。杀 gzclient/rviz2 无效 | **重启机器/X 会话**（不是代码问题，别排查代码） |
| — | SITL 会话劣化：连续多轮起降后磁力计/EKF 退化（`Attitude failure (roll)`/`horizontal velocity unstable`/RTF 崩 `Time jump`）| **重启机器**；失败点逐轮随机且代码未改控制链即可判定 |
| Q35 | `~/.gazebo/models/<name>` 缓存抢优先于 GAZEBO_MODEL_PATH | 删除该缓存条目 |
| Q34 | mavros EKF 启动位置毛刺 (0.98,-2.52) 级 | semantic_map 已加 TF 跳变守卫；验收脚本自锚定实时数据规避 |
| Q22 | MID-360 平放：2.5m 航高下雷达最低可视高度 = 航高 − 距离×tan(7°)（5m 处 1.89m）→ 矮障碍不可见 | 规划验收用 3m 立柱；实机需倒装 |
| Q19 | SORT id 轮换 | ✅ 已解决（id_consolidator） |
| — | **mavros 源码**：已 clone 2.14.0 到 `/tmp/mavros-src`（可能不持久，可重下：`git clone --depth 1 --branch 2.14.0 https://github.com/mavlink/mavros.git`），查 mavros 行为直接读源码 |

---

## 5. M4.3 任务书

### 5.1 目标

把用户迁移的 EGO-Planner（`/home/jia/ego_planner_ros_humble`，基于 Kaede-Rukawa 移植版 + 用户修复，可编译）集成进 easyfly，实现**局部规划 + 轨迹跟踪飞行**，控制接入 easyfly 控制链。

### 5.2 已批准决策（用户确认，勿再询问）

1. **控制接入方案 A**：集成入 easyfly 控制链（`UAVCommand` 加 TRAJECTORY 模式 + bridge encoder + flight_control 新增 `/follow_trajectory` action）；
2. **ego_to_mavros 桥的 ENU→NED 手动换轴按判断修**（已由 mavros 源码证明是双重变换 bug，见 5.3）；
3. **复制范围**：7 包（quadrotor_msgs / path_searching / bspline_opt / plan_env / traj_utils_z(目录改名 traj_utils，包名本就是 traj_utils) / plan_manage / ego_to_mavros），**排除** uav_simulator、bridge_test、new（空壳）；
4. **验收方式**：手动 goal（CLI/RViz）+ **轻链**（跳过 YOLO/跟踪/SLAM）；NavigateTo→EGO 完整导航栈接线**下沉 M4.4**；
5. **目录规范**：上游算法进 `third_party/`，适配包在层内（见第 1 节表）。

### 5.3 侦察结论（已核实，直接可用，不必重查）

| 项 | 结论 |
|----|------|
| **点云坐标系** | EGO `grid_map` 直接用点的原始坐标、**零变换** → 点云必须已在世界系。改 `easyfly_pointcloud_filter/config/pointcloud_filter.yaml` 的 `output_frame: base_link → odom`（semantic_map 的 TF 查询退化为恒等，无副作用） |
| **触发** | `ego_replan_fsm.cpp:58` `have_trigger_ = !flag_realworld_experiment_`；sim 模式（`fsm/realworld_experiment: False`）**have_trigger_ 初始为 true → 不需要发 /traj_start_trigger** |
| **目标接口** | `fsm/flight_type: 2`（MANUAL_TARGET）订 `/move_base_simple/goal`（PoseStamped）。**注意**：`waypointCallback` 里 goal 高度**硬编码 z=1.0**（`Eigen::Vector3d end_wp(x, y, 1.0)`）→ EGO 航线在 1.0m 高度（sim 可接受，低空反而利好雷达可视性；不改上游代码，文档记录） |
| **输出** | `traj_server` 发 `/position_cmd`（`quadrotor_msgs/PositionCommand`，50Hz，含 position/velocity/acceleration/yaw/yaw_dot，`trajectory_flag=READY`）；`planning/bspline` 为内部话题 |
| **参数位置** | 全部内联在 `plan_manage/launch/advanced_param.launch.py`（**无 yaml 配置文件**，只有 random_forest.yaml 是场景用的）。必须按雷达重调的项：`obstacles_inflation: 0.099→~0.35`、`max_ray_length: 4.5→~20`、`local_update_range_x/y: 5.5→~15`（z 4.5 可留）、**`use_depth_filter: True→False`**（否则点云被 `depth_filter_maxdist: 5.0` 裁到 5m）；其余（resolution 0.1、p_hit/p_miss、planning_horizon 7.5、max_vel 2.0、max_acc 6.0）可先沿用 |
| **mavros 坐标系（源码实证）** | `mavros 2.14.0` `setpoint_raw.cpp` `local_cb`：除 `FRAME_BODY_NED/*_BODY_OFFSET_NED` 外**一律按 ENU 处理并自动 `transform_frame_enu_ned`**。→ **正确写法：发 ENU 数值 + `coordinate_frame = FRAME_LOCAL_NED(1)`，`type_mask` 原样透传**。TRAJECTORY（位置+速度+yaw，忽略加速度/角速率）mask = `IGNORE_AFX\|IGNORE_AFY\|IGNORE_AFZ\|IGNORE_YAW_RATE` = 64+128+256+1024 = **1472**。→ 用户桥的手动换轴 = 双重变换（轴序错乱+高度反号），**修法：删掉 `fillTrajectorySetpoint`/`fillHoldSetpoint` 的换轴，直传 ENU** |
| **命名空间** | 上游用 `drone_id` 前缀（`/drone_0_planning/pos_cmd` 等）；我们的适配 launch **不用它**，显式 remap 到无前缀话题 |
| **上游包依赖** | `plan_manage` 需 `quadrotor_msgs`/`traj_utils`/`cv_bridge`/`message_filters`/PCL 等；目录 `traj_utils_z` 的包名是 `traj_utils`（复制时目录可改名 `traj_utils`） |

### 5.4 任务分解（a→e，逐步汇报）

**a) 结构统一 + 复制 + 编译（0.5-1 天）**
1. `git mv src/perception/p3_tracking/fast_lio src/third_party/slam/fast_lio`，重编，冒烟（perception_sitl 起点云/Odometry 正常）；同步 schedule.md 目录规范；
2. 复制 7 包到 `src/third_party/planners/ego_planner/`（保留包名/内容原样，仅 `traj_utils_z` 目录改名为 `traj_utils`）；
3. `colcon build` 全量通过（预期小坑：cv_bridge 未装则 `sudo apt install ros-humble-cv-bridge`、包间 include、ament 依赖声明）。

**b) 数据接线 + 轻链联调（1 天）**
1. 启用适配包 `src/execution/e2_planning/easyfly_local_planner`（当前是空壳）：自写 launch（**不用上游 single_run_in_sim**，绕开 map_generator/pcl_render_node/rviz），起 `ego_planner_node` + `traj_server`，参数用 5.3 重调后的值，remap：`grid_map/cloud→/pointcloud_filtered`、`grid_map/odom→/odom`、`odom_world→/odom`、`planning/bspline→/planning/bspline`（position_cmd 默认即 `/position_cmd`）；`fsm/flight_type: 2`；
2. 轻链 launch：`pointcloud_filter` + `coord_transform` + EGO + RViz；pointcloud_filter 输出系切 `odom`；
3. 联调判据（RViz/CLI）：grid_map occupancy 随雷达成形 → CLI 发 goal → 出 bspline 轨迹 → `/position_cmd` 有 50Hz 流。

**c) 控制接入（1.5-2 天）**
1. `easyfly_msgs/msg/UAVCommand.msg` 加 `uint8 TRAJECTORY=5`（字段复用已有 position_x/y/z + velocity_x/y/z + yaw）；
2. `easyfly_mavlink_bridge` encoder 加 TRAJECTORY 分支 → `/mavros/setpoint_raw/local`（PositionTarget；**ENU 直传 + FRAME_LOCAL_NED + mask 1472**，见 5.3）；
3. `easyfly_flight_control` 加 `/follow_trajectory` action → TRAJ_FOLLOW 状态：转发 `/position_cmd`（50Hz）为 UAVCommand TRAJECTORY；**流断 >0.5s → 就地悬停 + abort**；**外部接管（mode 6/7）→ abort 让位**；**cancel → 悬停 + CANCELED**；仅 HOVER 可进入（与既有单动作槽互斥）；
4. 修 `ego_to_mavros` 桥（去手动换轴；保留作调试对比路径，注意它与我方 bridge 都发 setpoint，**不可同时运行**）；
5. **回归 T1-T8 + 新增 T9**：T9 用**合成 PositionCommand 发布器**（空世界，不依赖 EGO）验证 TRAJECTORY encoder + TRAJ_FOLLOW 全流程（跟随直线 → 到达；停发流 → 0.5s 悬停；cancel → CANCELED）。把 T9 加进 `test/control_regression.py` + 更新 README。

**d) 验收（1-1.5 天）** —— 新建 `test/ego_acceptance.py` + `test/run_ego_acceptance.sh`（复用既有编排器模式）
| 用例 | 断言 |
|------|------|
| E1 静态绕障 | 立柱走廊（可加 2-3 根立柱）目标对侧：SUCCEEDED、全程 min 间距 >0.8m、到达误差 <1m |
| E2 动态重规划 | patrol 行人横穿航线：EGO 在线重规划、与人 min >1.2m、仍到达 |
| E3 流中断安全 | 飞行中杀 traj_server → 0.5s 内回悬停（z 保持、不坠） |
| E4 接管让位 | 飞行中切 RTL → FollowTrajectory abort |
| E5 | `run_control_regression.sh` 全绿 |
| 对比（信息性） | 同场景 A*（NavigateTo）vs EGO 的绕行距离/平滑度 |

**e) 文档 + 提交（0.5 天）**：schedule.md 加 M4.3 节（含踩坑）、test-guide.md 加 EGO 启动/验收流程、README 注明轻链用法。

### 5.5 关键文件路径索引

| 用途 | 路径 |
|------|------|
| 用户 EGO 源 | `/home/jia/ego_planner_ros_humble/src/{planner/*, ego_to_mavros}` |
| EGO 参数（内联） | `ego_planner_ros_humble/src/planner/plan_manage/launch/advanced_param.launch.py` |
| EGO FSM | `.../plan_manage/src/ego_replan_fsm.cpp`（flight_type/trigger/goal 语义） |
| EGO grid_map | `.../plan_env/src/grid_map.cpp`（点云零变换、odom 用途） |
| EGO 输出 | `.../plan_manage/src/traj_server.cpp`（/position_cmd 组装） |
| 用户桥 | `.../ego_to_mavros/src/bridge.cpp`（换轴 bug 位置: `fillTrajectorySetpoint`/`fillHoldSetpoint`） |
| 我方点云滤波 | `src/perception/p1_preprocess/easyfly_pointcloud_filter/`（config 改 output_frame） |
| 我方适配包 | `src/execution/e2_planning/easyfly_local_planner/`（空壳，本任务启用） |
| 控制 | `src/execution/e3_control/easyfly_flight_control/`、`src/communication/c2_protocol/easyfly_mavlink_bridge/` |
| 消息 | `src/easyfly_common/easyfly_msgs/msg/UAVCommand.msg` |
| 回归/验收 | `test/run_control_regression.sh`、`test/run_follow_acceptance.sh`、`test/run_navigate_acceptance.sh`、`test/*.py` |
| mavros 源码 | `/tmp/mavros-src`（2.14.0；可重 clone） |

### 5.6 剩余风险（仅两项，执行中解决）

1. **编译期依赖**：cv_bridge/PCL/message_filters、包间 include 路径 → build 暴露即修；
2. **grid_map 参数实调**：inflation/update_range/概率阈值的最终值 → 第 b 步 RViz 里按雷达点云质量微调。

---

## 6. 项目理解要点（供快速上手）

### 数据流

```
【控制链】任务 YAML → mission_fsm → flight_control(3 action) → /uav_command
          → mavlink_bridge encoder → mavros setpoint → PX4
          PX4 → mavros 8 话题 → bridge decoder → /uav_state → 反馈回 FSM/控制器
【感知链】/livox/lidar + /camera/* → P1(TF/coord) → P2 YOLO11 ONNX(/detections)
          → P3 SORT+id整合器(/tracks 稳定id, /tracks_raw) → P4 pixel_to_3d(/target_positions)
          fast_lio → /Odometry + map→odom TF
【规划】/pointcloud_filtered + /occupancy_grid → easyfly_global_planner(/navigate, A*+逐段航点)
```

### 关键设计决策（已固化）

- **全链 odom 坐标系**（mavros EKF）：控制/感知/规划同系；map 系仅可视化 → Q28（map→odom 单点依赖）与 Q13（UAVState 时间戳）不阻塞主线；
- `flight_control` 定位：**setpoint 生成器 + PX4 内环**（无自研 PID）；航点用**全轴目标渐近式**（抗 mavros local_position 毛刺）；起飞"先建流后解锁"（降落后可再起飞）；接管检测（flight_mode 6/7 持续 2s）；
- `semantic_map` 栅格：**两段式持久化**（最近 20 帧≈3s 见过=100，超时=0）——不能用数值衰减（会在 A* 占据阈值边缘抖动）；
- 聚类逐帧闪烁是常态 → 消费方要么时间累积（票选），要么栅格持久化；
- 验收脚本一律**自锚定实时感知数据**（/obstacles 票选、栅格占据格），**禁止锚定 gazebo 世界坐标**（odom↔world 有每会话随机偏移，Q34 连续谱）；
- 每套验收脚本自带 headless 保护与进程清理；EKF 相关一律"30s settle + arm 重试"。

### 空壳包清单（未实现，供判断）

- e2_planning：`easyfly_local_planner`（**本任务启用**）、`easyfly_swarm_planner`、`easyfly_trajectory_optimizer`
- e3_control：`easyfly_gimbal_control`、`easyfly_obstacle_avoidance`、`easyfly_precision_landing`
- p2：`landing/apriltag/ellipse/color_line/vehicle_reid`；p3：`single_object_tracking/target_prediction`；p4：`lidar_camera_fusion/depth_estimation`（p4 的 semantic_map 与 pixel_to_3d 已实装）
- a1/a2/a3 全部、c3 全部、ui 全部（阶段五/六）

---

## 7. 下一步

**从任务 a 开始执行**（fast_lio 目录迁移 → 复制 EGO 7 包 → 编译），完成后按 b→c→d→e 推进，每步汇报验收数据。全部完成后回写 `schedule.md` 并提交。
