# EasyFly 项目进度与结构

> 自主无人机软件平台 | PX4 1.16 · Ubuntu 22.04 · ROS2 Humble · Gazebo Classic
>
> 本文档记录 EasyFly 的整体架构、已完成工作与待办计划，随开发持续更新。

---

## 一、项目定位

融合 Prometheus（阿木实验室全栈无人机平台）、AstraDroneOpen（模块化多旋翼系统）、SpireCV（边缘感知 SDK）三大开源项目优势，重构的一套四层架构自主无人机软件平台。

### 技术栈

| 项 | 选型 |
|----|------|
| 飞控固件 | PX4 1.16 |
| 操作系统 | Ubuntu 22.04 |
| 中间件 | ROS2 Humble |
| 仿真 | Gazebo Classic + PX4 SITL |
| 主语言 | C++（部分 Python 绑定） |

---

## 二、四层架构总览

```
┌─────────────────────────────────────────────────────────┐
│ ④ 应用接口层 (Application Interface)                     │
│    A1 SDK 聚合 · A2 服务接口 · A3 任务编排               │
├─────────────────────────────────────────────────────────┤
│ ③ 执行层 (Execution)                                     │
│    E1 任务状态机 · E2 规划 · E3 控制                     │
├─────────────────────────────────────────────────────────┤
│ ② 感知层 (Perception)                                    │
│    P1 预处理 · P2 检测识别 · P3 跟踪/状态估计 · P4 融合  │
├─────────────────────────────────────────────────────────┤
│ ① 通信层 (Communication)                                 │
│    C1 硬件驱动 · C2 协议桥接 · C3 媒体流                 │
└─────────────────────────────────────────────────────────┘
    硬件层（支撑，不属于四层）
    PX4 飞控 · 机载计算机 · 传感器 · 云台
```

### 13 个子层划分

| 大层 | 子层 | 职责 |
|------|------|------|
| 通信层 C | C1 硬件驱动 | 传感器 SDK、串口、遥控器、GPS |
| | C2 协议桥接 | MAVLink、UDP、机间通信 |
| | C3 媒体流 | 视频推流、录制 |
| 感知层 P | P1 预处理 | 标定、坐标变换、时空对齐 |
| | P2 检测识别 | 目标检测、标志检测、ReID |
| | P3 跟踪/状态估计 | MOT、SOT、SLAM |
| | P4 融合/语义 | 激光-视觉融合、深度、3D投影 |
| 执行层 E | E1 任务状态机 | 任务调度、异常处理 |
| | E2 规划 | 全局/局部规划、轨迹优化 |
| | E3 控制 | 飞行控制、云台、降落 |
| 应用层 A | A1 SDK 聚合 | 统一头文件、Python 绑定 |
| | A2 服务接口 | ROS2 Service/Action 封装 |
| | A3 任务编排 | 任务脚本、Demo、仿真启动 |

---

## 三、目录结构

```
easyfly_ws/
├── README.md
├── build_all.bash            # 全量编译
├── build_layer.bash          # 按层编译
├── easyfly_env.bash          # 环境初始化
└── src/
    ├── easyfly_common/       # 跨层公共定义
    │   ├── easyfly_msgs/     #   msg/srv/action 接口契约
    │   └── easyfly_utils/    #   工具库
    ├── communication/        # ① 通信层
    │   ├── c1_drivers/       #   easyfly_serial / rc_receiver / gps_receiver
    │   │                     #   livox_ros_driver2 / realsense2_camera
    │   ├── c2_protocol/      #   easyfly_mavlink_bridge / udp_protocol / mesh_comm
    │   └── c3_media/         #   easyfly_video_streamer / video_recorder
    ├── perception/           # ② 感知层
    │   ├── p1_preprocess/    #   camera_calib / coord_transform / pointcloud_filter / time_sync
    │   ├── p2_detection/     #   object_detection / landing / apriltag / ellipse / color_line / reid
    │   ├── p3_tracking/      #   fast_lio / multi_object_tracking / single_object_tracking / target_prediction
    │   └── p4_fusion/        #   lidar_camera_fusion / depth_estimation / pixel_to_3d / semantic_map
    ├── execution/            # ③ 执行层
    │   ├── e1_state_machine/ #   easyfly_mission_fsm
    │   ├── e2_planning/      #   global_planner / local_planner / trajectory_optimizer / swarm_planner
    │   └── e3_control/       #   flight_control / gimbal_control / obstacle_avoidance / precision_landing
    ├── application/          # ④ 应用接口层
    │   ├── a1_sdk/           #   easyfly_core / easyfly_params / easyfly_pybind
    │   ├── a2_services/      #   easyfly_mission_srvs / easyfly_perception_srvs
    │   └── a3_mission/       #   mission_scripts / demos / sim_launcher
    ├── easyfly_ui/           # UI（独立于四层）
    │   ├── easyfly_ui_bridge/  #  UI ↔ ROS2 桥接
    │   ├── easyfly_desktop/    #  Qt6 + QML 桌面地面站
    │   └── easyfly_web/        #  Web 地面站
    ├── simulation/           # 仿真支撑
    │   ├── easyfly_gazebo_models / worlds / plugins
    │   └── easyfly_px4_sitl
    └── third_party/          # 第三方依赖
        ├── librealsense / livox_sdk2
        └── geographic_lib / nlopt / nlohmann_json
```

---

## 四、已完成工作

### 阶段〇：基础设施 ✅

| 项 | 状态 |
|----|------|
| 目录骨架（4 层 + 13 子层 + UI + 仿真 + 第三方） | ✅ |
| easyfly_msgs：11 msg + 6 srv + 6 action | ✅ |
| easyfly_utils：geometry/math/time/param_loader/crc | ✅ |
| colcon build 全绿 | ✅ |

### 阶段一：通信层 ✅

| 包 | 状态 | 说明 |
|----|------|------|
| easyfly_serial | ✅ | POSIX 串口封装，含单元测试 |
| easyfly_rc_receiver | ✅ | mavros RCIn → ROS2 topic |
| easyfly_mavlink_bridge | ✅ | 8 路 mavros 话题聚合 /uav_state + 4 种控制模式编码器 + arm/mode 服务 |
| livox_ros_driver2 | ✅ | 官方 MID-360s 驱动，输出 /livox/lidar |
| realsense2_camera | ✅ | tag 4.56.4，输出 color/depth/camera_info |

### 阶段二：控制闭环 ✅

| 包 | 状态 | 说明 |
|----|------|------|
| easyfly_flight_control | ✅ | PID 控制器，Takeoff/Land/GoToWaypoint 3 个 Action |
| easyfly_mission_fsm | ✅ | 任务解析 + 状态机 + 电池安全监控 |

**已实现数据流**：

```
Mission YAML → mission_fsm → flight_controller → /uav_command
    → mavlink_bridge(encoder) → mavros → PX4
PX4 → mavros → mavlink_bridge(decoder) → /uav_state
    → 反馈给 mission_fsm + flight_controller
```

### 阶段三 M0：仿真传感器就绪 ✅（2026-09）

| 项 | 状态 | 说明 |
|----|------|------|
| easyfly_iris.sdf 深度相机 | ✅ | D435i 风格前视相机，libgazebo_ros_camera（color 30Hz + aligned_depth 32FC1 + points），话题对齐实机 realsense 驱动 |
| livox_laser_simulation 插件 | ✅ | ROS2 移植版（源: AstraDroneOpen/livox_laser_simulation），输出 livox_ros_driver2/CustomMsg（20000 点/帧 ≈10Hz），CSV 非重复扫描 |
| mid360 仿真模型 | ✅ | 水平安装，/livox/lidar + /livox/imu（200Hz），复用 31MB 官方外观 mesh |
| perception_demo.world | ✅ | 验收场景：4 行人 + 2 消防车 + 4 纸箱，沿 +X 航线布置（COCO 类别可检目标） |
| px4_sitl / perception_sitl launch | ✅ | 修复 PX4 路径（~/PX4-Autopilot-1.16.1，PX4_DIR 可覆盖）；perception_sitl 一键启动 Gazebo+PX4+RViz2 |
| RViz2 感知调试配置 | ✅ | rviz/perception.rviz（color/depth 图像 + 深度点云视图） |

**关键经验（踩坑记录）**：
1. Ubuntu 把 RayPlugin 基类拆到 `gazebo-plugin-base` 包（`gazebo-11/plugins/libRayPlugin.so`），插件需显式链接；
2. ROS2 的 `libgazebo_ros_init.so` 是 SystemPlugin，必须 `gzserver -s` 加载，不能写在 world 文件（ROS1 写法会报 incorrect plugin type）；
3. `GAZEBO_PLUGIN_PATH` 需含 `/opt/ros/humble/lib`，PX4 插件运行需 `LD_LIBRARY_PATH` 指向其 build_gazebo-classic；
4. gazebo_ros_imu_sensor 固定发布 `~/out`，用 `<remapping>~/out:=imu</remapping>` 改话题名；
5. **相机安装位姿必须越过 iris.stl 视觉包络**：base_link 视觉 mesh 比 collision (0.47×0.47×0.11) 大（4 机臂外伸 + 旋翼），相机原设 (0.12, 0, 0.05) 完全被机身挡。现改 (0.25, 0, 0.22) 机头上方平视，可看到上方场景；视野下半仍偏近（视觉包络所致，M2 跑检测时再评估遮挡对识别的影响）。

### 阶段三 M1：P1 预处理就绪 ✅（2026-09）

| 项 | 状态 | 说明 |
|----|------|------|
| easyfly_camera_calib | ✅ | 传感器内外参统一管理 (`config/sensors.yaml`)，`calib_tf_publisher` 静态 TF 发布（base_link→camera_link→optical, base_link→livox_frame）；`camera_info_checker` 启动时校验 Gazebo 内参与 YAML 一致性 |
| easyfly_coord_transform | ✅ | `odom_tf_publisher` 订阅 `/uav_state` 发布 odom→base_link 动态 TF + `/odom`；`coord_utils.hpp` 提供 rpy↔quat、像素→3D、ENU↔FLU、FLU↔光学系 工具（供 M2/M5 复用） |
| 集成 | ✅ | `perception_sitl.launch.py` 加入 P1 节点；RViz 增加 TF 显示与 fixed_frame=odom |

**TF 树（M1 完成时）**：
```
odom
└── base_link           ← coord_transform (50Hz)
    ├── camera_link     ← camera_calib (static)
    │   ├── camera_color_optical_frame   (static)
    │   └── camera_depth_optical_frame   (static)
    └── livox_frame     ← camera_calib (static)
```

**关键经验**：
- TF `parent→child` 旋转是 "child 系向量 → parent 系向量"，FLU→optical 的 rpy = `(-π/2, 0, -π/2)`（方向容易搞反，验证方法是看 rotation matrix 列1 是否等于 (0,0,1)——即光轴 z 前 = 机体 x 前）；
- Gazebo depth camera 有两组话题：`/camera/*/image_raw`（BGR 渲染流，受 `<format>` 影响）和 `/camera/*/depth/image_raw`（32FC1 真深度），M2/M5 必须订阅后者；
- 点云 point_step 默认 32 字节（x,y,z,rgb），按 16 解析会错位；
- `/uav_state` 姿态来自 `/mavros/local_position/pose`（ENU+FLU），可直接用于 odom→base_link。

### 阶段三 M2：目标检测就绪 ✅（2026-09）

| 项 | 状态 | 说明 |
|----|------|------|
| conda 环境 `cv_easyfly` | ✅ | python 3.10 + torch 2.8.0+cu128 + ultralytics 8.3.9 + onnxruntime-gpu 1.23.2（模型导出/训练/验证用，运行时检测节点不依赖） |
| yolo11n ONNX | ✅ | 官方 COCO 80 类权重导出（opset 12, IR 10, 640），存 `easyfly_ws/models/` |
| onnxruntime C++ SDK | ✅ | 1.23.2 gpu 版入 `third_party/onnxruntime/`，运行库随包安装（RPATH $ORIGIN，部署自包含） |
| easyfly_object_detection | ✅ | SpireCV 式 Base/Impl 架构 + **运行时后端工厂**（onnx 已实现；tensorrt/openvino 预留 src/cuda、src/intel）；OnnxRuntime CUDA EP（失败自动回退 CPU）；自实现 letterbox/NMS；推理独立线程 + 丢帧节流；warmUp 预热 |
| 数据流 | ✅ | `/camera/color/image_raw` → `/detections` (DetectionInfoArray 归一化 bbox, track_id 留 M4, position 留 M5) + `/detections_debug_image`（有订阅才发） |
| 换模型接口 | ✅ | `config/detection.yaml` 全配置化（模型路径/类别表/imgsz/阈值/话题）——自定义模型 = 换 ONNX + 改 YAML，零代码 |

**验收数据（仿真实测）**：GPU 推理 3.5ms（纯）/ 端到端 5ms，节点 31Hz；场景 5 目标（3 person + 2 bus=消防车）全检出；**C++ 与 Python 基准逐框逐值一致**；CPU EP 回退 49.7ms（20fps）可用；M1 遗留的相机视野遮挡实测**不影响检测**。

**关键经验**：
- **onnx 1.22 导出的 ONNX 默认 IR version 13，超过 onnxruntime 1.23 支持上限（11）**——导出后须降 `model.ir_version=10` 再保存（**自定义杂草模型导出时同样要处理**）；
- ORT 1.23 C++ `CreateTensor` 需要 `Ort::MemoryInfo` 参数（老版本 API 无此要求，迁移代码注意）；
- YOLO11 输出布局 `[1, 84, 8400]`（4 box + 80 类置信度，列优先），非 NMS 版导出需自做按类别 NMS；
- 系统 OpenCV 4.5.4 仅用 resize/cvtColor/rectangle 完全够用，推理走 onnxruntime 与 OpenCV DNN 无关。

### 阶段三 M3：FAST-LIO SLAM 就绪 ✅（2026-09）

| 项 | 状态 | 说明 |
|----|------|------|
| 方案变更 | ✅ | 弃自研移植，改用 **hku-mars/FAST_LIO 官方 ROS2 分支**（Ericsii 移植，推荐 Humble，原生支持 livox_ros_driver2/CustomMsg）；用户下载 zip 后集成 |
| fast_lio 集成 | ✅ | `p3_tracking/fast_lio`（保留上游包名，易同步）；ikd-Tree 子模块从 AstraDroneOpen 同源补齐（完全兼容）；删除残留依赖 common_interfaces |
| 仿真配置 | ✅ | config/mid360.yaml：话题/外参与 M0 天然对齐；blind 0.3、关闭外参在线估计、不存 PCD |
| easyfly_fast_lio_integration | ✅ | **map→odom TF 节点**（REP-105）：订阅 /Odometry(SLAM)+/odom(mavros)，T_map_odom=T_map_base×T_odom_base⁻¹，指数平滑；独立包不侵入上游源码 |
| 一键启动 | ✅ | perception_sitl.launch.py 现为全链路：Gazebo+PX4+mavros+P1(TF)+P2(检测)+P3(SLAM)；修复潜伏的 `PythonLaunchDescriptionSource` import 错误；RViz fixed=map + SLAM 点云/轨迹显示 |
| colcon_defaults.yaml | ✅ | 新增，base-paths 限定 src/（Platform/ 内 ROS1 参考包与本区包名冲突） |

**验收数据（headless 实测）**：静止零漂（<0.1m）；连续前飞 10m 误差 **2.6cm**；No Effective Points = 0；全链路 /uav_state 20Hz + /Odometry 8.1Hz；TF 树 map→odom→base_link→camera/livox 各段均验证。

**关键经验（重要踩坑）**：
1. **FAST-LIO IMU_init 必须在静止状态执行**：测试脚本把无人机 spawn 到空中→自由落体+弹跳→mean_acc 被污染（norm=0.31 而非 9.8）→加速度放大 32 倍→预积分爆炸到 10⁴m。修复=静止贴地启动。真实流程（launch 顺序）天然满足；
2. **gz model teleport 不能测试 SLAM**：瞬移使 IMU（无物理过程）与 LiDAR（场景突变）矛盾，跟踪即崩。连续小步移动可测平移（精度厘米级）；旋转测试需 PX4 真实控制；
3. **多源 TF 时间戳毫秒差**：map→odom(SLAM 10Hz) 与 odom→base_link(mavros 20Hz) 最新时间戳不完全对齐，`lookup_transform(latest)` 可能报 extrapolation——RViz 显示正常（容忍），严格查询应指定时刻；
4. `/tf_static` 是 latched(transient_local) QoS，用默认 QoS 订阅收不到，验证静态 TF 要用 transient_local 或直接看节点日志；
5. 上游 ROS2 分支的 ikd-Tree 是 git submodule（fast_lio 分支），zip 下载不含内容——从 AstraDroneOpen 同源库补齐可用（零 ROS 依赖的模板库）；
6. 长时间反复 headless 测试需注意残留 gzserver 进程（端口占用会连到旧实例，时间戳错乱极难排查）与内存压力（全链路 ~10GB+，异常进程被 OOM kill 表现为 137 退出码）。

### 阶段三 M4：多目标跟踪就绪 ✅（2026-09）

| 项 | 状态 | 说明 |
|----|------|------|
| SORT 核心算法 | ✅ | 纯自实现零依赖（kalman.hpp 8维匀速模型 / hungarian.hpp O(n³) 分配 / sort.hpp 生命周期管理），header-only，含合成数据单测（test/test_sort.cpp：交叉运动/遮挡10帧ID保持/类别隔离/速度估计 6 项断言全过） |
| easyfly_multi_object_tracking | ✅ | 组件节点：/detections → SORT → /tracks (TrackInfoArray)；tracking.yaml 全配置（iou/max_lost/min_hits/max_tracks/target_classes 类别过滤）；/tracks_debug_image 黄框+ID 叠加 |
| 集成 | ✅ | perception_sitl.launch.py 全链：Gazebo+PX4+mavros+P1(TF)+P2(检测)+P3(SLAM)+P4(跟踪) |

**验收数据（仿真实测）**：静止 96 帧恰好 6 个稳定 ID（4 person + 2 truck，无跳变无重建）；前飞 12m 后旧目标 ID 保持（1/4/5 不变）、出视野目标正确删除、新目标新 ID 递增不复用；跟踪零性能瓶颈（与检测同频）。

**关键经验**：
- **自写卡尔曼的 F 矩阵低级错误**：只给位置行设了 F[i][i]=1 和 F[i][i+4]=1，速度行对角 F[4][4]..F[7][7] 漏设 → 预测时速度状态被清零、P 速度方差归零、增益恒 0，症状是"位置能跟但速度恒 0、预测不前进"。**教训：手写 KF 必须先用 numpy 参考实现对拍**（当时 numpy 三行就暴露了 vcx=3.99 vs C++ 0.0 的差异）；
- SORT 关联必须按类别隔离（类别不同的代价设为必然拒绝值），否则交叉运动时 person/car 互抢 ID。

### 阶段三 M5：像素转 3D 就绪 ✅（2026-09）

| 项 | 状态 | 说明 |
|----|------|------|
| easyfly_msgs 新增 Target3D/Target3DArray | ✅ | 带 track_id/类别/世界系位置/distance/像素坐标/position_valid 的 3D 目标契约（现为 13 msg + 6 srv + 6 action） |
| easyfly_pixel_to_3d | ✅ | /tracks(M4) + 深度图(M0) + TF(M1/M3) → /target_positions + /target_markers (MarkerArray: 按类别配色球+ID+距离文字)；深度采样: bbox 区域自适应下采样+中位数+有效比例阈值；内参从 camera_info 实时获取 |
| 集成 | ✅ | perception_sitl 全链: Gazebo+PX4+mavros+P1+P2+P3+P4+P5；RViz 加 TargetMarkers 显示 |

**验收数据（仿真实测）**：轻量链路 person_1 误差 **0.24m**、person_2 **0.31m**（验收线 0.5m）；全链路（真实 mavros TF + map 系）person_1 **0.26m**；深度超范围目标正确标记 position_valid=false 不输出错误数据；~8Hz 稳定输出。

**关键经验**：
- **Gazebo 相机插件的 camera_info 是 VOLATILE QoS**——用 transient_local 订阅会 "incompatible QoS" 一条都收不到（日志有 WARN 但极易忽略），订阅 Gazebo 话题一律用普通 QoS；
- **TF 查询需双路容错**：先按消息时间戳查（精确时空对齐），失败（静态 TF stamp=0 引发 TF_OLD_DATA/extrapolation）再回退 latest——静态外参链用 latest 安全，本条对一切"消费 TF 的节点"通用；
- 深度图 32FC1 中 bbox 中心单像素采样极脆弱（遮挡/混合像素），中位数+下采样是性价比最高的鲁棒方案；
- headless 注入 /uav_state 模拟 mavros 时，时间戳与 /clock 的微小偏差会被 tf2 以 TF_OLD_DATA 拒收——**注入测试天然测不了跨 TF 链功能，最终验收必须走真实 mavros 全链路**（本里程碑验证了这一点）。

### P0 控制安全修复 ✅（2026-09-13，全项目审查后实施）

依据 question.md 审查结论，修复控制链路 10 个 P0 级问题（flight_control / mission_fsm / mavlink_bridge）：

- **安全兜底**：低电量自动 RTL（直切 PX4，不依赖自家链）；Land 超时严禁空中 disarm；Takeoff/Waypoint deadline 超时保护；
- **取消语义**：航点/起飞/降落取消后**就地悬停**（守卫反馈：|fb−ramp|<3m 采信反馈，防 z=-10 毛刺）；任务取消响应 <2s（轮询等待替代阻塞等待）；
- **正确性**：OFFBOARD 切入确认（wait_mode_engaged）；起飞 yaw 锁存防姿态毛刺；任务文件解析防崩溃（safe_stod 全串消费校验）；
- **架构**：移除 PID 死代码（明确定位为 setpoint 生成器 + PX4 内环）；uav_ 跨线程加锁；状态订阅独立回调组（修复回调组饿死）；
- **实机级 Bug**：PX4 的 RTL 模式名是 `AUTO.RTL` 而非 `RTL`（bridge 已修）。

实测全绿：起飞/航点/航点取消(停于取消点)/降落取消(恢复悬停)/正常降落/坏任务文件(不崩)/低电量注入 RTL 触发，详见 question.md"修复记录"。

### P1 控制质量修复 ✅（2026-09-13，P0 之后实施）

依据 question.md P1 批次（Q11/Q12/Q14-Q18/Q26，Q13 缓做至阶段四）：

- **launch 化 + use_sim_time**（Q11+Q26）：flight_control / mission_fsm 各自 launch（use_sim_time 参数）；perception_sitl 一键集成控制节点，启动即可飞；
- **encoder 修复**（Q14/Q15）：ANGULAR_RATE 的 type_mask 0b10000111→0b10000000（原值静默丢弃角速率指令，E2 规划层接入前置扫雷）；ATTITUDE_THRUST 明确为 ATTITUDE 历史别名；
- **完成判定去抖**（Q16）：ramp 走完 + 连续 5 帧双条件，防反馈毛刺误判；
- **rc_connected 掉线检测**（Q17）：1s 超时；**实测 dt**（Q12）：限幅实测周期；**模式映射文档化**（Q18）。

回归全绿（新 launch 入口）：起飞/远近航点/降落/use_sim_time/rc 仿真语义/一键节点表，详见 question.md"八、P1 修复记录"。

### 感知类修复 ✅（2026-09-13，P0/P1 之后实施）

依据 question.md 感知批次（Q19/Q20/Q23/Q25；Q21/Q22/Q24 维持文档记录）：

- **跟踪 ID 稳定性**（Q19）：SORT 双门限关联（IoU 或中心距离）+ KF 速度噪声 0.01→1.0 + 参数调优（iou 0.3→0.15、max_lost 30→45）——**飞行 unique ID 168→26（↓84%）**；
- **深度-跟踪时间同步**（Q20）：pixel_to_3d 深度环形缓冲（10 帧）+ 按 tracks 时间戳最近帧匹配（|Δt|>200ms 跳帧）；
- **深度范围**（Q23）：相机 far 10→20m（SDF+插件+pixel_to_3d 同步），实测 19.45m 目标 3D 恢复；
- **类别过滤**（Q25）：tracking.yaml target_classes 配置为关注类别（person/car/truck/bus 等）。

未做（理由记录于 question.md）：Q21 机身遮挡（仿真保真度，实机无此问题）、Q22 MID-360 盲区（实机倒装解决）、Q24 livox 噪声（简单噪声无意义，实机验收）。

### 全项目复查（第二轮）✅（2026-09-13）

对 P0/P1/感知修复后的全部代码做逻辑闭环复查，修复 4 个缺陷（详见 question.md"十"）：

- **A 外部接管检测盲区**：检测从 HOVER 分支提升为 TAKEOFF/WAYPOINT/HOVER 通用——低电量 RTL 发生在航点中时即时中止（原会卡到超时误报）；
- **B 取消窗口子 goal 泄漏**：goal 已接受但 future 未返回的窗口内取消，补发子 goal 取消；
- **C goal 被拒后空指针**：mission_fsm takeoff/land 步骤补判空（原抛晦涩异常）；
- **D 降落后无法再次起飞**：起飞流程重构为"先建流后解锁"（发 setpoint→切 OFFBOARD→等注册→arm 重试 10s）——修复 PX4 降落后停留 OFFBOARD 模式导致 arm 永拒的问题；实测连续起降循环 ×2 通过（修复前第 2 循环必失败）。

新记录的环境怪癖：SITL 连续 3+ 轮起降后磁力计退化（重启仿真）；RTL 虚拟 home 519m（SITL GPS 偏差，RTL 仍正常执行）。test-guide.md 已全面更新（含 RTL/接管验证流程、连续起降回归项、常见问题表扩充至 15 条）。

### 阶段三 M6：全链路集成验收 ✅（2026-09）

| 项 | 状态 | 说明 |
|----|------|------|
| 演示任务 | ✅ | perception_demo_mission.yaml：起飞2.5m→前飞15m途经目标区→悬停→折返→降落（低空2.5m：平放 MID-360 的 -7° 下视角在此高度可视约16m内地面，5m 以上高度看不到地面——见踩坑5） |
| waypoint 控制重构 | ✅ | **全轴目标渐近式 setpoint**（替代增量跟随式），修复飞行失控 |
| 全链路验收 | ✅ | **任务 "mission complete"**：起飞→前飞15.5m→折返→降落归位(x=0.1)；SLAM 全程稳定（最远15.59m、返航末态归零、693帧/630点地图）；3D 定位全程693帧有效（person定位误差<0.3m） |
| 低优先包处理 | ✳ | pointcloud_filter / time_sync **推迟到阶段四**（规划层开工时按需实现；仿真全同源无 time_sync 实际需求），schedule 原计划"按需裁剪"的落实 |

**M6 排障中修复的三个重大问题（阶段二遗留 Bug 一次性暴露）**：
1. **EKF 坐标旋转（磁偏角）**：launch 里设了 PX4_HOME_LAT/LON=武汉，与 PX4 SITL 默认 home（苏黎世）的磁偏角差使 EKF local frame 相对 Gazebo 世界旋转约90°——航点(10,0)被飞成(0,10)，且 mavros 系与 SLAM/Gazebo 系不一致。**修复：删除自定义 HOME**；
2. **waypoint 增量跟随式控制发散**：mavros local_position 偶发大幅毛刺（实测 z 尖峰 -10m），`cmd=feedback+Δ` 把毛刺写进 setpoint 形成正反馈螺旋（z 缓降趴地 / xy 反向漂移）。悬停/起飞用绝对目标所以正常，仅 waypoint 中招——阶段二未飞过航点故潜伏。**修复：waypoint 改全轴目标渐近式**（setpoint 从起点直线渐近目标，零反馈依赖）；
3. **桨叶 collision 遮挡 LiDAR**：iris 旋翼的 cylinder collision（r=0.128）在电机高速旋转时挡住 MID-360 射线（静态时射线恰从桨叶间隙穿过故此前未现）。**修复：rotor collision 半径置 0.001**（visual 保留）。

**踩坑记录（M6 补充）**：
4. **MID-360 平放的高度盲区**：垂直 FOV -7°~+52°（中心朝上），平放在 5m 高度实测 z<-1 点数为 0——完全看不到地面，SLAM 因无特征发散。倒装尝试因插件坐标系不确定性放弃（外参枚举均漂移）。**采用低空飞行（2.5m）方案**：-7° 下视角可视 ~16m 内地面。实机部署时应倒装/斜装雷达并重标外参；
5. **git checkout 误伤**：对未提交的工作区文件执行 `git checkout -- file` 会静默回退全部未提交修改（M0-M6 的 SDF 传感器配置曾因此丢失，靠对话记录重建）。**教训：重要修改及时 commit；回退单个文件改动应用手动编辑而非 git checkout**；
6. PX4 残留进程（`PX4 server already running`）会让新实例静默退出（exit 255）→ mavros 电池为 0 → 起飞失败。反复测试间必须彻底清理（pkill 精确路径）；
7. 飞行中跟踪 ID 偏多（168 个/次飞行）：画面抖动+目标进出视野下 min_hits/lost 参数的平衡问题，属参数优化项（非功能故障），阶段四接 TrackTarget 时按需调优。

### 阶段四 M4.0：规划基础设施 ✅（2026-09-14）

| 项 | 状态 | 说明 |
|----|------|------|
| easyfly_pointcloud_filter | ✅ | `/livox/lidar`(CustomMsg) → 距离滤波(0.3~25m)+体素(0.1m) → `/pointcloud_filtered`(PointCloud2, base_link 系)；滤波核心 header-only 无 ROS 依赖，单测 5/5；为 M4.3 EGO grid_map 备好输入 |
| easyfly_semantic_map | ✅ | 滤波点云 → 逐帧 RANSAC 地面剔除 → 5 帧滑动累积 → 欧式聚类 → `/obstacles`(ObstacleInfoArray) + `/get_obstacles`(srv, 按距机体水平距离过滤) + `/occupancy_grid`(2D 栅格+膨胀 0.3m) + `/obstacle_markers`；TF 跳变守卫 |
| 集成 | ✅ | perception_sitl.launch.py t=20s 启动两节点；rviz 增 FilteredPointCloud/OccupancyGrid/ObstacleMarkers 三显示项 |
| 验收数据 | ✅ | perception_demo 场景 10 目标检出 8-9 个；近场(≤12m)精度 **0.01~0.15m**（person1 0.08、box1 0.01、person_w 0.03）；远场(20-25m) 0.7~1.9m（大物体部分可见包围盒中心）；truck1 大车辆聚类分段属已知特性；GetObstacles 服务正常 |

**M4.0 踩坑记录（重要）**：
1. **EKF 原点每次启动都不同**：地面在 odom 系的高度不固定（-0.98 ~ -0.06 都出现过），机体静止时 base_link 离地仅 ~0.06m（spawn 0.83 是投放高度）。**任何写死的"离地高度/地面高度"都会失效**——地面必须从数据估计（RANSAC 平面）；
2. **地面剔除必须逐帧做**：mavros EKF 姿态噪声（~0.5°）经 25m 杠杆把地面涂抹成 ±0.3m 厚带，累积后整体 RANSAC 拟不干净（残留点把聚类链成 12m 巨簇）；单帧内姿态一致，倾斜地面仍是完美平面，每帧独立拟合即可干净移除；
3. **mavros 启动位置毛刺**（详见 question.md Q34）：首帧 local_position 可达 (1.08,-2.57)，会把整个场景平移复制进累积窗口 → 幻影簇。semantic_map 加了 TF 跳变守卫（>1m 丢帧 + 持续漂移 10 帧重置基线——注意 EKF 启动是"持续错误后收敛"而非孤立尖峰，固定基线会永久卡死）；
4. **px4_sitl.launch.py 的 world 参数用 str+LaunchConfiguration 相加**会在 launch 生成期抛错（阶段一起潜伏，方式 B 从未真正可用，回归测试首跑即暴露）——已改 PathJoinSubstitution；
5. onnxruntime GPU SDK 单文件 352MB 超 GitHub 100MB 限制，third_party/onnxruntime 不入库（获取方式见其 EASYFLY_SETUP.md）；fast_lio 上游 doc/（128MB 演示 gif）同样排除；
6. 大物体（fire_truck 5m）会被 0.4~0.6m 容差的欧式聚类分段成多簇——对规划无害（每段都是障碍），跨帧稳定 ID 待消费方需求出现再做（M4.0 边界，obstacle_id 为帧内索引）。

---

## 五、待完成工作

### 阶段三：感知流水线 ✅（已完成 M0-M6，2026-09）

**目标**：仿真中无人机检测目标、跟踪目标、完成 SLAM 定位，RViz2 可视化验证。

| 步骤 | 任务 | 依赖 | 优先级 |
|------|------|------|--------|
| 3.0 | 给 easyfly_iris.sdf 加仿真相机 + LiDAR 插件 | - | ✅ 已完成（M0） |
| 3.1 | easyfly_camera_calib + coord_transform | 仿真传感器 | ✅ 已完成（M1） |
| 3.2 | easyfly_object_detection（YOLO11n ONNX，GPU 推理） | 3.1 | ✅ 已完成（M2） |
| 3.3 | easyfly_fast_lio（FAST-LIO2） | 仿真 LiDAR | ✅ 已完成（M3，集成 hku-mars 官方 ROS2 分支） |
| 3.4 | easyfly_multi_object_tracking（SORT） | 3.2 | ✅ 已完成（M4） |
| 3.5 | easyfly_pixel_to_3d | 3.2 + 仿真深度 | ✅ 已完成（M5，输入升级为 /tracks） |
| 3.6 | easyfly_pointcloud_filter / time_sync | LiDAR | ⏸ 推迟到阶段四（规划层开工时按需实现；仿真全同源无 time_sync 实际需求，M6 决策） |
| 3.7 | landing_detection / apriltag 等 | 3.1 | ⏸ 阶段四再做（schedule 原计划） |

### 阶段四：规划 + 避障

| 包 | 说明 |
|----|------|
| ~~easyfly_pointcloud_filter~~ | ✅ M4.0 已完成（CustomMsg→滤波→PointCloud2） |
| easyfly_global_planner | A*/RRT*，输入 /occupancy_grid（M4.0 已产出） |
| easyfly_local_planner | EGO-Planner（ROS1→ROS2 迁移，风险最高） |
| easyfly_trajectory_optimizer | Minimum Snap |
| easyfly_obstacle_avoidance | 避障机动 |
| easyfly_gimbal_control | 云台控制（工厂模式） |
| easyfly_precision_landing | 精确降落闭环 |

### 阶段五：应用层

| 包 | 说明 |
|----|------|
| easyfly_core | C++ SDK 聚合头文件 |
| easyfly_params | 统一参数管理 |
| easyfly_mission_srvs / perception_srvs | 标准化 A2 服务 |
| easyfly_mission_scripts | 任务脚本引擎 |
| easyfly_demos | 5 个 Demo |
| easyfly_pybind | Python 绑定 |

### 阶段六：UI + 媒体 + 打磨

| 包 | 说明 |
|----|------|
| easyfly_video_streamer / recorder | 视频推流 + 录制 |
| easyfly_ui_bridge | UI ↔ ROS2 桥接 |
| easyfly_desktop | Qt6 桌面地面站 |
| easyfly_web | Web 地面站 |

---

## 六、关键依赖链

```
最长阻塞路径（阶段三→四的必经之路）：
C1(LiDAR驱动) ✅ → P1(预处理) 🔜 → P3(FAST-LIO) 🔜 → P4(语义地图) → E2(规划层)
```

**注意**：EGO-Planner 从 ROS1 迁移到 ROS2 是全程工作量最大的单项，阶段四需留足 buffer。

---

## 七、技术风险清单

| 风险 | 缓解 |
|------|------|
| FAST-LIO2 的 ROS2 Humble 兼容性 | 阶段三第一批验证，必要时换 LIO-SAM |
| TensorRT 在 x86 仿真环境不可用 | 先用 OpenCV DNN 跑通链路，再切后端 |
| Gazebo 传感器仿真效果不足 | 先跑通数据流，必要时录 rosbag 回灌 |
| P4 融合外参标定精度 | 仿真用理想外参验证算法，再考虑标定 |
| EGO-Planner ROS1→ROS2 迁移 | 阶段四预留充足时间 |

---

## 八、开发节奏参考

```
阶段〇 基础设施      ✅ 已完成
阶段一 通信+仿真     ✅ 已完成
阶段二 控制闭环      ✅ 已完成
阶段三 感知流水线    ✅ 已完成（M0-M6，2026-09；3.6/3.7 推迟至阶段四）
阶段四 规划+避障     🔜 下一阶段（约 3-4 周）
阶段五 应用层        ⏳（约 2-3 周）
阶段六 UI+媒体+打磨  ⏳（约 2-3 周）
```

---

*最后更新：跟随 git 提交持续维护。*
