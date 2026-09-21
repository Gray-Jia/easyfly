# EasyFly 测试、验收与依赖版本基线

> 制定日期：2026-09-15
> 整理起点：master / 94c70cd 加 P0 工作树修改；实际验收须记录提交后的新 HEAD
> 目标：用可重复、分层、可追溯的方法重新验收现有工作，而不是继续扩展功能。

## 1. 验收原则

1. 先冻结版本，再测试；测试期间禁止混入新功能。
2. 先静态和组件测试，再启动 PX4；先最小链，再全感知链。
3. 每次只增加一层依赖，失败立即停止，不在未知状态下继续飞行。
4. build、install、log 使用新的 v2 目录，避免旧产物造成假通过。
5. 功能测试、lint、性能和飞行安全分别统计，不能用一个“全绿”混在一起。
6. 所有仿真和飞行结果必须绑定 Git commit、dirty diff、依赖版本和参数文件。
7. 单次通过只说明可运行；安全相关套件至少连续两轮通过。
8. 任何 crash、NaN、frame 错误、时间跳变、Action 无终态或 failsafe 都是阻塞项。

## 2. 当前验收结论

| 范围 | 当前结论 |
|---|---|
| P0 接口/状态机/并发 | 组件级通过；最终 Review 无 P0/P1 |
| P0 mock | 14/14 通过 |
| 关键包构建 | msgs、bridge、flight_control、mission_fsm、pixel_to_3d 通过 |
| EGO traj_server | 单目标构建通过 |
| 完整干净构建 | 未通过/未重新执行 |
| 工作区全部测试 | 不能标记通过；跨多轮积累的旧结果为 131 项、84 项失败，当前可见失败主要来自 lint |
| T1-T8 | 历史上通过，需要在冻结基线上重跑 |
| T9 | 组件路径通过；真实 SITL 到达未通过 |
| G7-F、G7-N | 当前修复基线均已连续两轮全绿；G7-F 含新增 F6 外部接管，G8/E1-E4 仍待 |
| E1-E4 | 未取得完整全绿 |
| PX4/Gazebo | V2-10 姿态问题已关闭，G7-F/G7-N 无 failsafe；完整 EGO/PX4 SITL（G8）仍有待定位的姿态/时钟/failsafe 阻塞 |
| 实机 | 未验收 |

## 3. 验收记录必须包含的元数据

每轮测试建立独立目录，例如 artifacts/acceptance-YYYYMMDD-HHMM，并保存：

- git rev-parse HEAD；
- git status --short；
- git diff --stat 和完整 patch；
- test-v2.md 第 5 节的版本快照；
- 使用的 launch、YAML 和环境变量；
- 测试命令、开始/结束时间和退出码；
- ros2 node/topic/action/service 列表；
- rosbag2、PX4 ulog、Gazebo/PX4/MAVROS/节点日志；
- CPU、内存、GPU、仿真 RTF；
- 每个断言的实际值，不只保存 PASS/FAIL。

建议先手动提交或保存当前 P0 diff，再开始长时间验收。不要在 dirty 工作树上连续修补而不记录每轮差异。

## 4. 当前需要冻结的版本

### 4.1 操作系统与工具链

| 组件 | 当前实际版本 | 证据/备注 |
|---|---|---|
| Ubuntu | 22.04.5 LTS | lsb_release |
| Kernel | 6.8.0-138-generic | uname |
| 架构 | x86_64 | uname |
| GCC/G++ | 11.4.0 | 系统编译器 |
| CMake | 3.22.1 | 系统 CMake |
| Python 系统环境 | 3.10.12 | /usr/bin/python3 |
| colcon-core | 0.20.1 | 当前 Python 环境 |
| 整理前 Git 基线 | 94c70cd / master / dirty | 本文编写时的 EasyFly 起点；正式验收记录新 HEAD |

### 4.2 ROS、MAVROS 与仿真

| 组件 | 当前实际版本 | 是否必须冻结 |
|---|---|---|
| ROS 2 | Humble | 是 |
| ros-base 元包 | 0.10.0 apt 包 | 是 |
| rclcpp | 16.0.19 | 是 |
| rmw_fastrtps_cpp | 6.2.10 | 是；QoS/通信行为相关 |
| MAVROS | 2.14.0 | 是；setpoint 与坐标转换边界 |
| mavros_msgs | 2.14.0 | 是；消息 ABI |
| libmavconn | 2.14.0 | 是 |
| ROS mavlink definitions | 2026.6.6 | 是；消息定义可能变化 |
| Gazebo Classic | 11.10.2 | 是 |
| gazebo_ros_pkgs | 3.9.0 | 是 |
| gazebo_plugins | 3.9.0 | 是 |
| tf2_ros | 0.25.20 | 是 |
| cv_bridge | 3.2.1 | 是 |
| image_transport | 3.1.12 | 是 |
| pcl_ros / pcl_conversions | 2.4.5 | 是 |

### 4.3 PX4

| 项 | 当前实际值 |
|---|---|
| 路径 | /home/jia/PX4-Autopilot-1.16.2 |
| git describe | v1.16.2-dirty |
| commit | 54f0455ffcd755534539a7cf33a09a20bf71d29d |
| 文档/目录名 | 已统一为 1.16.2 |

目录名不作为版本依据，冻结记录仍以 PX4 commit、dirty diff、SITL build target、ROMFS 参数和 ulog 为准；当前目录与 G0 对齐的 v1.16.2 一致。

### 4.4 视觉、点云和数学库

| 组件 | 当前实际版本 |
|---|---|
| OpenCV | 4.5.4 |
| PCL | 1.12.1 |
| Eigen | 3.4.0 |
| yaml-cpp | 0.7.0 |
| GeographicLib headers/library | 1.52 |
| GeographicLib 数据 | egm96 geoid/gravity、emm2015 magnetic 已存在 |
| NLopt | 未安装，third_party/nlopt 为空目录 |
| nlohmann-json | 未安装，third_party/nlohmann_json 为空目录 |

空 third_party 目录不是有效依赖锁定。若后续包实际需要 NLopt 或 nlohmann-json，必须明确选择系统包还是 vendored 版本。

### 4.5 GPU、CUDA 与推理环境

| 组件 | 当前实际版本 | 备注 |
|---|---|---|
| GPU | NVIDIA GeForce RTX 5060 Ti 16GB | 当前测试机 |
| NVIDIA Driver | 595.91.07 | nvidia-smi |
| Driver 报告 CUDA capability | CUDA 13.2 | 代表驱动可支持的最高运行时，不是编译工具链 |
| CUDA Toolkit | 12.8 | nvcc 与 cuda-toolkit-12-8 |
| cuBLAS | 12.8.3.14 | CUDA 12.8 |
| cuDNN | 9.8.0.87 | CUDA 12 |
| TensorRT runtime | 未发现 libnvinfer 包 | ORT 目录虽含 TensorRT provider，当前不能据此认定可用 |
| ONNX Runtime C++ | 1.23.2，commit a83fc4d5 | vendored GPU SDK |
| ORT CUDA ABI | CUDA 12 / cuDNN 9 | ldd 已解析，无 not found |

ONNX Runtime 是否使用 GPU 必须从运行日志或 provider 查询确认；创建 CUDA EP 失败后回退 CPU 不能算 GPU 验收通过。

### 4.6 模型与 Python 训练/导出环境

| 组件 | 当前实际版本 |
|---|---|
| conda 环境 | cv_easyfly |
| Python | 3.10.20 |
| PyTorch | 2.8.0+cu128 |
| Ultralytics | 8.3.9 |
| onnx | 1.22.0 |
| onnxruntime Python | 1.23.2 |
| 模型 | models/yolo11n.onnx |
| ONNX SHA-256 | fb11c28ed4f579f0503cc9516fce5ee876498f303fa8a01b409d665eafcfe908 |
| PyTorch 权重 SHA-256 | 0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1 |
| ONNX IR | 10 |
| ONNX opset | 12 |
| producer | PyTorch 2.8.0 |
| 输入尺寸 | 历史配置为 640，验收时从模型和 YAML 再核对 |

模型验收还应保存 SHA-256；文件名 yolo11n.onnx 不足以唯一标识模型。

### 4.7 RealSense

| 组件 | 当前实际版本 | 状态 |
|---|---|---|
| realsense-ros | 4.56.4-1-gd69f05c1 | detached HEAD，本地新增构建适配提交 |
| realsense-ros commit | d69f05c1 | 删除 librealsense2 manifest 依赖并忽略 3 个非目标包 |
| realsense2_camera package | 4.56.4 | package.xml |
| realsense2_camera_msgs | 4.56.4 | package.xml |
| vendored librealsense API | 2.56.5 | rs.h |
| librealsense2 工作区安装 | 当前不存在 | 全量构建阻塞项 |

realsense_ros 在主仓库中表现为 gitlink，但根 .gitmodules 没有对应映射。d69f05c1 是基于 IntelRealSense/realsense-ros 4.56.4 的本地提交，并不在 Intel 上游远程；主仓库记录该 gitlink 后，其他机器仍无法自动取回。正式共享基线前必须把该提交推送到可访问的 fork，或把补丁和初始化方式纳入仓库。

### 4.8 Livox

| 组件 | 当前可确认版本 | 可信度 |
|---|---|---|
| livox_ros_driver2 package | 1.0.0 | 仅 package.xml |
| Livox SDK2 | changelog 最新条目 1.2.5 | 无独立 git tag/commit，不能完全确认来源 |

验收时必须记录 MID-360 固件版本、设备配置 JSON、广播码、IP、点云格式和 IMU 频率；这些不能从当前源码自动得出。

### 4.9 FAST-LIO 与 EGO-Planner

| 组件 | 当前版本结论 |
|---|---|
| FAST-LIO | package.xml 为 0.0.0；历史说明来自 hku-mars ROS2 分支，但无上游 commit |
| ikd-Tree | 历史说明从 AstraDroneOpen 同源补齐，无独立 commit |
| EGO-Planner ROS2 | 多数 package.xml 为 0.0.0，无上游 tag/commit |
| ego_to_mavros | package.xml 为 0.1.0，但不能代表整个 EGO 源码版本 |

这些版本目前只能绑定 EasyFly commit 94c70cd，不能可靠回溯上游。恢复开发前应为每个导入目录增加 UPSTREAM.md，记录仓库 URL、branch、commit、导入日期和本地 patch。

## 5. 版本快照命令

每轮正式验收前执行并保存输出：

~~~bash
git rev-parse HEAD
git status --short
git diff --stat

lsb_release -ds
uname -a
gcc --version
cmake --version
python3 --version
gazebo --version

dpkg-query -W \
  ros-humble-rclcpp \
  ros-humble-rmw-fastrtps-cpp \
  ros-humble-mavros \
  ros-humble-mavros-msgs \
  ros-humble-libmavconn \
  ros-humble-mavlink \
  ros-humble-gazebo-ros-pkgs \
  ros-humble-gazebo-plugins \
  libopencv-dev libpcl-dev libeigen3-dev libyaml-cpp-dev

git -C /home/jia/PX4-Autopilot-1.16.2 describe --tags --always --dirty
git -C /home/jia/PX4-Autopilot-1.16.2 rev-parse HEAD
git -C src/communication/c1_drivers/realsense_ros describe --tags --always --dirty
git -C src/communication/c1_drivers/realsense_ros rev-parse HEAD

nvidia-smi
nvcc --version
sha256sum models/yolo11n.onnx
~~~

## 6. 总体验收门禁

~~~text
G0 版本与工作树冻结
 ↓
G1 接口、静态检查和分层干净构建
 ↓
G2 纯逻辑单元测试
 ↓
G3 无 PX4 的节点级故障注入
 ↓
G4 最小 PX4/Gazebo/MAVROS 稳定性
 ↓
G5 控制链 T1-T9
 ↓
G6 感知链逐层恢复
 ↓
G7 跟随 F1-F6 与全局导航 N1-N5
 ↓
G8 EGO E1-E4
 ↓
G9 长时间、重复启停与资源测试
 ↓
G10 实物台架/HIL
 ↓
G11 受控实机飞行
~~~

上一级不通过，不进入下一级。

### 6.1 与 plan.md 开发阶段的对应关系

test-v2 的 G0-G11 是质量门禁，plan.md 的阶段〇至六是功能开发顺序。验收时按下表组合使用：

| plan.md 阶段 | 对应门禁 | 当前适用性 |
|---|---|---|
| 阶段〇 基础设施 | G0、G1、G2 | 可直接执行；验证版本冻结、干净构建、接口和单测 |
| 阶段一 通信+仿真 | G3、G4，加 RealSense/Livox/RC/串口专项 | 可执行；必须先解决最小 SITL 姿态故障 |
| 阶段二 控制闭环 | G3、G5 | 可执行；P0 mock 后再跑 T1-T9 |
| 阶段三 感知流水线 | G6 | 可执行；按传感器→TF→检测→SLAM→跟踪→融合逐层恢复 |
| 阶段四 规划+避障 | G7、G8 | 部分可执行；A*/跟随已有套件，EGO 仍有阻塞，精确降落等尚未实现 |
| 阶段五 任务+应用 | 在 G8 后新增 SDK/API/任务专项门禁 | 当前不能完整执行；多数包仍是骨架 |
| 阶段六 UI+媒体+打磨 | G9、G10、G11，加 UI/视频专项 | 当前只能执行稳定性框架；UI 和媒体功能尚未实现 |

所以可以沿用最初的阶段顺序重新验收，但每个阶段只能在其前置门禁通过后开始。阶段五、六不能因为目录和包存在就判定通过，届时必须在本文件中补充具体接口、媒体、UI 和端到端验收用例。

## 7. G0：冻结基线

验收条件：

- 主仓库 commit 已记录；
- 当前 P0 diff 已保存或提交；
- realsense_ros 和 PX4 的独立 dirty 状态已保存；
- 所有外部依赖版本已记录；
- 参数文件和模型 SHA-256 已记录；
- 测试期间不再合入功能修改。

任何修复都应产生新的基线编号，并从受影响的最低门禁重新开始。

## 8. G1：接口与分层干净构建

### 8.1 使用隔离目录

不要删除现有 build/install。使用：

~~~bash
source /opt/ros/humble/setup.bash
colcon --log-base log-v2 build \
  --base-paths src \
  --build-base build-v2 \
  --install-base install-v2 \
  --symlink-install
~~~

当前不建议第一步直接全量构建。按组进行：

### 8.2 第一组：接口与控制

~~~bash
colcon --log-base log-v2 build \
  --base-paths src \
  --build-base build-v2 \
  --install-base install-v2 \
  --symlink-install \
  --packages-up-to \
    easyfly_msgs easyfly_mavlink_bridge easyfly_flight_control \
    easyfly_mission_fsm easyfly_rc_receiver
~~~

### 8.3 第二组：感知基础

~~~bash
source install-v2/setup.bash
colcon --log-base log-v2 build \
  --base-paths src \
  --build-base build-v2 \
  --install-base install-v2 \
  --symlink-install \
  --packages-up-to \
    easyfly_camera_calib easyfly_coord_transform \
    easyfly_pointcloud_filter easyfly_object_detection \
    easyfly_multi_object_tracking easyfly_pixel_to_3d \
    easyfly_semantic_map
~~~

### 8.4 第三组：规划

~~~bash
source install-v2/setup.bash
colcon --log-base log-v2 build \
  --base-paths src \
  --build-base build-v2 \
  --install-base install-v2 \
  --symlink-install \
  --packages-up-to \
    easyfly_global_planner easyfly_local_planner ego_planner
~~~

### 8.5 驱动单独处理

librealsense2、realsense2_camera、livox_sdk2、livox_ros_driver2、fast_lio 分别构建，避免一个 SDK 阻塞整个报告。librealsense2 如发生联网 FetchContent，先记录失败，不应无限等待或把旧安装当作新构建结果。

验收标准：

- 每个包从空 build-v2 成功；
- 没有链接到意外的旧工作区 install；
- warnings 分类记录；
- 生成依赖图；
- librealsense 阻塞必须有明确处理方案。

## 9. G2：纯逻辑单元测试

当前明确存在的 EasyFly 逻辑测试：

| 包 | 测试 |
|---|---|
| easyfly_serial | test_loopback |
| easyfly_pointcloud_filter | test_filter_core |
| easyfly_multi_object_tracking | test_sort、test_id_consolidator |
| easyfly_global_planner | test_astar |

执行：

~~~bash
colcon test \
  --build-base build-v2 \
  --install-base install-v2 \
  --packages-select \
    easyfly_serial easyfly_pointcloud_filter \
    easyfly_multi_object_tracking easyfly_global_planner

colcon test-result --test-result-base build-v2 --verbose
~~~

注意：历史 ament lint 有大量失败。报告应分别列出：

- gtest 功能断言；
- copyright；
- cpplint/uncrustify；
- CMake/XML/Python lint。

不能因为 test_astar 8/8 通过就隐藏同包 lint 失败，也不能因为 lint 失败就误称 A* 算法测试失败。

## 10. G3：无 PX4 的组件与故障注入

### 10.1 P0 FlightController mock

终端 A：

~~~bash
source /opt/ros/humble/setup.bash
source install-v2/setup.bash
ros2 run easyfly_flight_control flight_control_node \
  --ros-args -p use_sim_time:=false
~~~

终端 B：

~~~bash
source /opt/ros/humble/setup.bash
source install-v2/setup.bash
python3 test/p0_flight_controller_mock.py
~~~

当前预期 14/14：

- Action server；
- 起飞事务；
- 非有限 Goal；
- 旧轨迹 ID；
- 错误 frame；
- WAIT cancel；
- 旧时间 N+1；
- 新 ID 激活；
- TRAJECTORY encoder；
- ACTIVE ID 回退；
- 流中断；
- 并发 Goal；
- Waypoint cancel；
- Land cancel 和 OFFBOARD 确认。

### 10.2 还应补齐的组件测试

- Bridge：错误 frame、零时间戳、未来/过期时间、NaN/Inf、推力越界、watchdog。
- UAVState：各遥测 freshness 独立过期，发布快照一致。
- MissionFSM：双 Goal、电池无效宽限、低电量、取消、析构 join。
- traj_server：非法 knot、NaN、时间倒退、未来 start_time、仿真暂停。
- Topic 所有权：/mission_status 只有 MissionFSM 发布。

这些测试应尽量不启动 Gazebo，以便快速、确定性执行。

## 11. G4：最小 PX4/Gazebo/MAVROS 稳定性

这是当前最优先的系统阻塞项。只启动：

- empty.world；
- PX4 SITL；
- MAVROS；
- easyfly_mavlink_bridge；
- 必要时 flight_control，但不发飞行 Goal。

暂不启动相机、Livox、FAST-LIO、YOLO、EGO、RViz。

分四步：

1. 地面静置 5 分钟：检查时钟、姿态、local pose、EKF、MAVROS connected。
2. 只发送稳定位置 setpoint，不解锁：检查 setpoint 频率与数值。
3. 起飞到 1.5m，悬停 2 分钟，再降落。
4. 重启会话三次，每次重复。

必须记录：

- Gazebo real_time_factor；
- /clock 是否倒退或跳变；
- PX4 estimator status 和 failsafe；
- roll/pitch/yaw 原始曲线；
- MAVROS local_position 与 Gazebo ground truth；
- CPU/内存；
- PX4 ulog。

若再次出现 Attitude failure (roll)，使用二分法：

~~~text
PX4 + 原生 iris
→ 加 EasyFly iris 模型
→ 加 MAVROS
→ 加 Bridge
→ 加 FlightController
→ 加传感器插件
~~~

找到首次出现故障的最小组合。不能直接把它归因于“会话劣化”，也不能在故障未解释时继续 EGO 验收。

## 12. G5：控制链 T1-T9

现有入口：

~~~bash
bash test/run_control_regression.sh
~~~

实际脚本当前运行 T1-T9；test/README.md 仍写 T1-T8，需要后续统一文档。

| 用例 | 验收目标 |
|---|---|
| T1 | /uav_state、模式和 Action server 就绪 |
| T2 | 起飞与悬停 |
| T3 | 航点往返 |
| T4 | Waypoint cancel 后就地悬停 |
| T5 | Land cancel 后恢复 OFFBOARD |
| T6 | 连续起降 |
| T7 | 非法任务文件不崩溃 |
| T8 | 低电量触发 AUTO.RTL 与任务中止 |
| T9 | 合成轨迹到达、断流和取消 |

准入条件：G4 连续三轮无姿态故障。

通过标准：

- 所有硬断言通过；
- 无 crash、Action 悬挂、unexpected mode、NaN 或 failsafe；
- T8 信息性落地未确认时必须单独记录；
- T1-T9 连续两轮通过；
- 两轮之间完整清理进程并检查没有残留 publisher。

## 13. G6：感知链逐层验收

按以下顺序逐层增加，禁止一步启动全链：

### 13.1 传感器与 TF

- 相机 color/depth/camera_info 频率、编码和 QoS；
- Livox CustomMsg 与 IMU 频率；
- odom→base_link→camera/livox TF 连通；
- frame_id、stamp 和 ROS time 一致；
- 仿真暂停/恢复无时间倒退。

### 13.2 目标检测

- 明确日志显示 CUDA EP；
- 固定模型 SHA-256；
- 与保存的 m2_frame.bin / m2_baseline.json 对拍；
- GPU 和 CPU fallback 分开报告；
- 记录预处理、推理、NMS 和端到端延迟。

### 13.3 FAST-LIO

- 地面静止完成 IMU 初始化；
- /Odometry 和点云频率；
- 静止漂移、直线漂移和回环后误差；
- map→odom 不出现阶跃；
- 不使用 teleport 测 SLAM。

### 13.4 跟踪和 3D 融合

- SORT 遮挡与交叉；
- ID consolidation；
- tracks 与 depth 时间差；
- 无效深度不得生成有效世界坐标；
- odom frame 输出与 TF 对齐；
- 固定目标的 3D 误差。

### 13.5 语义地图

- 地面剔除；
- TF 跳变守卫；
- occupancy 持久化；
- 聚类覆盖率；
- GetObstacles 距离过滤。

每层至少保存 60 秒 rosbag，再进入下一层。

## 14. G7：目标跟随与 A* 导航

### 14.1 跟随

~~~bash
bash test/run_follow_acceptance.sh
~~~

当前冻结定义为：

- F1 就绪；
- F2 静态距离；
- F3 移动距离和最小间距；
- F4 感知断流/目标丢失后 abort 与悬停；
- F5 用户 cancel 后 CANCELED 与悬停；
- F6 外部 AUTO.RTL 接管后 ABORTED（AUTO.LAND 走同一让位代码路径，但尚未单独动态验收）。

### 14.2 A* 导航

~~~bash
bash test/run_navigate_acceptance.sh
~~~

N1-N5 检查就绪、绕障、返程、取消和障碍内目标。验收目标必须从实时 odom/障碍数据自锚定，不能直接使用 Gazebo 世界坐标。

通过标准：各套件在重启后的独立会话连续两轮通过，无残留进程、无低电量串扰、无 GUI/GLX 影响。

## 15. G8：EGO-Planner

~~~bash
bash test/run_ego_acceptance.sh
~~~

| 用例 | 当前要求 |
|---|---|
| E1 | 静态绕障、最小间距、到达误差 |
| E2 | 动态重规划、直接测量动态目标间距、到达 |
| E3 | traj_server 中断后快速 abort 并悬停 |
| E4 | 外部接管后 FollowTrajectory 让位 |

准入条件：

- G4、G5、G6、G7 全部通过；
- EGO 输入点云已明确处理地面；
- /position_cmd 为 odom、ROS time 和递增 trajectory_id；
- EGO 与 ego_to_mavros 不得同时向 MAVROS 发布 setpoint；
- PX4 姿态故障已解决。

当前 E2 不能只用立柱相对几何间接证明动态行人安全；必须能够直接识别或获得动态目标真值并计算最小间距。

## 16. G9：稳定性与重复性

通过全部功能套件后执行：

- 30 分钟地面运行；
- 30 分钟悬停/任务循环；
- 至少 10 次完整启动/关闭；
- 至少 3 次连续起降；
- kill/restart 感知、planner、MissionFSM、traj_server；
- ROS time 暂停/恢复；
- CPU/GPU 压力下观察 deadline 和 watchdog；
- 检查进程、共享内存、DDS participant、GPU 显存和 Gazebo 资源是否泄漏。

任何需要“重启机器后偶尔能过”的测试都不能算稳定通过。

## 17. G10/G11：实物台架与实机

### 17.1 上桨前

- 无桨台架；
- 飞控、RC、kill switch、模式切换；
- MAVROS 与 Bridge；
- 坐标方向和 yaw；
- setpoint watchdog；
- 断网、节点崩溃、计算机重启；
- 低电量和 GPS/定位丢失；
- 传感器时间同步；
- RealSense、Livox 固件与外参。

### 17.2 HIL/系留

- 限制高度和速度；
- 独立安全员；
- 手动接管优先；
- geofence；
- 逐项验证起飞、悬停、降落和取消；
- 规划与感知故障时不得继续自主飞行。

### 17.3 自由飞行

只有 G0-G10 都有签字记录后进行。从最小控制开始，不直接运行完整 EGO/感知任务。

## 18. 失败分类与处理

| 类型 | 示例 | 处理 |
|---|---|---|
| CODE | 崩溃、竞态、错误 Action 终态 | 修复后从受影响最低门禁重跑 |
| CONTRACT | frame、stamp、QoS、单位错误 | 阻塞所有下游测试 |
| ENV | 缺库、GLX、端口、权限 | 固化环境后重跑，不算功能通过 |
| PX4 | EKF、姿态、failsafe | 保存 ulog，先在 G4 最小化 |
| FLAKY | 同版本结果不一致 | 至少三次复现，未定位前按失败 |
| TEST | 脚本断言或 API 自身错误 | 修测试，并证明原测试是否是假阳性 |
| PERF | RTF、频率、延迟不达标 | 记录资源曲线，不能用功能 PASS 覆盖 |

## 19. 当前最先执行的验收批次

建议下一步只做以下四项，不启动完整感知链：

1. G0：保存主仓库、PX4、realsense_ros 和依赖版本。
2. G1：用 build-v2/install-v2 构建接口与控制组。
3. G2/G3：功能 gtest、P0 mock、Bridge/Mission/traj_server 故障注入。
4. G4：最小 PX4/Gazebo/MAVROS 二分定位 Attitude failure (roll)。

只有这四项稳定通过，才进入 T1-T9 和后续感知/规划验收。
