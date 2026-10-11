# 统一导航的真实 SITL 验收

2026-10-08起默认使用项目局部PX4 HRT兼容版；先显式构建，缺失/指纹不符
拒绝启动，不回退原版。下文 `--px4-dir` 指定受支持原安装时也会选择兼容
版，旧原版结果仍按其实际指纹保留。见[电池SITL说明](battery-sitl.md)。

仅使用主机上的 PX4/Gazebo 仿真，不连接真实飞控。此入口显式发送飞行动作，
不会被 `colcon test` 自动启动。开始前应确认没有其它仿真占用共享 PX4/MAVROS
端口；ROS domain 和 Gazebo 端口不同并不隔离所有飞控通信端口，场景必须串行。

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
evidence_dir=$(mktemp -d /home/jia/easyfly_ws/artifacts/navigation-check.XXXXXX)
ros2 run easyfly_sim_launcher navigation_sitl \
  --px4-dir /home/jia/PX4-Autopilot-1.16.2 \
  --output-dir "$evidence_dir" --domain 220 --gazebo-port 11401 \
  --strategy combined --scenario happy
```

输出目录必须已经存在且为空。使用独立 PX4 rootfs、显式 `-w/-s` 启动包装、
冻结的 DDS 配置、项目私有 Gazebo server，以及 `perception_sitl.launch.py` 的
原模型/CPU 感知负载。不会删除旧证据、修改系统库或重设生产安全阈值。

## 场景

- `happy`：起飞后等待真实高度进入 1.5±0.1m 且连续稳定低速，然后相对当前
  odom 位置沿 +x 导航 2m，检查真实终态、到位误差与同 UUID 所有权释放，再
  显式普通 Land，并确认新鲜 disarmed。支持 `astar`、`ego`、`combined`。
- `cancel`：导航 4m，在实际水平移动至少 0.15m 后精确取消；必须收到真实
  CANCELED 和同 UUID RELEASED。稳定悬停后发送新导航，验证执行锁和会话可复用，
  最后显式 Land。
- `map-loss`：同样先证实真实运动，只向本轮所属且 PID/start_ticks 身份仍匹配
  的 `semantic_map_node` 发送 SIGINT；导航必须 ABORTED、success=false，并确认
  同 UUID 释放。仍拥有新鲜 OFFBOARD、稳定悬停后才执行单独计划的 Land。
- `mission`：生成正式版本 1 YAML，使用 `/execute_mission` 顺序执行起飞、导航、
  降落；检查三步完成反馈、导航步实际位置、真实终态、任务 UUID 与内层导航
  UUID RELEASED。
- `search`：起飞稳定后执行 1.5×2.2m 的弓字形搜索；按默认 2m 条带间距形成
  两条扫描带、四个接近/扫描端点。确认进度 1、几何面积 3.3m²、真实成功、
  搜索 UUID 及四个内层导航 UUID 全部 RELEASED，再显式 Land。面积不是传感器
  实际覆盖，也不保证检测到目标。

`map-loss` 使占据栅格和 EGO 信任点云同时停止，测试的是地图生产者丢失，
并不宣称分别证明每一种地图输入的失效通道。取消 ACK、STOP 通知或 Action
终态都不能独自证明后台已释放，必须查询精确 UUID 所有权。

## 证据与失败处理

`result.json` 保存参数、DDS/启动来源、Action UUID/反馈/真实终态、所有权查询、
会话状态、实际位置及退出结果；`states.jsonl` 保留源时间、ROS 时钟和独立
接收时间；`inputs.jsonl` 保存真实地图/点云/odom 的源时间、尺寸及接收时间，
odom 发布者信息保存在 `result.json`；`console.log` 是原始完整启动日志。
成功还要求新鲜 disarmed、24 个
启动进程全部正常退出、Gazebo transport live=0/pending=0、无所属进程残留。

非预期失败仅精确取消已经受理的本轮动作并等待真实结果/所有权，不自动追加
Land、RTL、上锁或补偿切模式。无法排空会记录错误，无法正常关闭会记录强制
收尾，均不得记 PASS。负向场景的预期终态后 Land 是独立验收步骤，不是生产
任务的失败补偿。不提供真实设备接入，也不是实机安全或障碍绕行认证。

纯谓词测试不启动仿真：

```bash
colcon test --packages-select easyfly_sim_launcher
colcon test-result --test-result-base build/easyfly_sim_launcher
```

实际本轮结果、失败和适用边界见 `schedule-v4.md` 第 20 节。

## 本轮修复与验证边界

A* 在 LOS 剪枝前纳入请求的精确终点，避免格心终点造成假到位；同格目标
仍保留起终点。EGO 只对当前会话实际发布的轨迹执行运行期碰撞检查，不对
已经 STOP 的旧会话曲线误报；新轨迹的完整碰撞检查和输入失效关闭仍保留。
传感器回调使用最新一帧，地图库 Debug 构建保留符号/断言并优化热路径，
不放宽源/接收时间限制、不削减障碍或感知负载。

Livox 仿真插件同时修正初始与逐帧射线起点，遵循
[Gazebo 11.10.2 的量程约定](https://raw.githubusercontent.com/gazebosim/gazebo-classic/gazebo11_11.10.2/gazebo/physics/MultiRayShape.cc)：
射线从最小量程开始，返回最小量程加射线测得的长度。原实现从原点开始却
仍加最小量程，本模型会产生 +0.2m 系统偏差。该修复不改变配置的量程、
外参或 0.3m 点云预处理盲区，不做自身模型过滤，也不跳过近场碰撞。
独立原生 ODE 几何回归验证距离和量程边界，不等同于全场景传感器标定。

本入口验证的是新鲜 `/uav_state` 中的观测位置，不是 Gazebo ground-truth
定位精度认证；搜索面积只代表已完成条带的几何估计。短程已知场景的 PASS
也不证明任意复杂障碍、负载或偶发急停都已解决。原始 FAIL 保留且必须与
对应修复后的独立场景区分，不能仅凭一次复跑成功归因历史故障。

## 任务级取消、超时与仿真接管

额外六个显式场景只支持 `--strategy combined`，不被自动组件测试启动：

| `--scenario` | 注入及预期结果 |
|---|---|
| `mission-nav-cancel` | navigate实际执行后精确取消外层任务，真CANCELED |
| `mission-search-cancel` | 已完成第一条带、第三个导航实际执行后取消，保留1.65m²部分几何面积 |
| `mission-nav-timeout` | 正式任务navigate步骤预算8s到期，真ABORTED/step_timeout |
| `mission-search-timeout` | 正式任务search步骤预算12s到期，真ABORTED/step_timeout |
| `mission-nav-land` | navigate执行中请求仿真外部AUTO.LAND，确认实际模式7及任务失败关闭 |
| `mission-search-land` | search执行中执行相同外部接管验证 |

2026-10-07用户确认独立准备：先用正式任务takeoff(1.5m/0.3m/s)→hover(10s)，
确认该任务真成功并释放，再独立观察实际高度1.5±0.1m、新鲜OFFBOARD及连续
1s低速悬停；不靠固定等待认定准备完成。电池保护在准备任务中仍正常启用，
准备失败不发被测任务。被测任务为hover→navigate/search→Land；最后Land是
不得继续执行的哨兵步骤。旧整段流程的初始碰撞/电池失效FAIL保留，不能用
独立准备的PASS反推其已解决。
注入前不仅要求内层UUID处于EXECUTING，还要观察新鲜TRAJECTORY意图、实际
MAVROS轨迹setpoint和至少0.15m水平运动。保存任务、搜索、导航、FollowTrajectory
UUID状态及精确GetResult载荷、所有权查询和匹配会话STOP；禁止把ACK当作终态。

取消/超时逐层排空后观察无迟到新子动作/后续Land，确认新鲜OFFBOARD和稳定
悬停，再执行独立恢复任务：hover→短程navigate→Land。它是明确的测试步骤，
不是生产失败补偿；未确认释放或非预期失败不会追加该恢复任务。

`*-land`向本轮私有ROS domain的 `/mavros/set_mode` 仅发送一次AUTO.LAND请求；
不重试未知结果，不发本平台Land，不切回OFFBOARD或上锁。接管后等待PX4自己
完成降落。观察 `/uav_command` 以及MAVROS position、velocity、attitude和raw
四类出口。控制器停发与桥接层原1s缓存尾流分开：确认模式后0.5s起控制器
应静默，下游1.5s起至少持续1s静默；接收/调度余量不改变生产TTL。直到新鲜
disarm都不允许重新发布或在仍armed时退回其它模式。

恢复到位记录成功FollowTrajectory UUID的第一次终态事件及当时最新的新鲜
UAVState观测，单独查询GetResult证实载荷；保留后来任务反馈的误差，不把两
个不同时间混为一帧，也不从任意历史窗口挑最小误差。既有动作成功不承诺
上层收到消息时已经稳定低速停在半径内，本批不改变该控制语义。

结果新增 `action_status`、`child_results`、`mission_events`、`search_feedback`、
`streams`、注入点及终态观测。未决保锁/迟到终态/拒绝取消另由任务与搜索
组件mock后端测试验证，不能称为真实飞行未知结果全矩阵。实际进度、原FAIL
及验收结论见 `schedule-v4.md` 第21节；外部接管仅覆盖此次仿真AUTO.LAND，
不等同于真实遥控器、AUTO.RTL/POSCTL及任何其它外部模式都已签收。

最终六类独立准备场景均PASS，目录后缀为 `-prepared`；证据位于
`artifacts/mission-lifecycle-sitl-20261007.YznI0t/`。每轮24进程正常退出、
transport排空及无所属残留，汇总复核见 `prepared-evidence-audit.json`，最终
源/安装入口及生产二进制指纹见 `prepared-runtime-binaries.sha256`。准备修改
前的manifest和原FAIL仍保留，不能混用入口指纹；该汇总不替代原始结果。
46项纯谓词/准备阻断回归和9项profile回归均通过；具体终态、覆盖与适用
边界见交接第21.9–21.10节，不把本批有界通过扩大为所有故障已经解决。

## 初始短轨迹专项（2026-10-09）

原`mission-search-timeout-signed`的FIRST_TRAJ_COLLISION标记实际上来自十次
细化成功后被严格速度检查拒绝，不足以证明几何碰撞。managed模式现对
细化结果重新做动力学检查，最多五次全时间域重参数化/重新细化；保留
原边界导数输入、固定终点及每次完整碰撞检查，发布前限速防线不取消。
通用首次规划失败标记改为FIRST_TRAJ_FAILED，具体拒绝原因继续单独记录。
legacy非managed模式不切换到新时间重分配策略。

新增显式`--lifecycle-preparation direct`仅用于六类任务生命周期场景，
使用原四步takeoff(1.5m/0.3m/s)→hover2s→navigate/search→Land，不等待
独立稳定准备。默认仍是用户批准的isolated协议，二者不能混用验收证据。
例如在新的空输出目录、无其它仿真时，显式选择：

```bash
ros2 run easyfly_sim_launcher navigation_sitl \
  --px4-dir /home/jia/PX4-Autopilot-1.16.2 \
  --output-dir /绝对路径/新的空目录 --domain 217 --gazebo-port 11432 \
  --strategy combined --scenario mission-search-timeout \
  --lifecycle-preparation direct
```

原search步预算仍12s；若预期超时前发生规划失败，整轮仍FAIL。超时后只在
所属任务及子动作真实排空、仍可信OFFBOARD并稳定时，执行原声明的独立
恢复验证任务；非预期失败不追加降落/返航。专项组件反例与实际SITL结果、
指纹、剩余边界见schedule-v4 §23；此前原FAIL不被覆盖。
