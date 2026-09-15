# EasyFly P0 整改清单

> 生成日期：2026-09-14
> 用途：定义 EasyFly 继续扩展功能之前必须优先解决的问题，以及相应的修改与验收方法。
> 范围：本文记录 P0 问题、已实施方案与验收标准；2026-09-14 已由 Codex 按“编码 Agent → Review Agent → 主 Agent 验收”流程实施。

## 0. 当前实施状态（2026-09-14）

P0-1 至 P0-5 已完成代码整改，并通过受影响组件构建、静态检查和 FlightController 确定性故障注入测试。主要落地内容如下：

- **P0-1**：局部世界系统一为 `odom`/ENU/Z-Up；消息接口补齐 frame、时间戳与有效性契约，Bridge 和 FlightController 拒绝错误 frame、过期时间戳和非有限控制值。
- **P0-2**：EGO 使用节点 ROS clock，校验 B-spline 并处理时钟跳变；FlightController 在首条有效轨迹到达前保持进入轨迹前的悬停点，并绑定新轨迹 ID。
- **P0-3**：FlightController 的 Goal 预留、状态转换、取消和完成路径已并发保护；所有已接受 Goal 都有确定的成功、取消或中止终态。
- **P0-4**：起飞/降落改为显式准备与确认事务；降落准备阶段持续发送安全悬停 setpoint，AUTO.LAND 与取消恢复 OFFBOARD 的服务事务串行化。
- **P0-5**：`MissionStatus` 仅由 MissionFSM 发布；遥测增加 freshness/validity，Bridge 使用锁内一致快照；MissionFSM 使用可回收 worker，并对电池数据失效设置宽限期与空中 RTL 策略。

当前验收边界：代码与组件级 P0 验收已通过；完整 PX4/Gazebo SITL 尚未通过，因为两次运行均在进入 EGO 轨迹阶段前由 PX4 报告 `Attitude failure (roll)` 并触发 failsafe。该环境/飞行器姿态异常需要单独排查，因此本文不把“完整实机等价飞行链路”标记为已验收。

## 1. 总体判断

EasyFly 当前的分层方向基本合理：

```text
Application / Mission
        ↓ ROS Action
Planning / Tracking
        ↓ ROS Action 或 PositionCommand
Flight Control（飞行状态机、setpoint 生成）
        ↓ UAVCommand
MAVLink Bridge（协议适配）
        ↓ MAVROS / PX4
```

感知侧的“传感器 → 检测/跟踪 → 三维目标/地图 → 规划”分层也可以保留。现阶段不建议大规模重新划分目录或重写全部节点，应该先把以下四条系统契约收紧：

1. **飞行命令只能有一个明确的仲裁者和状态所有者。**
2. **所有规划、状态和控制消息必须使用统一的坐标系、方向和时间源。**
3. **进入飞行状态前必须先满足数据有效性和模式切换条件。**
4. **安全相关 Topic 必须有唯一权威发布者，不能用默认值冒充有效数据。**

P0-1 至 P0-5 已按本文顺序完成。后续可以进入完整 SITL 环境故障排查；在该验收通过前，不建议把当前结果视为实机放飞依据。

---

## 2. 建议执行顺序

| 顺序 | 编号 | 问题 | 原因 |
|---:|---|---|---|
| 1 | P0-1 | 统一坐标系、Z 方向、frame 和时间源 | 这是所有模块之间的基础契约，后续修复都依赖它 |
| 2 | P0-2 | 修复 EGO 轨迹时间源与轨迹首帧门控 | 当前可能直接产生错误飞行 setpoint |
| 3 | P0-3 | 收敛 FlightController 的状态所有权和并发模型 | 当前存在数据竞争和双 Goal 同时进入的窗口 |
| 4 | P0-4 | 重构飞行前置条件、降落事务和输入校验 | 避免模式切换失败或非法数值进入 PX4 |
| 5 | P0-5 | 统一 MissionStatus 与遥测有效性 | 避免状态被覆盖、未知电量误触发或漏触发 RTL |

完成每一项后先做对应单元/组件测试；五项全部完成后，再进行完整 SITL 验收。不要把多项修改后的首次验证直接放到长时间全链路仿真中，否则很难定位回归来源。

---

## 3. P0-1：统一坐标系和时间契约

### 3.1 当前问题

当前代码实际采用的主世界系是 `odom` 下的 ENU：X 向东、Y 向北、Z 向上。MAVROS `/local_position/pose` 的 Z 被直接写入 `UAVState.position_z`，起飞、降落和规划也都把正 Z 当作上升。

但是 `easyfly_msgs/msg/UAVState.msg` 当前写着：

```text
position_z # 负值表示高于 home
```

这与实现相反。另外，状态和 setpoint 有的填写 `map`，EGO 输出填写 `world`，局部规划输入使用 `odom`，而 FlightController 目前不检查输入 frame。这样即使数值恰好能跑，也没有可靠的模块边界契约。

时间方面，仿真设置了 `use_sim_time=true`，但 EGO `traj_server.cpp` 使用独立的默认 `rclcpp::Clock` 获取当前时间。默认 Clock 可能处于 system time 域，而轨迹 `start_time` 属于 ROS time 域。

### 3.2 目标契约

P0 阶段建议固定为：

```text
局部世界坐标系：odom
局部位置和速度：ENU，X East / Y North / Z Up
姿态和 yaw：ROS ENU 语义，yaw=0 指向 +X，逆时针为正
全局地图：如果暂时没有闭环重定位，map 与 odom 不混用
节点当前时间：node->get_clock()->now()
消息时间：必须和节点的 ROS clock 属于同一 time domain
```

PX4/MAVLink 内部需要 NED 时，只允许在 MAVROS/Bridge 边界转换。上层节点不能同时承担 ENU/NED 猜测或隐式换轴。

### 3.3 推荐修改

1. 修正 `UAVState.msg` 的 `position_z` 注释为“ENU，正值表示高于局部原点”。同时审计 roll/pitch/yaw 和角速度的 frame 注释，不要在消息里把位置写成 ENU、姿态笼统写成 NED。
2. `UAVState.header.frame_id` 使用实际来源 frame。当前主链建议统一填 `odom`，不要填没有对应 TF 语义的 `map`。
3. `UAVCommand` 应明确声明其位置、速度和 yaw 全部属于 `header.frame_id`；正常飞行命令固定要求 `odom`。
4. 所有命令生产者必须设置 `header.stamp` 和 `header.frame_id`。FlightController 和 MAVLink Bridge 在消费命令时检查：
   - frame 是否为允许值；
   - 时间戳是否有效、是否过旧、是否来自未来；
   - 所有参与控制的数值是否为有限值。
5. EGO `PositionCommand.header.frame_id` 从硬编码 `world` 改为参数，EasyFly 启动配置中设置为 `odom`。
6. 不建议仅用字符串替换 `map/world/odom`。应沿以下链路逐项核对：

```text
/mavros/local_position/pose
  → UAVState
  → /odom
  → pointcloud_filtered / EGO
  → PositionCommand
  → UAVCommand
  → /mavros/setpoint_*
```

### 3.4 验收标准

- 接口注释、消息 `header.frame_id`、TF 树和实际数值方向一致。
- 静止在地面时 Z 接近局部原点；起飞后 Z 为正且随高度增加。
- 给定 `(x+1, y, z)` 和 `(x, y+1, z)` 指令时，RViz、里程计和 PX4 运动方向一致。
- 所有送入 FlightController 的规划轨迹都明确为 `odom`；错误 frame 的命令会被拒绝并报告原因，而不是直接飞行。
- 仿真暂停时 ROS time 不前进；恢复后轨迹从正确的相对时刻继续，不发生瞬间跳到终点。

---

## 4. P0-2：修复 EGO 时间源和轨迹首帧门控

### 4.1 当前问题

`traj_server.cpp` 中存在全局：

```cpp
rclcpp::Clock _clock;
```

轨迹起点来自 `Bspline.start_time`，而 `cmdCallback()` 使用 `_clock.now()` 计算 `t_cur`。在 `use_sim_time=true` 下，两者可能不属于同一时钟域，导致：

- `t_cur` 远大于轨迹总时长，直接进入“轨迹结束”分支并发布终点；
- 时间倒退或跳变时发布零位置；
- 轨迹时间和消息时间戳不一致。

FlightController 的 TRAJECTORY 分支还有第二个问题：在 Action 已进入 TRAJECTORY、但第一条有效 `/position_cmd` 尚未到达的宽限期内，代码仍然使用默认构造的 `PositionCommand` 发布 `(0,0,0)`。

### 4.2 推荐修改：traj_server

首选方案是把 `traj_server` 从全局变量/自由函数改成一个 Node 类，使以下状态都归节点实例所有：

- 轨迹对象、轨迹 ID、开始时间、总时长；
- yaw 状态；
- publisher、subscription、timer；
- ROS clock。

关键规则：

```cpp
const auto time_now = this->get_clock()->now();
const rclcpp::Time start_time(msg->start_time, this->get_clock()->get_clock_type());
```

必须显式保证 `time_now` 和 `start_time` 的 clock type 相同。不要继续保留独立默认 `_clock`。

对时间异常增加防御：

1. `t_cur < -允许抖动`：不发布轨迹位置，输出节流错误日志。
2. `t_cur` 只有轻微负值：可以钳制为 0。
3. 检测 ROS time 大幅倒退时：使当前轨迹失效，等待新轨迹，而不是发布零点。
4. 轨迹结束后可继续发布终点悬停，但应把完成状态表达清楚；不要让消费者只能根据位置猜测轨迹是否结束。
5. 收到新 B-spline 时校验控制点、knots、duration 和所有浮点数均为有限值。

`create_wall_timer` 可以保证 PX4 setpoint 刷新频率不因 ROS time 暂停而完全中断，但轨迹采样时刻仍必须使用节点 ROS clock。如果希望 timer 本身也严格遵循仿真时间，应改用绑定节点 clock 的 ROS timer；二者需要根据“仿真暂停时是否仍应维持 OFFBOARD 流”的策略统一决定，不能无意混用。

### 4.3 推荐修改：FlightController 首帧门控

TRAJECTORY 状态必须拆成至少两个阶段：

```text
TRAJECTORY_WAITING_FIRST_COMMAND
TRAJECTORY_ACTIVE
```

进入等待阶段时：

1. 保存进入轨迹前最后一个安全悬停点。
2. 清空上一条轨迹的缓存和轨迹 ID。
3. 在首条有效新轨迹到达前，持续发布保存的悬停 setpoint。
4. 首条命令必须满足：frame 正确、时间新鲜、轨迹 ID 属于当前请求、位置/速度/yaw 有限。
5. 通过校验后才能切换为 ACTIVE 并开始转发。
6. startup grace 超时则 abort Action，并保持原悬停点。

伪代码：

```cpp
if (state == TRAJECTORY_WAITING_FIRST_COMMAND) {
    publish_hold_setpoint(pre_trajectory_hold);
    if (valid_new_command_available()) {
        state = TRAJECTORY_ACTIVE;
    } else if (startup_timeout()) {
        abort_and_keep_holding("trajectory_start_timeout");
    }
    return;
}
```

不要在 `have_cmd == false` 时读取默认 `PositionCommand` 中的位置。

### 4.4 轨迹身份绑定

当前 FollowTrajectory Goal 只有目标点和超时，没有预期 trajectory ID。这使得 Action 与 EGO 发布流的对应关系比较弱。建议二选一：

- 在 `FollowTrajectory.action` 中增加 `trajectory_id`；或
- FlightController 在接受 Goal 时记录“接受时已见最大 ID”，只接受随后出现且 ID 更大的首条轨迹。

同时拒绝旧 ID、重复倒退 ID 和时间戳早于 Action 接受时刻的命令。

### 4.5 验收标准

- FollowTrajectory 接受后的前 2 秒即使没有 `/position_cmd`，发布的仍是进入前悬停点，绝不出现默认原点。
- 仿真时间和系统时间相差很大时，轨迹仍从 `t=0` 正确开始。
- 暂停/恢复仿真不会瞬间跳到终点。
- 注入旧轨迹 ID、错误 frame、NaN、过期时间戳时，飞行器保持悬停并返回明确失败原因。
- 正常轨迹的 setpoint 位置连续；首帧和相邻帧位移不超过按最大速度/周期计算出的合理上限。

---

## 5. P0-3：FlightController 单一状态所有权与并发安全

### 5.1 当前问题

FlightController 使用 `MultiThreadedExecutor`，状态订阅、控制定时器、Action 回调和服务响应可以并行。`uav_` 与轨迹消息已经有局部锁，但以下核心飞行状态仍由多个线程直接读写：

- `active_`；
- 四种 GoalHandle；
- hover、takeoff、waypoint、trajectory 的目标和 deadline；
- 去抖计数和 takeover 状态。

典型风险：

- 两个 Goal 同时在 goal callback 中观察到可接受状态，随后都被接受；
- control loop 正在成功结束 Goal 时，cancel callback 同时 reset 同一 GoalHandle；
- accepted callback 修改目标的同时，control loop 读取到一半新、一半旧的状态；
- 阻塞式 service wait/sleep 与取消、外部接管之间出现竞态。

### 5.2 推荐架构

推荐采用“**控制循环是飞行状态唯一写入者**”模型：

```text
Action/Topic/Service callback
        ↓ 只校验并投递 Event
线程安全事件队列
        ↓
Control loop
        ├─ 处理事件
        ├─ 执行状态转换
        ├─ 生成唯一 setpoint
        └─ 完成/取消 Action
```

事件至少包括：

```text
TakeoffRequested
LandRequested
WaypointRequested
TrajectoryRequested
CancelRequested
TrajectoryCommandReceived
ModeChanged / ArmResult / ModeResult
ExternalTakeover
```

Goal callback 中要完成原子的“检查并预留”。不能先返回 ACCEPT，再等 accepted callback 才把 `active_` 改掉。可以使用一个受 mutex 保护的 `reserved/active goal token`，或把状态变成 CAS 可更新的原子枚举。

### 5.3 阻塞操作处理

当前 accepted callback 内有多次 `sleep_for`、service future wait 和最多约 10 秒重试。长期方案应改成非阻塞子状态机：

```text
TAKEOFF_PRESTREAM
  → WAIT_OFFBOARD
  → WAIT_ARM
  → TAKEOFF_CLIMB
```

每个控制周期检查 deadline 和异步 service future，不要让 Action 回调线程睡眠。这样取消、RTL 和状态更新都能及时响应。

如果本轮不准备完整重构，最低可接受方案是：

1. 使用同一个 `flight_state_mtx_` 保护全部 `active_`、GoalHandle 和对应目标状态。
2. 所有状态转换通过少数几个 helper 完成，例如 `try_reserve_action()`、`transition_to()`、`finish_action()`。
3. 任何 service wait、sleep、publisher 调用和 Action 回调均不得在持锁状态执行。
4. goal callback 中原子预留槽位；accepted 失败时释放槽位。
5. cancel 和 external takeover 必须具备幂等性，同一 Goal 只能设置一次终态。

### 5.4 验收标准

- 并发发送任意两个 Action Goal，最多一个被接受。
- 在起飞建流、切模式、解锁重试、航点飞行和轨迹等待首帧的任意阶段取消，均能在规定时间内响应。
- cancel、timeout、external takeover 同时发生时，每个 Goal 只进入一个终态，不抛异常、不崩溃。
- 连续执行 `takeoff → waypoint → cancel → waypoint → land → takeoff` 不残留旧 GoalHandle 或旧轨迹。
- 使用 ThreadSanitizer 或等价并发检查时，FlightController 核心状态无数据竞争报告。

---

## 6. P0-4：飞行前置条件、输入校验与模式切换事务

### 6.1 所有飞行输入统一校验

在 Action goal callback 和 MAVLink Bridge 边界都应校验，不依赖某一层独自兜底。

必须检查：

- 所有位置、速度、角度、半径、超时、推力均为 `std::isfinite()`；
- 高度、速度、推力、验收半径在配置允许范围；
- UAVState 已收到且在 freshness 窗口内；
- 当前 armed/mode 与 Action 要求一致；
- position/yaw 数据有效，不能把默认零值当真实状态；
- 命令 frame 和时间戳符合 P0-1 契约。

建议集中实现验证函数，返回结构化失败原因，例如：

```cpp
ValidationResult validate_takeoff_goal(...);
ValidationResult validate_waypoint_goal(...);
ValidationResult validate_trajectory_command(...);
```

不要把非法输入静默替换成默认值。只有明确约定 `0=使用默认值` 的字段才能这样处理；NaN/Inf 必须直接拒绝。

### 6.2 降落必须是事务

当前 `handle_land_accepted()` 在 `AUTO.LAND` 切换失败后仍进入 LANDING，随后控制循环停止 OFFBOARD setpoint。这会让 PX4 进入不可预期的模式或 failsafe。

推荐流程：

```text
收到 Land
  → 保持当前悬停流
  → 请求 AUTO.LAND
  → 等待 UAVState 确认 AUTO.LAND
      ├─ 成功：进入 LANDING，停止由 EasyFly 主导的轨迹
      └─ 失败：保持/恢复 OFFBOARD 悬停，abort Land
```

注意事项：

1. service 返回 `mode_sent=true` 不等于飞控已经进入该模式，必须看状态反馈。
2. `land_timeout_` 参数应真正使用，去掉控制循环中的硬编码 `60.0`，并明确它和配置默认值的关系。
3. 超时且仍在空中时不能强制 disarm；现有这一原则应保留。
4. 取消降落只有在 PX4 确认重新进入 OFFBOARD 后才能报告取消完成；否则应报告“取消失败、PX4 继续降落”。
5. `Land.action` 中如果包含 descent speed，应明确由谁执行。如果使用 PX4 AUTO.LAND 且无法传递该速度，就不要让接口暗示该参数已经生效。

### 6.3 Watchdog 策略

Bridge 当前在上层命令超时后停止发布 setpoint，依赖 PX4 自行退出 OFFBOARD。这可以作为最后防线，但应明确：

- FlightController 正常运行时负责持续产生安全 setpoint；
- Bridge 只做有限值、frame、时间戳检查和协议翻译；
- 命令超时后记录明确错误并暴露健康状态；
- 不要在 Bridge 内自动生成未知来源的“零点”或“当前位置”命令。

### 6.4 验收标准

- NaN、Inf、超范围高度/速度和错误 frame 均在起飞前被拒绝。
- 模式切换 service 返回失败或状态迟迟未确认时，Land abort 且飞机保持原悬停流。
- 正常 AUTO.LAND 切换后才进入 LANDING。
- `land_timeout` 参数修改后，运行时行为随参数改变，不再受硬编码 60 秒控制。
- 上层命令流中断时，日志、Action 结果和 PX4 模式变化三者一致。

---

## 7. P0-5：MissionStatus 单一发布者与遥测有效性

### 7.1 MissionStatus 所有权

当前 MAVLink Bridge 和 MissionFSM 同时发布 `/mission_status`：

- MissionFSM 发布真实任务阶段；
- MAVLink Bridge 在状态定时器中持续发布 IDLE。

结果是任务进行期间也会不断收到 IDLE，任何 UI、记录器或上层状态机都无法可靠判断任务状态。

推荐：

1. 删除 MAVLink Bridge 的 `/mission_status` publisher 和相关发布逻辑。
2. `/mission_status` 由 MissionFSM 唯一发布。
3. MissionFSM 启动时和任务结束后自行发布 IDLE。
4. 如果未来有多个任务执行器，增加独立的 Mission Manager 统一发布，而不是让通信层参与任务语义。

### 7.2 遥测有效性

Bridge 在还没收到电池消息时，`battery_remaining` 默认是 0。MissionFSM 只检查 `<0.15`，因此任务如果早于第一条电池数据启动，可能立即触发 RTL。反过来，电池 percentage 为 NaN 时比较结果为 false，又会漏掉保护。

推荐在 `UAVState` 增加明确的健康/有效性字段，至少包括：

```text
connected
pose_valid
velocity_valid
attitude_valid
battery_valid
gps_valid
state_age 或各数据 header/stamp
```

如果暂时不改消息结构，最低限度也要让 MissionFSM 订阅独立的有效性状态，不能把数值 `0` 当作“未收到”和“真的没电”两种语义共同使用。

低电量逻辑建议为：

```text
未获得有效电池数据：拒绝开始自动任务，或按配置进入降级策略
任务中电池数据短时丢失：告警并计时
超过 freshness timeout：触发预定义 failsafe
有效电量连续 N 帧低于阈值：RTL
NaN / Inf / percentage 不在 [0,1]：视为无效遥测，不视为正常电量
```

阈值和持续时间都应参数化，避免单帧毛刺触发 RTL。

### 7.3 MissionFSM 自身并发

MissionFSM 虽然部分变量已是 atomic，但 `uav_` 仍由订阅线程写、由 safety timer 和任务线程读，缺少快照锁；`mission_active_` 又是在 detached 线程开始执行后才置为 true，两个并发 Goal 存在同时被接受的窗口。

建议：

1. `UAVState` 使用 mutex 保护并通过 `get_uav_snapshot()` 读取。
2. goal callback 使用 `compare_exchange` 原子预留 mission slot。
3. 不使用无法 join 的 detached thread。使用受生命周期管理的 worker、callback 状态机或可在析构时停止并 join 的线程。
4. 所有退出路径使用统一 cleanup，保证 mission slot、子 GoalHandle 和状态 Topic 一致复位。

### 7.4 验收标准

- `ros2 topic info /mission_status --verbose` 中正常情况下只有一个权威 publisher。
- 任务执行期间不再穿插 Bridge 发布的 IDLE。
- 无电池数据、NaN 电池数据和过期数据不会被当作正常电池状态。
- 两个 ExecuteMission Goal 并发到达时只能接受一个。
- 节点关闭或任务取消后没有 detached 线程访问已销毁 Node。

---

## 8. P0 完成后的架构调整建议（暂不阻塞本轮修复）

以下调整有价值，但建议在 P0 修复和回归通过后再实施。

### 8.1 增加 Command Arbiter

目前 MissionFSM、GlobalPlanner、TargetTracking 等通过 Action 间接争用 FlightController。以后加入遥控接管、避障、精准降落和集群控制后，仅靠 `active_` 枚举会越来越难维护。

建议增加明确的命令仲裁层，优先级例如：

```text
PX4 failsafe / emergency
manual takeover
land / RTL
collision avoidance
mission trajectory
target tracking
position hold
```

仲裁输出仍保持单一 `/uav_command`，MAVLink Bridge 不参与业务优先级判断。

### 8.2 Lifecycle 与 readiness

启动文件目前大量使用固定 TimerAction 延迟。固定等待时间不能保证慢机器上的模型、TF、SLAM、PX4 和规划器真的 ready。

建议逐步将关键节点改为 Lifecycle 或提供 readiness/health 状态，按条件启动：

```text
PX4 connected
→ local pose valid
→ TF ready
→ perception ready
→ map ready
→ planner ready
→ allow autonomous action
```

### 8.3 分离启动配置

将全量感知仿真拆成至少三种 profile：

- `minimal_flight`：PX4、MAVROS、Bridge、FlightController；
- `planning_sitl`：增加地图和规划；
- `full_perception`：增加相机、YOLO、FAST-LIO、RViz。

这样可以减少 EGO/FAST-LIO/GUI 同时运行导致的实时率下降，也能让回归测试定位更清楚。

### 8.4 第三方代码适配边界

对 EGO、FAST-LIO 等第三方工程，尽量把 EasyFly 专属修改收口到 adapter 包；无法避免修改第三方源码时，维护独立 patch 说明和回归测试。这样后续升级上游版本时不会丢失关键的时间、frame 和 ROS 2 兼容修复。

---

## 9. 本轮验收记录

本轮已按以下顺序完成审查和验收：

```text
源码 diff 审核
→ 接口/坐标/时钟一致性检查
→ 编译与静态测试
→ 单组件故障注入
→ minimal flight SITL
→ EGO trajectory SITL
→ 完整回归
```

验收时重点检查的不只是“能够飞到终点”，还包括错误输入、首帧延迟、时钟跳变、取消、超时、模式切换失败、状态丢失和并发 Goal 等异常路径。

实际结果：

- 受影响的 `easyfly_msgs`、`easyfly_mavlink_bridge`、`easyfly_flight_control`、`easyfly_mission_fsm`、`easyfly_pixel_to_3d` 构建通过。
- EGO `traj_server` 目标单独构建通过。
- `easyfly_msgs` 接口测试通过（5 项、0 失败）。
- `test/p0_flight_controller_mock.py` 故障注入与状态机测试通过（14 项、0 失败），包括旧轨迹 ID 首帧、被拒帧不污染 ID 水位及 ACTIVE 回退保护。
- Python 测试脚本语法检查与 `git diff --check` 通过。
- 完整 SITL 未通过：PX4 在进入轨迹测试前报告 roll 姿态故障并触发 failsafe；该项保留为独立环境/飞行器问题，不能用组件测试结果替代。
