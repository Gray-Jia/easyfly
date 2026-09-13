# EasyFly 测试与使用指南（test-guide.md）

> 更新时间：2026-09-13（阶段三完成 + P0/P1/感知修复 + 两轮全项目复查后）
> 环境：Ubuntu 22.04 + ROS2 Humble + PX4 1.16.1 + Gazebo Classic 11 + RTX GPU（OnnxRuntime CUDA）
> 已知问题见 `question.md`，本指南只覆盖当前可用功能。

---

## 〇、环境准备

```bash
cd ~/easyfly_ws
source easyfly_env.bash        # 内含 /opt/ros/humble + install/setup.bash
```

前置检查：

```bash
ros2 pkg list | grep -E "mavros|easyfly" | head    # ROS 包就绪
ls ~/PX4-Autopilot-1.16.1/build/px4_sitl_default/bin/px4   # PX4 SITL 已编译
nvidia-smi                                        # GPU（检测节点用）
```

全量编译 / 分层编译：

```bash
colcon build                # 全量
bash build_layer.bash       # 分层构建脚本
```

**仿真时钟约定**：全链路节点（含 mavlink_bridge）均已配置 `use_sim_time=true`。手动单独启动任何节点时务必带上该参数，否则其发布的 TF/消息时间戳为墙钟，会导致下游 TF 查询 extrapolation 失败。

**启动前清理（重要）**：

```bash
bash easyfly_clean.sh    # 一键清除残留仿真进程
```

**必读**：`fastlio_mapping` 进程路径不含 "easyfly"，异常退出时极易残留成僵尸。多个僵尸实例会导致 RViz 中 **path 乱画、点云/飞机消失**（多个 SLAM 实例同时发布矛盾的 `/Odometry`/`/path`，`map→odom` TF 被乱数据驱动跳变）。出现这些症状先跑清理脚本再重启仿真。

---

## 一、两种启动方式

### 方式 A：感知全链路仿真（推荐，日常用这个）

```bash
ros2 launch easyfly_px4_sitl perception_sitl.launch.py
```

一键拉起（按时间先后）：

| t | 组件 | 说明 |
|---|------|------|
| 0s | gzserver | perception_demo.world（4 行人 + 2 消防车 + 4 纸箱沿 +X 排开） |
| 3s | spawn easyfly_iris | 带 D435i 前视深度相机 + 平放 MID-360 |
| 6s | gzclient + PX4 SITL + RViz2 + robot_state_publisher | GUI / 飞控 / 可视化 / 机体 URDF 模型 |
| 8s | mavros + mavlink_bridge | `/uav_state` 开始发布 |
| 10s | **flight_control + mission_fsm** | 控制节点（P1 修复后自动拉起，直接可飞） |
| 12s | P1：calib_tf + coord_tf | 静态外参 TF + odom TF |
| 14s | P2 检测 + P3 SLAM | YOLO11n 推理 + FAST-LIO 建图（含 map→camera_init 恒等桥接 TF） |
| 16s | P4 跟踪 | SORT |
| 18s | P5 像素转3D | 目标世界系定位 |

**注意**：
- 此 launch **已包含**控制节点（flight_control + mission_fsm，use_sim_time=true），启动完成后即可直接发送起飞/航点指令，无需另开终端；
- **首次起飞前等待 PX4 EKF/GPS 收敛**：看 PX4 终端出现绿色 `Ready for takeoff!`（约启动后 30-60s，重场景较慢）。未收敛时发起飞会被 arm 重试兜住（自动重试 10s），但等待更稳。

### 方式 B：纯控制仿真（不带感知）

```bash
ros2 launch easyfly_sim_launcher easyfly_sim.launch.py   # px4_sitl(empty.world) + mavlink_bridge
```

或单独起仿真骨架：

```bash
ros2 launch easyfly_px4_sitl px4_sitl.launch.py          # 默认 empty.world
ros2 launch easyfly_px4_sitl px4_sitl.launch.py world:=perception_demo.world
```

---

## 二、模块功能与接口速查

### 仿真层（S）

| 包 | 功能 | 关键输出 |
|----|------|---------|
| `easyfly_px4_sitl` | iris 模型 + launch + RViz 配置 | — |
| `easyfly_gazebo_worlds` | empty.world / perception_demo.world | — |
| `easyfly_gazebo_models` | mid360 / person / fire_truck 等模型库 | — |
| `easyfly_gazebo_plugins` | **livox_laser_plugin**：MID-360 仿真插件（ROS2 移植），CSV 非重复扫描 | `/livox/lidar`（CustomMsg，20000 点/帧，~10Hz）、`/livox/imu`（200Hz） |
| iris 模型内相机 | D435i 风格深度相机（系统 gazebo_ros_camera） | `/camera/color/image_raw`(rgb8 30Hz)、`/camera/color/camera_info`、`/camera/aligned_depth_to_color/depth/image_raw`(32FC1)、`/camera/aligned_depth_to_color/points` |

### 通信层（C）

| 包 | 功能 | 关键输入 → 输出 |
|----|------|----------------|
| `easyfly_mavlink_bridge` | 解码：聚合 8 路 mavros 话题；编码：UAVCommand → mavros setpoint；服务：/arm_motors、/set_flight_mode | mavros 话题 → `/uav_state`(20Hz)、`/mission_status`；`/uav_command` → `/mavros/setpoint_position/local` 等 |
| `easyfly_rc_receiver` / `easyfly_serial` | 遥控器接收 / POSIX 串口（实机用，仿真空载） | — |
| `livox_ros_driver2` | 实机 MID-360 驱动 + CustomMsg 消息定义（仿真也用其消息类型） | — |

### 执行层（E）

| 包 | 功能 | 接口 |
|----|------|------|
| `easyfly_flight_control` | 3 个 Action Server：起飞 / 降落 / 航点。**实际控制策略**：目标渐近式 setpoint（抗反馈毛刺）+ PX4 OFFBOARD 内环 | `/takeoff`、`/land`、`/goto_waypoint`（action）；订阅 `/uav_state`，发布 `/uav_command` |
| `easyfly_mission_fsm` | 任务状态机：解析 YAML 任务 → 逐步调用上述 action；1Hz 电池检查（仅报警，见 question.md Q2） | `/execute_mission`（action，goal 为 mission_file 路径）；发布 `/mission_status` |

### 感知层（P）

| 包 | 功能 | 输入 → 输出 |
|----|------|------------|
| `easyfly_camera_calib` | 内外参管理（config/sensors.yaml）+ 静态 TF（base→camera/livox 各光学系）+ 内参校验节点 | yaml → `/tf` 静态变换 |
| `easyfly_coord_transform` | `/uav_state` → odom→base_link 动态 TF + `/odom`（twist 已转 body 系） | `/uav_state` → `/tf`、`/odom` |
| `easyfly_object_detection` | YOLO11n OnnxRuntime GPU 推理（CUDA EP，~3.5ms/帧），letterbox + NMS 自实现 | `/camera/color/image_raw` → `/detections`（归一化 bbox）、`/detections_debug_image` |
| `easyfly_multi_object_tracking` | SORT（像素空间卡尔曼 + 匈牙利关联） | `/detections` → `/tracks`（稳定 ID）、`/tracks_debug_image` |
| `easyfly_pixel_to_3d` | bbox + 深度图中位采样 → 针孔反投影 → TF 到 map 系 | `/tracks` + 深度 + TF → `/target_positions`、`/target_markers`（RViz 球+标签） |
| `fast_lio` + `easyfly_fast_lio_integration` | FAST-LIO2（hku-mars 官方 ROS2 分支）：Livox CustomMsg + IMU → 里程计 + 建图，发布 map→odom TF | `/livox/lidar` + `/livox/imu` → `/odometry`(FAST-LIO)、`/cloud_registered`、`/path`、`/tf`(map→odom) |

**TF 树全貌**（感知仿真启动后）：

```
map ──(fast_lio 动态)── odom ──(coord_transform 动态, 来自 mavros EKF)── base_link
  ├─(静态恒等, map_odom_tf)── camera_init          ← FAST-LIO 点云 frame 的桥接
  ├─(静态, calib_tf)─ camera_link ─ camera_color_optical_frame / camera_depth_optical_frame
  └─(静态, calib_tf)─ livox_frame
```

注意：
- `map→odom` 与 `odom→base_link` 是**两条独立链**（SLAM 与 EKF 各自维护），同时启动时 map frame 的位姿以 FAST-LIO 为准；
- `map→camera_init` 恒等桥接由 `map_odom_tf` 自动发布——没有它 FAST-LIO 的点云（frame=camera_init）在 RViz 中无法显示（TF 树断裂）；
- `base_link→camera_link/livox_frame` 的静态 TF 有两个发布源（calib_tf_publisher 与 robot_state_publisher 的 URDF），数值严格一致、重复无害；修改传感器安装位姿时须**三处同步**：`sensors.yaml` + `easyfly_iris.sdf` + `easyfly_iris.urdf`。

---

## 三、飞行控制使用

### 启动控制节点

**方式 A（推荐）**：`perception_sitl.launch.py` 已自动拉起（见第一节），无需手动启动。

**方式 B（单独启动，如纯控制仿真）**：

```bash
ros2 launch easyfly_flight_control flight_control.launch.py                      # 仿真
ros2 launch easyfly_mission_fsm mission_fsm.launch.py
# 实机: use_sim_time:=false
```

### 单个 Action 调用（注意：字段名以此为准）

```bash
# 起飞到 2.5m（climb_speed 可选，默认 1.0 m/s）
ros2 action send_goal /takeoff easyfly_msgs/action/Takeoff \
  "{target_altitude: 2.5, climb_speed: 1.0}" --feedback

# 航点飞行（注意字段是 target_x/y/z，不是 target_position）
ros2 action send_goal /goto_waypoint easyfly_msgs/action/GoToWaypoint \
  "{target_x: 10.0, target_y: 0.0, target_z: 2.5, max_speed: 2.0}" --feedback

# 降落（切 PX4 AUTO.LAND）
ros2 action send_goal /land easyfly_msgs/action/Land "{}" --feedback
```

**起飞内部流程**（自动执行，无需手动干预）：发初始 setpoint 建流 → 切 OFFBOARD → 等流注册 → arm（重试 10s 兜底 EKF 收敛边缘）→ 校验模式切入。**降落后可直接再次起飞**（自动处理 PX4 残留模式），支持连续多轮起降。

约束（当前实现的既定行为）：
- 航点高度建议 **≤2.5m**（MID-360 平放 5m 以上看不到地面，SLAM 漂移风险，见 question.md Q22）；
- Takeoff/Land 只能在 `active_==NONE/HOVER` 状态发起，连续发会被 REJECT；
- 航点完成半径默认 0.5m；
- **取消行为**（P0 修复后）：航点/起飞取消 → 无人机减速并悬停在取消点附近（带惯性会过冲 ~1m）；降落取消 → 切回 OFFBOARD 爬回降落前悬停高度；
- **超时保护**：起飞/航点超时（3×名义时间+余量）自动 abort 并就地悬停；
- **低电量保护**：电量 <15% 时任务自动中止并触发 PX4 RTL 返航（`/mission_status` 报 EMERGENCY）；
- **外部接管**：HOVER 状态下若检测到 PX4 被切到 RTL/AUTO.LAND（低电量保护或地面站手动），控制节点自动停止 setpoint 并复位，可重新接受新任务。

### 任务文件方式（YAML 状态机）

示例文件：`src/execution/e1_state_machine/easyfly_mission_fsm/missions/`（含 `perception_demo_mission.yaml`）

```bash
ros2 action send_goal /execute_mission easyfly_msgs/action/ExecuteMission \
  "{mission_file: '/home/jia/easyfly_ws/src/execution/e1_state_machine/easyfly_mission_fsm/missions/perception_demo_mission.yaml'}" --feedback
```

任务 YAML 格式（`---` 分隔步骤，支持 takeoff / waypoint / hover / land）：

```yaml
type: takeoff
altitude: 2.5
climb_speed: 1.0
---
type: waypoint
x: 10.0
y: 0.0
z: 2.5
yaw: 0.0
max_speed: 2.0
---
type: hover
wait: 5.0
---
type: land
```

运行中监控：`ros2 topic echo /mission_status`（phase / 当前进度）。

---

## 四、分模块验证方法

### V1. 仿真传感器（M0）

启动方式 A 后：

```bash
ros2 topic hz /camera/color/image_raw          # ~30Hz
ros2 topic hz /livox/lidar                     # ~10Hz, CustomMsg
ros2 topic echo /livox/lidar --once --field point_num   # 20000
ros2 topic hz /livox/imu                       # ~200Hz
ros2 topic echo /camera/aligned_depth_to_color/depth/image_raw --once --field encoding  # 32FC1
ros2 topic hz /clock                           # 仿真时钟存在（若 0 说明 -s 插件没加载）
```

RViz2 中：检测画面面板有图像；Gazebo 窗口能看到场景。

### V2. TF 与坐标（M1）

```bash
ros2 run tf2_tools view_frames                 # 生成 frames.pdf，核对第一节 TF 树
ros2 run tf2_ros tf2_echo map base_link        # 起飞后持续变化
ros2 run tf2_ros tf2_echo base_link camera_color_optical_frame   # 静态 (0.25,0,0.22)+(-π/2,0,-π/2)
ros2 topic echo /odom --once
```

内参校验节点在启动时自动比对 YAML 与 `/camera/color/camera_info`，日志出现 `一致` 即通过。

### V3. 目标检测（M2）

```bash
ros2 topic hz /detections                     # ~相机帧率
ros2 topic echo /detections --once            # 归一化 bbox + class_name + confidence
```

可视化：RViz2 检测画面（`/detections_debug_image`，绿框+类别+置信度）。场景中的 person / fire_truck（truck 类）应稳定出框。注意视野下半幅有机身遮挡（question.md Q21）。

换模型：编辑 `easyfly_object_detection/config/detection.yaml`（model_path / class_names / conf_threshold / imgsz），支持任意 YOLO 导出的 ONNX。

### V4. 多目标跟踪（M4）

```bash
ros2 topic echo /tracks --once                # track_id 稳定复现
```

可视化：`/tracks_debug_image`（黄框 + #ID）。验收标准：静态场景同目标 ID 稳定；短暂遮挡（目标互相走过）后 ID 保持。飞行中 ID 更替已优化至 ~26 个/次飞行（2026-09-13 调参后，原 168；剩余为视野边缘进出/机身遮挡闪断的自然更替）。类别过滤已启用（tracking.yaml `target_classes`，只跟踪 person/car/truck 等关注类别）。

### V5. 像素转 3D（M5）

```bash
ros2 topic echo /target_positions --once      # position_valid / x,y,z / distance
```

RViz2：`/target_markers` 球体 + 标签（#ID 类别 距离）。验收：marker 落在 Gazebo 中目标实际位置附近（静态测试误差 <0.3m）。

### V6. SLAM（M3）

```bash
ros2 topic hz /cloud_registered               # ~雷达帧率
ros2 run tf2_ros tf2_echo map odom            # 飞行中缓慢变化（SLAM 修正量）
```

RViz2：点云地图（`/cloud_registered`）随飞行累积成形、绿色轨迹（`/path`）平滑。验收：飞到 x=15 折返后，降落时 map �系位置回零（M6 实测 x=0.1m）。

### V7. 控制链路（阶段二）

```bash
ros2 topic echo /uav_state --once             # armed / position / battery 齐全
ros2 topic echo /uav_command --once           # 飞行中 20Hz
```

依次执行第三节命令，观察 Gazebo 中飞机轨迹。**已验证场景**（M6）：起飞 2.5m → 前飞 15.5m → 折返 → 降落回原点（误差 0.1m）。

---

## 五、全链路验收流程（M6 标准场景复现）

完整跑一遍 ≈ 3 分钟：

```bash
# 终端1: 感知仿真 + 控制节点 (一键, P1 修复后无需另起控制终端)
ros2 launch easyfly_px4_sitl perception_sitl.launch.py

# 终端2: 等一切就绪(~30s)后起飞 → 前飞 → 折返 → 降落
ros2 action send_goal /takeoff easyfly_msgs/action/Takeoff "{target_altitude: 2.5}"
ros2 action send_goal /goto_waypoint easyfly_msgs/action/GoToWaypoint "{target_x: 10.0, target_y: 0.0, target_z: 2.5}"
ros2 action send_goal /goto_waypoint easyfly_msgs/action/GoToWaypoint "{target_x: 0.0, target_y: 0.0, target_z: 2.5}"
ros2 action send_goal /land easyfly_msgs/action/Land "{}"
```

通过标准（同屏观察）：
1. RViz2：SLAM 点云地图随航线累积、绿色轨迹连续、目标 Marker 出现在行人/车辆位置、灰色机体模型随飞行移动；
2. 检测画面：飞行经过目标区时 person/truck 框稳定出现；
3. Gazebo：飞机轨迹为直线往返、降落回起点附近（<1m）；
4. 全程无节点崩溃（`ros2 node list` 前后一致）。

### 附加验证：低电量 RTL 与接管（安全链路）

```bash
# 1. 起飞 + 远航点任务（文件见 missions/，或自写 20m 航点任务）
ros2 action send_goal /execute_mission easyfly_msgs/action/ExecuteMission \
  "{mission_file: '.../perception_demo_mission.yaml'}" --feedback

# 2. 航点飞行中模拟低电量（另一终端）
ros2 topic pub -r 10 /mavros/battery sensor_msgs/msg/BatteryState \
  "{voltage: 13.0, percentage: 0.10}" &
```

期望行为链（全部自动）：
- mission_fsm：`Battery low (10%) → 中止任务 + 触发 PX4 RTL`，mission 状态 ABORTED；
- flight_control：`检测到外部模式接管 (mode=6)`，立即停 setpoint 并释放状态（**不是**等超时）；
- PX4：切 AUTO.RTL → 自动返航降落（仿真中约 2 分钟，含虚拟 home 距离）；
- 降落后可直接发新 takeoff（验证"降落后可再次起飞"）。

### 附加验证：连续起降循环（回归项）

```bash
for i in 1 2; do
  ros2 action send_goal /takeoff easyfly_msgs/action/Takeoff "{target_altitude: 2.0}" 
  ros2 action send_goal /land easyfly_msgs/action/Land "{}"
  sleep 3
done
```

两轮均应 SUCCEEDED（第 3 轮起 SITL 磁力计可能退化报 failsafe，属仿真怪癖——见第六节）。

---

## 六、常见问题排查

| 现象 | 原因 | 处理 |
|------|------|------|
| `/clock` 无输出、所有传感器时间戳为 0 | `libgazebo_ros_init.so` 未加载 | 确认 gzserver 命令带 `-s libgazebo_ros_init.so`（launch 已内置；手跑 gzserver 别忘了） |
| 传感器话题全无 | GAZEBO_PLUGIN_PATH 缺失 | 需含 easyfly 插件 + /opt/ros/humble/lib + PX4 build_gazebo-classic 三个路径 |
| 起飞 action 一直 pending | OFFBOARD 未真正切入 / EKF 未收敛 | 看 PX4 终端 `Preflight Fail` 消息；等 `Ready for takeoff!`（30-60s）后重试；确认 flight_control 与 mavlink_bridge 都在运行 |
| RViz 全空 + 无侧边栏 | rviz 配置损坏 | 重新 `colcon build --packages-select easyfly_px4_sitl` 后重启 launch；手改 .rviz 后先 `python3 -c "import yaml; yaml.safe_load(open('xxx.rviz'))"` 校验 |
| RViz 里点云显示但"没有飞机" | 正常——iris 无 URDF | P2 复查后已有 URDF（RobotModel 显示灰色机体）；若仍无：确认 `/robot_description` 话题存在、RobotModel 显示项 Enabled |
| SLAM 点云不显示（TF 断链） | FAST-LIO 点云 frame 是 `camera_init`，缺 map→camera_init 桥接 | 已修复（map_odom_tf 自动发布恒等 TF）；若复现检查 fastlio_integration 是否在跑 |
| 起飞 arm 被拒（日志 "Arming denied"） | EKF/GPS 未收敛或时序窗口 | 内置 arm 重试（10s）通常自愈；仍失败则等 `Ready for takeoff!` 后重发 |
| 降落后无法再次起飞 | 已修复（"先建流后解锁"流程） | 若复现：查 `/mavros/state` 残留模式，重启 flight_control 节点 |
| 连续 3+ 轮起降后姿态报错/failsafe | SITL 磁力计退化（仿真怪癖，实机无此问题） | 重启仿真环境后继续 |
| RTL 返回点显示 519m | SITL GPS home 与 Gazebo 原点偏差（已知怪癖） | RTL 仍正常执行并降落，需 ~2 分钟；验证链路时耐心等待 |
| 航点 (x,0) 飞成 (0,x) | EKF 磁偏角问题回归 | 确认 launch 未设置 PX4_HOME_LAT/LON（M6 已删） |
| FAST-LIO 崩溃后 RViz 全空 | map frame 单点依赖 | 重启 fast_lio（`ros2 launch easyfly_fast_lio_integration fastlio.launch.py`）；长期方案见 question.md Q28 |
| 检测节点起不来 | onnxruntime/CUDA 问题 | `nvidia-smi` 确认驱动；检查 third_party/onnxruntime 完整性 |
| 残留 gazebo 进程占端口 | 上次未正常退出 | `bash easyfly_clean.sh`（一键清理） |
| **RViz path 乱画 + 点云/飞机消失** | **fastlio_mapping 僵尸多实例**（路径不含 "easyfly"，pkill 常规模式匹配不到；多实例同发 /Odometry 导致 TF 跳变） | `bash easyfly_clean.sh` 后重启仿真；确认：`ros2 node list \| grep -c laser_mapping` = 1 |
| **odom_ned/map_ned/base_link_frd 帧在"漂移"** | 正常现象。这三个是 mavros 发布的 **NED 惯例桥接帧**（纯旋转零平移的静态孪生帧，供 PX4 原生 NED 接口用），EasyFly 全链路不使用。看到的"漂移"= EKF yaw 静止漂移（SITL 磁力计怪癖，实测 ~15°/分钟）+ map→odom 的 SLAM 修正（REP-105 设计行为），非帧本身移动 | 无需处理；嫌乱可在 RViz TF 显示项里取消勾选这三个帧 |
| 编译报 "Failed to find livox_ros_driver / prometheus_msgs" | Platform/ 参考项目被 colcon 误扫描 | 已加 `Platform/COLCON_IGNORE`；若复现确认该文件存在 |

---

## 七、配置文件索引（改参数看这里）

| 用途 | 文件 |
|------|------|
| 传感器内外参（相机/雷达安装位姿、内参） | `src/perception/p1_preprocess/easyfly_camera_calib/config/sensors.yaml` |
| 检测模型/阈值/输入输出话题 | `src/perception/p2_detection/easyfly_object_detection/config/detection.yaml` |
| SORT 跟踪参数（iou/中心距门限/max_lost/类别过滤） | `src/perception/p3_tracking/easyfly_multi_object_tracking/config/tracking.yaml` |
| 3D 定位（深度范围 0.3-19.5m/有效像素比/目标坐标系） | `src/perception/p4_fusion/easyfly_pixel_to_3d/config/pixel_to_3d.yaml` |
| FAST-LIO（外参/滤波/建图） | `src/perception/p3_tracking/fast_lio/config/mid360.yaml` |
| 飞控/mavros 连接 | `easyfly_mavlink_bridge/launch/mavlink_bridge.launch.py` 的 fcu_url |
| 场景内容 | `src/simulation/easyfly_gazebo_worlds/perception_demo.world` |

**重要**：相机/雷达安装位姿改 `easyfly_iris.sdf` 后，必须同步改 `sensors.yaml`（外参 TF 与模型保持一致），并核对 FAST-LIO 的 `extrinsic_T/R`。
