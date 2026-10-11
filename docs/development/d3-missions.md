# D3 版本化任务、搜索与示例

本批实现第一版严格顺序任务，复用同一 C++ SDK 和现有动作服务器，不发布 UAVCommand / MAVROS setpoint。用户确认失败即终止；取消/超时只取消所属子动作，不自动追加返航或降落。原有独立低电量 RTL 保护仍保留。条件分支、重试、事件式跟随结束条件、螺旋/栅格搜索和实机验证不属于本批交付。

## 格式与离线校验

```yaml
schema_version: 1
frame_id: odom
units: {position: m, angle: rad, time: s}
failure_policy: abort
steps:
  - {type: takeoff, altitude: 1.5, timeout: 60}
  - {type: hover, duration: 2, timeout: 10}
  - {type: land, timeout: 60}
```

仅支持单个 YAML 文档、版本 1、odom、m/rad/s；failure_policy 可省略，默认 abort。拒绝未知/重复字段、非法类型、非有限数值、带引号数值及不支持步骤。JSON/根级 flow 文档不支持。文件必须为常规文件且不超过 64KiB，步骤数 1–256。每步 timeout 默认 120s，范围 0.05–3600s；正式 YAML 的步骤预算总和不超过 7200s。

| type | 必填字段 | 可选字段与默认值 | 静态范围 |
|---|---|---|---|
| takeoff | altitude | climb_speed=1 | 高度 0.01–50m，爬升速度 0.01–20m/s |
| hover | duration | — | 0–3600s，且不超过 timeout |
| waypoint | x, y, z | yaw=0, max_speed=2, acceptance_radius=0.5 | x/y ±1000m，z 0–50m，yaw ±π，速度 0.01–20m/s，半径 0.05–5m |
| navigate | x, y, z | max_speed=2 | 同上位置/速度范围；调用统一 /navigate |
| track | target_id, duration | follow_distance=2, follow_height=0 | ID 为十进制整数 -1–INT_MAX；时长 0.01–3600s 且不超过 timeout，距离 0.1–30m，高度偏移 ±10m |
| search | center_x, center_y, area_width, area_height, altitude, pattern | max_speed=1 | 中心 ±1000m，宽/高 0.1–100m，高度 0.5–50m，速度 0.01–20m/s；pattern 仅 boustrophedon |
| land | — | — | 仅通用 timeout |

静态校验不是飞行准入：实际节点的飞行边界、地图、定位、跟踪目标及飞控状态还须满足运行时要求。任务在接受前校验全文；执行前有界等待所有所需动作及受管所有权服务就绪，不能因后半份格式非法或后续动作服务器缺失先起飞。后续运行时动作拒绝仍会终止任务，不承诺提前验证将来的动态环境。

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run easyfly_mission_fsm mission_validate \
  src/application/a3_mission/easyfly_mission_scripts/missions/takeoff_hold_land_v1.yaml
```

该命令不初始化 ROS、不发送 Goal。旧扁平 `.mission`（以及历史上只是改了后缀的旧文件）按内容兼容读取，仍限 takeoff/waypoint/hover/land；并非因此支持任意 YAML/JSON。私有无后缀快照也按内容识别。共享校验器同时用于任务门面和执行器，避免两处格式判断分叉。

## 顺序执行与真实终态

MissionStatus 的 current_waypoint / total_waypoints 在正式任务中表示步骤索引/总步骤数；步骤结束才增加任务进度，不将等待时间伪装成航程。hover 只等待并沿用下层既有保持行为，没有新增通用悬停控制出口；地面旧任务 hover 仍可作纯等待。

限时 track 从真实准入开始计时。指定时长到达后精确取消该 TrackTarget，收到真实 CANCELED 才作为该步骤正常完成；提前 SUCCEEDED、取消拒绝/异常、超时或终态未确认均不是完成。处置预算耗尽可先向上报告失败，但未决执行继续保锁并排空；不能继续下一步或据此自动降落。

定位数值非法、遥测过期、外部 RTL/LAND 接管会失败关闭；本任务自己的 land 不误判为外部接管。电池无效或数值非法沿用有界宽限，低电量保护独立处理。数据 header 使用 ROS 时钟，超时/持续时长和接收新鲜度使用 steady 时钟；SDK 的 result_received_seconds 不是 UTC 时间。模拟系统必须统一 use_sim_time，未收到有效 /clock 不视为新鲜。

## 跨层所有权与门面

公开 Action 终态可能早于其内部子动作/规划 STOP 完成。D3 增加 GetActionOwnership 服务，以精确 Goal UUID（32 位小写十六进制）查询：/navigation/ownership、/search/ownership、/mission/ownership。OWNED 继续保锁；只有匹配 UUID 的 RELEASED 才能排空。UNKNOWN、错误回显、超时或服务丢失均不当作释放。每层保存最近 128 个已释放 UUID；淘汰后 UNKNOWN，活动所有权不靠时间淘汰。节点重启导致未知状态时没有自动强制解锁，操作员必须另行确认实际控制状态。

SDK Snapshot 区分 action_terminal_received 与 remote_execution_pending；即使公开 status 已 FAILED/CANCELED，执行仍可能未排空。生产任务执行器、搜索和运动示例设置 require_managed_ownership=true。C++ ClientOptions 与 Python 构造函数的该选项默认 false，以兼容独立旧动作服务器；默认模式只有发现对应所有权服务时才采用排空协议，不提供强制受管保证。

任务服务仍提供目录内 list / validate / start / query / cancel，不增加任意路径写入。ManageMission 新增 execution_pending；公开终态已收到但内部未释放时，该字段仍为 true，目录快照保留，新任务被拒绝。取消响应与真实结果分别保存，迟到取消拒绝不会覆盖真实失败结果。GetCapabilities 将 legacy_mission、versioned_mission 和 boustrophedon 搜索与运行时 ready 区分；ready 不是运动许可。

新增 srv、ManageMission 字段和 SDK API 要同步重新编译 easyfly_msgs、core/pybind、规划器、执行器、服务、示例及外部 SDK 消费者。公开飞行动作 Goal 字段不改。不是 wire/ABI 无变化的升级。

## SearchArea 第一版

真实 /search_area 将矩形拆成弓字条带，每个端点调用统一 /navigate；只支持模式 1 / boustrophedon。启动参数均只读：strip_spacing=2m（0.1–20）、segment_timeout=60s（0.05–3600）、total_timeout=300s（0.05–7200）、cancel_timeout=5s（0.05–30）。默认可飞范围 x/y [-50,50]m、z [0.5,2.5]m，矩形整体须在范围内，条带最多 256 条。独立部署须将这些边界与飞控/导航配置同步，不能只修改搜索边界。

条带数 ceil(area_height/strip_spacing)，实际带宽 area_height/条带数。只有整条扫描段真实成功，且新鲜遥测证明到达（位置误差 ≤0.15m、速度 ≤0.3m/s），才累计 area_width×实际带宽；进场/条带转移不计覆盖。迟到成功不越过期限，也不启动下一段。取消保留已完成条带的部分面积。面积和进度为几何覆盖估计，不代表传感器实际视场/检测覆盖，不宣称整个区域已被可靠感知。

targets_found 对搜索期间区域内的稳定非负 ID 去重，使用 /target_positions 的数组及条目时间、odom、position_valid、有限位置和置信度检查；忽略过期、越界及无效观测。最多接收每帧 10000 条和累计 4096 个不同 ID，超预算失败关闭。发现数与已完成条带面积独立，不把逐帧检测数相加，不新增视觉模型或预测能力。

## 安装模板与示例

mission_scripts 仅安装四份模板：takeoff_hold_land_v1.yaml、navigation_return_v1.yaml、search_land_v1.yaml、timed_track_land_v1.yaml；唯一任务执行器仍是 mission_fsm。绕障模板调用统一导航，是否真实绕障取决于所启动策略、地图和场景，不靠文件名保证。

```bash
# 默认只离线校验，不自动运动：
ros2 run easyfly_demos sdk_mission_demo
ros2 run easyfly_demos sdk_mission_demo.py
# 仅在已准备且准入有效的平台显式执行；模拟图加 --sim-time：
ros2 run easyfly_demos sdk_mission_demo --execute --cancel-after 2
ros2 run easyfly_demos sdk_mission_demo.py --execute --cancel-after 2
```

两种示例都复用 C++ SDK，实际取消指定任务并等待真实排空；未确认返回失败，不以退出进程作为飞行已停证明。可用 --mission PATH 选择模板。默认任务门面的目录仍是旧任务目录，防止升级后悄悄改变原列表；需要管理新模板时显式启动：

```bash
ros2 launch easyfly_mission_srvs platform.launch.py use_sim_time:=false \
  mission_directory:=/home/jia/easyfly_ws/src/application/a3_mission/easyfly_mission_scripts/missions
```

上面是本工作区路径。部署时可用 ament_index 的 easyfly_mission_scripts share 目录找到模板，再对模板文件 Path.resolve().parent 求规范父目录；--symlink-install 下单个文件可能指向源码，不能把未解析的安装目录误当作受信目录。任务门面要求规范化后的文件父目录与允许目录一致，保留此安全边界。

platform.launch.py 默认不启动执行器，也不启动飞控或自动发起任务；仅当尚无执行器时显式 start_mission_executor:=true，现有 profile 已启动 mission_fsm 和 search，勿重复。hardware_unverified 仍禁止启动。验收结果及失败修复见 [schedule-v4](../../schedule-v4.md) 第 9 节，限于组件/软件闭环，不是 PX4/Gazebo SITL 或实机签收。

2026-10-07另补充版本1三步任务和两条几何扫描带的真实PX4/Gazebo有界验收，
检查外层任务/搜索UUID及内层导航UUID全部RELEASED、新鲜disarm和正常退出。
入口见[导航SITL说明](navigation-sitl.md)，原始结果见 `schedule-v4.md` 第20节；
不将几何面积当作实际传感器覆盖，不改变失败即终止或未决子动作保锁语义。

同日任务级导航/搜索取消、原生步骤超时及仿真AUTO.LAND接管六类真实SITL
通过，见 `schedule-v4.md` 第21节。先执行独立正式准备任务并核实实际稳定
高度，再提交被测任务；每类核实子UUID真实终态/载荷、精确释放和会话STOP，
未继续后续哨兵Land。取消/超时排空后另发明确的恢复任务，接管则只等PX4
自行降落，不追加生产失败补偿。搜索取消保留1.65m²已完成条带几何面积。
组件未知结果保锁与实际飞行证据分开；旧初始碰撞/电池失效仍未归因，不
因准备隔离PASS而宣称修复，也不扩展为RC/RTL/POSCTL或实机验收。
