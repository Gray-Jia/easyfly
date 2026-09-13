# EasyFly 平台总体设计规划

> 本文档汇总第二次至第六次会话的设计成果。
> 技术栈：PX4 1.16 飞控固件 · Ubuntu 22.04 · ROS2 Humble · Gazebo Classic

---

## 目录

1. [四层架构总览](#1-四层架构总览)
2. [四层下的小层划分（4 大层 13 子层）](#2-四层下的小层划分4-大层-13-子层)
3. [ROS2 工作空间目录结构](#3-ros2-工作空间目录结构)
4. [EasyFly UI 设计](#4-easyfly-ui-设计)
5. [开发阶段顺序](#5-开发阶段顺序)

---

## 1. 四层架构总览

EasyFly 平台分为四层：

| 层 | 名称 | 定位 |
|---|------|------|
| ① | **通信层 (Communication)** | 数据总线，负责所有内外部数据流通 |
| ② | **感知层 (Perception)** | 环境理解与建模，输入原始数据，输出结构化环境信息 |
| ③ | **执行层 (Execution)** | 决策与行动中枢，将感知结果+任务指令转化为执行器命令 |
| ④ | **应用接口层 (Application Interface)** | 对上提供简洁 API，对下组织各层模块协作 |

### 1.1 通信层功能划分

| 子模块 | 功能 | 来源参考 |
|--------|------|----------|
| MAVLink 桥接 | 与 PX4 1.16 飞控双向通信 | Prometheus uav_control；AstraDroneOpen serial_tool |
| 机间/机地通信 | 无人机间、无人机与地面站数据交互 | Prometheus communication |
| 视频推流 | RTSP/RTMP 推流，FFmpeg(x86)/GStreamer(Jetson) 双后端 | SpireCV video_io |
| 传感器驱动 | Livox 雷达、RealSense 相机、串口、遥控器 | AstraDroneOpen 相关驱动 |
| UDP/TCP 协议 | 感知结果跨设备传输 | SpireCV UDP samples；AstraDroneOpen serial_tool |
| ROS2 自定义消息 | 系统内统一消息/服务/动作契约 | Prometheus prometheus_msgs |

> 设计决策：传感器驱动放通信层而非感知层——驱动是"数据获取"，不涉及算法处理。

### 1.2 感知层功能划分

| 子模块 | 功能 | 来源参考 |
|--------|------|----------|
| 激光 SLAM | FAST-LIO2 + ikd-Tree | Prometheus/AstraDroneOpen FAST_LIO |
| 通用目标检测 | YOLO 系列，CUDA/TensorRT + OpenVINO 双后端 | SpireCV common_det |
| 多目标跟踪 MOT | ByteTrack / SORT | SpireCV mot |
| 单目标跟踪 SOT | CSRT/KCF/SiamRPN | SpireCV sot；AstraDroneOpen pix_tracker |
| 起降标志检测 | 降落平台标志检测 | SpireCV landing_det |
| AprilTag/ArUco | 视觉标签定位与位姿解算 | AstraDroneOpen apriltag_ros |
| 单目深度估计 | 单目图像深度图 | SpireCV mde |
| 颜色线/椭圆检测 | 竞赛场景检测 | SpireCV color_line/ellipse_det |
| 车辆再识别 ReID | 跨帧车辆身份关联 | SpireCV veri |
| 激光-相机融合 | 点云着色、像素转 3D | AstraDroneOpen lidar_cam_fusion, pixel2map |
| 目标预测 | 运动模型轨迹预测 | AstraDroneOpen target_prediction |
| 坐标系转换 | IMU→欧拉角、RTK→FLU、pose↔tf | AstraDroneOpen 相关工具 |

> 设计决策：坐标系转换放感知层（涉及坐标语义理解）；感知算法采用 SpireCV "统一接口+多后端"模式。

### 1.3 执行层功能划分

| 子模块 | 功能 | 来源参考 |
|--------|------|----------|
| Offboard 控制 | 位置/速度/姿态指令生成 → MAVLink → PX4 | Prometheus uav_control（最成熟） |
| 全局路径规划 | A* / RRT* | Prometheus global_planner |
| 局部轨迹规划 | EGO-Planner + B 样条优化 | Prometheus ego_planner_swarm；AstraDroneOpen ego-planner |
| 避障控制 | 基于感知的实时避障 | AstraDroneOpen rc_obstacle_avoidance |
| 精确降落 | 视觉标志降落闭环 | AstraDroneOpen astra_auto_land |
| 云台控制 | 多型号云台伺服（工厂模式） | SpireCV gimbal_ctrl |
| 任务状态机 | 起飞→搜索→跟踪→降落→返航编排 | Prometheus future_aircraft |
| 集群编队控制 | 多机编队保持 | Prometheus swarm_*；AstraDroneOpen Swarm |
| 无人车控制 | 异构协同（可选） | Prometheus ugv_control |

> 设计决策：控制核心以 Prometheus uav_control 为基础移植 ROS2；规划器从 AstraDroneOpen ego-planner 出发；SpireCV 云台作为独立 .so 引入。

### 1.4 应用接口层功能划分

| 子模块 | 功能 | 来源参考 |
|--------|------|----------|
| 统一 C++ SDK API | 聚合头文件，一个 include 调用全部能力 | SpireCV sv_world.h 模式 |
| ROS2 Service/Action 接口 | 标准化对外接口 | Prometheus prometheus_msgs |
| Python 绑定 | pybind11 / rclpy 接口 | 全新设计 |
| 任务脚本引擎 | YAML/Python 定义任务序列 | Prometheus Experiment/config 思路 |
| 仿真启动器 | 一键启动 Gazebo + PX4 SITL | AstraDroneOpen simulation |
| 参数配置中心 | 统一 JSON/YAML 参数 | SpireCV params；Prometheus config |
| Demo 案例库 | 开箱即用示例 | Prometheus tutorial_demo |
| Web 地面站接口 | HTTP/WebSocket（可选） | 全新设计 |

### 1.5 技术选型

| 决策点 | 推荐 |
|--------|------|
| MAVLink 桥接 | mavros2（初期）→ px4_ros2_cpp（逐渐迁移） |
| 感知算法 SDK | SpireCV 为核心，独立 .so |
| 控制与规划 | Prometheus 逻辑蓝本，移植 ROS2 |
| SLAM | FAST-LIO2 |
| 云台控制 | SpireCV libsv_gimbal.so |
| 自定义消息 | prometheus_msgs 蓝本 → ROS2 .msg/.srv/.action |
| 仿真 | AstraDroneOpen simulation 体系 |

---

## 2. 四层下的小层划分（4 大层 13 子层）

```
应用接口层：A1 SDK聚合 → A2 服务接口 → A3 任务编排
执行层：  E1 任务状态机 → E2 规划 → E3 控制
感知层：  P1 预处理 → P2 检测/识别 → P3 跟踪/状态估计 → P4 融合/语义
通信层：  C1 硬件驱动 → C2 协议桥接 → C3 媒体流
```

### 2.1 通信层（硬件→协议→媒体）

| 子层 | 职责 | 输入 → 输出 |
|------|------|------------|
| **C1 硬件驱动层** | 对接硬件 SDK，字节流→结构化数据 | USB/串口字节流 → 点云/图像/IMU/GPS/遥控器值 |
| **C2 协议桥接层** | ROS2 内外数据格式转译 | MAVLink/UDP → ROS2 Topic/Service/Action |
| **C3 媒体流层** | 视频编码推流与持久化 | 图像帧 → RTSP 流/MP4 |

依赖：C2→C1，C3→C1；C2 与 C3 无直接依赖。

### 2.2 感知层（预处理→检测→跟踪→融合）

| 子层 | 职责 | 输入 → 输出 |
|------|------|------------|
| **P1 预处理层** | 传感器数据时空对齐 | 原始数据+标定 → 统一坐标系传感器帧 |
| **P2 检测/识别层** | "画面里有什么" | 图像帧 → 检测框列表 |
| **P3 跟踪/状态估计层** | "怎么动，我在哪" | 检测框序列 → 轨迹+自身位姿 |
| **P4 融合/语义层** | "离我多远，3D 在哪" | 检测框+点云+深度 → 3D 坐标/栅格/可通行区 |

规则：每层只依赖上层；同子层内模块可互相调用；P2 检测器并行独立。

### 2.3 执行层（决策粒度由粗到细）

| 子层 | 职责 | 输入 → 输出 | 频率 |
|------|------|------------|------|
| **E1 任务状态机层** | "此刻执行什么阶段" | 任务脚本+感知事件+遥控器 → 阶段目标 | 1-10Hz |
| **E2 规划层** | "可飞的路径" | 阶段目标+障碍物 → 全局路径+局部轨迹 | 10-50Hz |
| **E3 控制层** | "电机执行的指令" | 轨迹点+状态 → MAVLink setpoint | 50-200Hz |

### 2.4 应用接口层（抽象级别由低到高）

| 子层 | 职责 | 面向 |
|------|------|------|
| **A1 SDK 聚合层** | 一个 include/import 用全部能力 | 开发者 |
| **A2 服务接口层** | SDK 能力暴露为 ROS2 标准化接口 | ROS2 节点 |
| **A3 任务编排层** | Service/Action 编排成完整任务 | 用户/飞手 |

规则：A3 调 A2 不直调 A1；A2 调 A1 不直操作 E/P 层；外部节点可直接调 A2。

### 2.5 子层与来源平台对应

| 子层 | 主要借鉴 |
|------|----------|
| C1 | AstraDroneOpen 驱动包 |
| C2 | Prometheus communication + mavros2 |
| C3 | SpireCV video_io |
| P1 | AstraDroneOpen 坐标/时间工具 |
| P2 | SpireCV 各检测模块 |
| P3 | SpireCV mot/sot + FAST_LIO |
| P4 | AstraDroneOpen 融合 + SpireCV mde |
| E1 | Prometheus future_aircraft 状态机 |
| E2 | Prometheus motion_planning + ego_planner |
| E3 | Prometheus uav_control + SpireCV gimbal_ctrl |
| A1 | SpireCV sv_world.h 聚合头文件 |
| A2 | Prometheus prometheus_msgs（ROS2 改造） |
| A3 | Prometheus tutorial_demo + 仿真体系 |

---

## 3. ROS2 工作空间目录结构

```
easyfly_ws/
├── README.md
├── easyfly_env.bash
├── build_all.bash / build_layer.bash
└── src/
    ├── easyfly_common/              # 跨层公共定义（最先编译）
    │   ├── easyfly_msgs/            # 11 msg + 6 srv + 6 action
    │   └── easyfly_utils/           # geometry/math/time/param_loader/crc
    │
    ├── communication/
    │   ├── c1_drivers/              # livox/realsense/serial/rc/gps 驱动
    │   ├── c2_protocol/             # mavlink_bridge/udp/mesh
    │   └── c3_media/                # video_streamer/video_recorder
    │
    ├── perception/
    │   ├── p1_preprocess/           # camera_calib/coord_transform/pointcloud_filter/time_sync
    │   ├── p2_detection/            # object/landing/apriltag/ellipse/color_line/reid
    │   ├── p3_tracking/             # mot/sot/fast_lio/target_prediction
    │   └── p4_fusion/               # lidar_camera/depth/pixel_to_3d/semantic_map
    │
    ├── execution/
    │   ├── e1_state_machine/        # mission_fsm（8状态+转移条件+安全监控）
    │   ├── e2_planning/             # global/local/trajectory_optimizer/swarm
    │   └── e3_control/              # flight/gimbal/obstacle_avoidance/precision_landing
    │
    ├── application/
    │   ├── a1_sdk/                  # core/pybind/params
    │   ├── a2_services/             # mission_srvs/perception_srvs
    │   └── a3_mission/              # mission_scripts/demos/sim_launcher
    │
    ├── easyfly_ui/
    │   ├── easyfly_ui_bridge/       # ROS2 ↔ UI 桥接
    │   ├── easyfly_desktop/         # Qt6 + QML
    │   └── easyfly_web/             # Vue3 + WebSocket
    │
    ├── simulation/                  # gazebo_models/worlds/plugins/px4_sitl
    └── third_party/                 # livox_sdk2/librealsense/geographic_lib/nlopt/nlohmann_json
```

### 3.1 消息接口清单（23 个）

- **msg (11)**：UAVState, UAVCommand, DetectionInfo, DetectionInfoArray, TrackInfo, TrackInfoArray, ObstacleInfo, ObstacleInfoArray, GimbalState, SwarmInfo, MissionStatus
- **srv (6)**：ArmMotors, SetFlightMode, GetObstacles, TriggerLanding, SetGimbalAngle, QueryParams
- **action (6)**：Takeoff, Land, GoToWaypoint, TrackTarget, SearchArea, ExecuteMission

### 3.2 包粒度决策

| 级别 | 是否独立成包 |
|------|-------------|
| 算法后端（TensorRT/OpenVINO） | ❌ 编译宏切换 |
| 算法变体（YOLOv7/v8, ByteTrack/SORT） | ❌ 同包内子目录 |
| 不同功能（检测 vs 降落检测） | ✅ 独立 package |
| 不同硬件（Livox vs RealSense） | ✅ 独立 package |
| Demo 程序 | ❌ 一个包多个入口 |

### 3.3 编译方式

```bash
colcon build --symlink-install                          # 全量
colcon build --packages-up-to c3_media                  # 通信层
colcon build --packages-up-to p4_fusion                 # 感知层
colcon build --packages-up-to e3_control                # 执行层
colcon build --packages-up-to a3_mission                # 应用层
```

13 个子层均为 metapackage，支持按子层/大层/单包编译。

---

## 4. EasyFly UI 设计

UI 定位：四层架构之上的"人机交互层"，五大功能域（顶部 Tab 页签）。

### 4.1 功能域总览

| 模块 | 定位 |
|------|------|
| **飞控仪表大盘** | 飞行中最重要的实时监控页（仿 GCS） |
| **任务中心** | 任务全生命周期：编辑→仿真→执行→监控 |
| **感知视窗** | 实时查看无人机"看到了什么" |
| **系统管理** | 配置、校准、参数管理 |
| **日志回放** | 飞行后复盘、问题定位、数据导出 |

### 4.2 飞控仪表大盘

- **主 HUD**：地平仪（pitch/roll）、航向罗盘（yaw+home 方向）、高度/速度条（绿黄红阈值）、位置/GPS 星数/HDOP、OSD 叠加（飞行模式/解锁/failsafe）
- **快捷指令面板**：解锁/锁定/起飞/降落/悬停/返航、飞行模式切换、紧急停机（红色二次确认）
- **3D 姿态预览**：实时渲染姿态位置，可拖拽旋转

### 4.3 任务中心

- **地图+任务编辑器**：卫星地图底图，航点类型（航点/搜索/跟踪/降落/云台/投放/等待/条件跳转），航点参数编辑
- **任务进度面板**：当前阶段、完成百分比、剩余时间、下一航点预览
- **集群编队编辑器**：编队类型（一字/楔形/圆形/自定义）、领机指定、从机相对位置、编队起飞/变换/降落

### 4.4 感知视窗

- **主相机画面**：实时视频流+检测框（类别+置信度）、跟踪 ID+轨迹线
- **图层开关**：检测框/跟踪ID/深度图/SLAM点云/融合视图/轨迹预测/降落标志
- **点云 3D 视图**：FAST-LIO2 实时建图、ESDF 地图、规划路径叠加
- **状态栏**：延迟、FPS、分辨率；截图/录像按钮

### 4.5 系统管理

- **参数配置**：树形导航（飞控参数/传感器校准/控制参数/感知参数/平台配置），参数表格编辑，搜索，保存/读取
- **校准向导**：加速度计→陀螺仪→磁力计→地平线，姿态图示引导，进度提示
- **软件版本与更新**：各 package 版本号，一键 git pull + colcon build
- **连接管理**：MAVLink 串口/波特率、视频流地址、多机状态、心跳监控

### 4.6 日志回放

- **日志列表**：日期/时长/起降点/评分/操作（回放/导出），分页
- **回放播放器**：播放控制+进度条，地图回放（轨迹线）+视频回放（同步），事件标记，数据通道开关（姿态/位置/输入/电机/传感器）
- **数据导出**：rosbag→视频（OSD）、飞行日志→CSV/JSON、检测结果→COCO 格式（训练闭环）

### 4.7 UI 技术选型

| 方案 | 适用场景 |
|------|----------|
| **Qt6 + QML（主）** | 桌面地面站，跨平台，高刷新率仪表 |
| Web (Vue3 + WebSocket)（备） | 移动端轻量地面站 |

### 4.8 UI 与架构对接

UI 只通过 A2 服务接口层交互：

| UI 模块 | A2 接口 |
|---------|---------|
| 飞控大盘 | 订阅 UAVState；调用 ArmMotors/SetFlightMode |
| 任务中心 | ExecuteMission.action（feedback 推送进度）、GoToWaypoint.action |
| 感知视窗 | 订阅 DetectionInfoArray/TrackInfoArray/压缩图像 topic |
| 系统管理 | 参数读写 service、config 配置文件 |
| 日志回放 | rosbag 文件 + 日志数据库 |

---

## 5. 开发阶段顺序

```
阶段〇  基础设施        空架子能编译
阶段一  通信+仿真       遥控器能飞，Gazebo 能仿真
阶段二  控制闭环        Offboard 自主悬停，航点飞行
阶段三  感知流水线      看得见、跟得住、知道自己在哪
阶段四  规划+避障       能绕障飞行，自主降落
阶段五  任务+应用       SDK 完整，一键任务执行
阶段六  UI+媒体+打磨    地面站可用，推流录像全通
```

### 5.1 阶段〇：基础设施（1-2 周）

- 目录骨架 + 全部 metapackage 空壳
- easyfly_msgs 全部 23 个接口定义
- easyfly_utils 工具库
- CI 配置
- **验收**：`colcon build` 全绿，`colcon test` 通过
- **关键**：消息是系统"语言"，接口契约必须先定

### 5.2 阶段一：通信层+仿真（3-4 周）

- easyfly_serial → easyfly_mavlink_bridge → easyfly_rc_receiver
- 真机联调：遥控器→飞控→ROS2 topic 数据闭环
- simulation 4 包 + easyfly_sim_launcher 一键仿真
- livox/realsense/gps 驱动
- **验收**：仿真中遥控器操控飞行，/uav_state 有数据

### 5.3 阶段二：控制闭环（3-4 周）

- easyfly_flight_control（offboard/position/velocity/mixer）
- 仿真验证 GoToWaypoint action
- easyfly_mission_fsm（8 状态+4 转移条件+安全监控）
- easyfly_mission_srvs（提前做，UI 唯一入口）
- easyfly_precision_landing（先用仿真假数据）
- **验收**：发 action 自主起飞→航点→降落

### 5.4 阶段三：感知流水线（6-8 周，最长阶段）

- **3A 预处理+检测**：camera_calib/coord_transform/time_sync → object_detection（双后端）/landing/apriltag
- **3B 跟踪+SLAM**（与 3A 并行）：fast_lio → mot/sot/target_prediction
- **3C 融合**（依赖 3A+3B）：pointcloud_filter → lidar_camera_fusion/depth/pixel_to_3d → semantic_map
- **验收**：detection/track/obstacle topic 有数据，RViz2 可见 SLAM 点云

### 5.5 阶段四：规划+避障+云台（3-4 周）

- global_planner（A*/RRT*）→ local_planner（ego-planner 四模块）→ trajectory_optimizer（MinSnap）
- obstacle_avoidance → gimbal_control（工厂模式+伺服+跟踪）
- 联调：规划+避障+飞行控制
- **验收**：Gazebo 放障碍物，无人机绕障飞行
- **注意**：依赖链最长路径 common→C1→P1→P3→P4→E2

### 5.6 阶段五：应用层+任务系统（2-3 周）

- easyfly_core（SDK 聚合头文件）→ easyfly_params → perception_srvs
- mission_scripts（YAML 解析引擎+3 示例任务）→ demos（5 个）
- 补全 P2 剩余模块（ellipse/color_line/reid）→ pybind → swarm_planner + mesh_comm
- **验收**：一个 YAML 驱动完整任务（起飞→搜索→跟踪→降落）

### 5.7 阶段六：UI+媒体+打磨（2-3 周）

- ui_bridge → desktop（大盘优先逐步加功能）
- video_streamer + video_recorder（C3）
- UI 感知视窗→任务中心→日志回放→系统管理
- 真机全链路测试+稳定性压测 → web 地面站 → 文档
- **验收**：桌面地面站全功能可用
- **注意**：C3 放最后——推流是锦上添花，不阻塞主链路

### 5.8 团队分工（3-4 人，总周期压缩至 12-16 周）

| 角色 | 阶段〇~二 | 阶段三 | 阶段四~六 |
|------|----------|--------|-----------|
| A：通信+控制 | C1/C2 + E3 + 仿真 | 协助联调 | E2 规划+避障 |
| B：感知 | P1 预处理 | P2+P3+P4 全部 | 协助联调 |
| C：应用+UI | 消息定义 | A1+A2 | A3+UI |

### 5.9 风险提示

| 风险 | 应对 |
|------|------|
| mavros2 与 PX4 1.16 兼容性 | 阶段一第一时间验证，不稳换 px4_ros2_cpp |
| FAST-LIO2 的 ROS2 版本 | 阶段三前确认可用性 |
| EGO-Planner 从 ROS1 迁移 | 工作量最大，阶段四留足 buffer |
| TensorRT/OpenVINO 版本 | 先用 OpenCV DNN 跑通再适配后端 |
| Gazebo Classic 寿命 | apt 版短期够用，长期迁 Gazebo Ignition |

**核心策略**：先跑通"通信→控制→仿真"最短链路（阶段〇-二）让飞机能飞；再做感知（阶段三）让飞机能看；再做规划（阶段四）让飞机能绕；最后封装 SDK 和 UI（阶段五-六）让用户能用。

---


