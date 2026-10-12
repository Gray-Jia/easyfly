# D5：云台与精准降落

范围：固定下视相机＋静止 AprilTag 36h11 板；独立模拟云台。没有实机、移动板、
动态云台相机外参或 G9–G11 验收。用户确认的安全策略与实际验证见
[schedule-v4 第11节](../../schedule-v4.md)。

## 接口与所有权

| 接口 | 语义 |
|---|---|
| `/gimbal/set_angle` | FLU角度，单位度；成功仅表示接受，真实运动看 `/gimbal/state` |
| `/gimbal/set_tracking` | 显式目标ID，odom目标结合新鲜UAV姿态转FLU；只控制云台 |
| `/gimbal/simulate_connection` | 仅模拟故障注入；恢复不复活旧命令 |
| `/landing/guidance_target` | 原图像源时间、odom板中心/法向、标签ID与尺寸；仅观测，不是命令 |
| `/flight_status` | 原MAVROS State源时间、模式/armed、首次接收年龄与有效性；独立观测，不是命令 |
| `/precision_land` | PrecisionLand Action，tag_id＋steady总期限；真实阶段反馈/取消/终态 |
| `/precision_landing/ownership` | 精确UUID，只有RELEASED代表动作槽排空，未知保持锁 |
| `/trigger_landing` | 兼容启动入口，accepted不等于降落成功；不支持有限XY或自定速度 |

飞控持有整个精准降落动作槽，拒绝重叠普通起降/航点/轨迹；不会用几个航点的间隙
交出控制权。专用包的策略不发布setpoint；唯一 `/uav_command` 出口仍为飞控。
稳定对准且实际高度进入显式收尾区间后，父动作提交带自己会话ID的真实普通Land子Goal。
准入、接收及副作用前再次检查目标/状态/身份/取消。该内部会话字段是可信ROS图内
协议，不是安全认证；不要让外部客户端伪造。

取消只取消所属子Goal并等真实排空；拒绝取消、迟到准入、丢失结果不会假装释放。
handoff后沿用普通Land取消：仅确认仍拥有新鲜AUTO.LAND时恢复OFFBOARD悬停；
外部接管不抢回。已发送模式请求结果不明时停流、保留全局故障锁；动作ownership
RELEASED不代表远端MAVROS命令结果已知。人工核查后重启，不自动重试/盲降/返航/上锁。

## 几何、时间与配置

LandingTarget沿链保留标签边长；检测、转换与飞控期望值必须一致。板中心使用完整
`T_odom_base * T_base_optical * p_tag`，包含相机杆臂与飞机roll/pitch/yaw。
光学Z不是离地高度；实际飞机相对板中心的odom Z差才用于下降/收尾。板法向由
标签局部Z转换；允许法向符号相反，但要求单位法向和绝对倾角符合边界。首版不对齐飞机yaw。

源图像与UAV状态按有限时间间隔配对；原源header/frame保持，不给旧观测重新打时间戳。
若对应状态尚未到达，按用户确认的优化保留最多32帧有界待配对历史，每帧保留首次
接收时刻；选择原有效期内且满足原状态配对窗口的最新可配帧，不外推车辆姿态。
状态迟到后仍须满足原源年龄、原接收TTL及配对间隔；过期或失效立即清除，不能复活。
等待期间不产生有效新目标；已有有效目标也只存活至原TTL，不续期。
源时间必须为正；ROS源年龄与steady接收TTL都检查。飞控允许最多
`min(0.2, target_max_age)` 秒小幅future，不允许回放/重复源时间推进稳定计数。
冻结/回退/过期时间、无效状态和标签缺失传播invalid，不能用缓存继续下降。

用户确认重复传输例外：仅对原始图像时间戳、frame、尺寸、编码、步长与像素数据
完全一致，且原接收TTL/源年龄/时钟/标定仍有效的重复输入静默忽略。不发布新观测、
不刷新原接收时刻、不推进稳定帧；同源异内容、倒序、过期或已失效上下文仍失效。
诊断哈希不是生产准入的等值判据，生产使用完整字段与数据比较。

无配置默认不可用。尺寸/ID/光学frame、单位相机四元数与FLU平移、静态plane Z、
横向/下降速度、对准容差、收尾高度、最大高度/半径必须显式有效；readonly启动配置，
D2参数服务不开放任意写入。显式 `d5_simulation.yaml` 只是仿真例子，launch检查
跨节点一致性，各节点检查数值范围；启动不发Goal，也不默认启动第二个飞控。
旧landing_dev仍是准备配置，不自动开启下降。

用户追加确认显式收尾高度区间：`precision_handoff_height` 是实测交接门槛，
`precision_descent_floor_height` 是下降指令目标下限，必须有限且
`0.15 ≤ floor < handoff ≤ 1.0`，缺失任一边界拒绝启用。捆绑仿真例子为0.6/0.5m。
该相机/板配置的floor视野检查包含白边、对准容差、标签倾角及边缘余量；旧0.3/0.2m
存在画面裁切反例，不再作为当前例子。该检查不保证任意机体姿态或实际高度误差。
避免把交接门槛同时当目标下限而依赖闭环误差穿越门槛。
floor不保证实际飞机不下穿，捕获实测悬停与普通Land收尾也不是同一目标下限约束。
新增参数需同步配置旧显式D5消费者；普通未启用飞控不受影响。

获取→对准→连续新观测稳定→有条件下降→真实普通Land收尾。标签丢失立即停止下降，
仍可信且拥有OFFBOARD时锁定首次失标的实测悬停点。重获必须连续五个独立有效观测，
重复源时间不计数，失效打断连续计数；确认前不横移、不下降，也不重设悬停点或续期。
丢失期限从首次失标计时，连续不稳定到期失败；确认后另需重新对准的独立观测。
飞机状态
失效/接管则停流，恢复反馈不复活旧动作。静止板位置与首次锚点比较，防止小步漂移累积。

## 使用与迁移

Python SDK新增 `precision_land(tag_id, timeout)`；C++为
`precision_land(const PrecisionLand::Goal&)`。正式schema_version=1任务
新增 `precision_land`＋显式tag_id，严格顺序/失败即终止。示例为
`easyfly_mission_fsm/missions/precision_landing_demo.yaml`；不会成功后再额外追加Land。
legacy任务语法不扩展。TriggerLanding有限XY/非默认速度拒绝，不静默忽略请求字段。

新增PrecisionLand、LandingGuidanceTarget、SetGimbalTracking，以及Land Goal内部会话
字段和LandingTarget尺寸元数据，需要同步重新编译easyfly_msgs及所有受影响客户端/服务端；
普通Land字段默认空、原 `/navigate` 公共字段不变。

## 验证分层

2026-10-08电池专项后，D5仿真入口统一选择并验证项目局部PX4 HRT兼容版，
缺少构建或指纹不匹配拒绝启动，不回退原安装；原私有rootfs保持隔离。
见[电池专项构建说明](battery-sitl.md)。本次仅回归配置/隔离构建测试，
不将此前使用原PX4的完整精降飞行结果追认成兼容版的全矩阵验收。

2026-10-09当前版本的生命周期矩阵入口新增显式`--scenario`：
`loss-recover`、`loss-persistent`、`cancel-descent`、`cancel-handoff`、
`external-takeover`，全部必须同时给`--direct-action`；默认`nominal`
不注入，默认启动仍不发送Goal。正常正式任务继续用`--mission`。

新增其它模式的显式场景：`external-posctl-descent`、
`external-posctl-handoff`、`external-rtl-descent`、`external-rtl-handoff`。
分别在真实descend/OFFBOARD或land_handoff/AUTO.LAND且唯一内部Land
Executing时请求POSCTL/AUTO.RTL；同样必须指定`--direct-action`。
实现及各场景实际PASS/FAIL以schedule-v4第33节为准，入口存在不代表
已验收全部场景。不会改变生产飞控模式切换、安全阈值或追加恢复动作。

每项使用新空目录、独立rootfs和既有DDS profile，串行执行，不与组件
压力回归并行。失标夹具通过独立测试话题转发未改动的真实相机消息，再
停止/恢复转发；检测/转换/飞控继续真实运行，不伪造目标，不改stamp、
TTL或安全阈值。这验证观测断流，不是光照/真实遮挡鲁棒性。

飞行入口在发现Action服务后、唯一Goal提交前查询飞控自己的
`/platform/flight_control/capabilities`，保留内部就绪快照及查询时延；
外部状态、固定等待和服务发现不再作为飞控内部首帧/clock的证明。
响应与原始状态必须新鲜，查询超时则不提交Goal；不重发被拒绝或
结果不明的飞行Goal。查询不占用控制权，实际Takeoff准入仍重新校验。

2026-10-11第34节接续：真实ROS反例验证缺state／clock仍拒绝、查询
无指令副作用、旧源新receipt不续期；新就绪流程已跨过真实起飞
准备阻断。AUTO.RTL下降与普通Land收尾两阶段真实SITL及独立审计
通过，精确父释放／子真ABORTED结果／新鲜独立模式／上下游停流／
进程清理均核对。这是接管负向验收，不是返航降落成功或实机验收。
POSCTL因仿真没有有效manual输入被PX4临时拒绝，按用户决定暂缓，
不注入手动流、不改参数或关闭保护；原FAIL保留。间歇失标仍未关闭。

新增显式 `unknown-mode-late` 与 `unknown-mode-withheld` 仿真场景，
必须指定 `--direct-action`。仅该入口单独启动并重映射所属飞控的
arm/mode客户端到 `/d5_test` 代理；代理原样转发真实桥接命令，
不伪造状态或响应，只扣留唯一内部Land的模式服务回复。前者在
真实超时终态、故障锁和停流检查后返回原回复，后者在验收期间
持续扣留；不改变生产5s等待期限或实际PX4保护。先确认真实
AUTO.LAND模式和父子ABORTED/false/精确释放，再独立查询故障锁；
真实新鲜disarmed后测试后续动作拒绝。各项实际结果见第35节，
入口可用不代表所有未知命令/取消/桥接故障场景均已签收。
未知命令的普通Land与父精降结果使用 `command_result_unknown:`
前缀；即使PX4实际已执行降落，也不能将本地未知结果报告为成功、
明确未进入降落或仍在悬停。明确失败与未知结果仍分别处理。
扣留场景只在所属飞控已退出后释放回复以排空测试回调，清理释放
单独标记；报告在observer回调有界排空、实体/context关闭后保存，
审计同时核对observer和飞行子进程的PID/start_ticks，不只看report旗标。

2026-10-11第35节最终 `verified/` 两个场景已真实SITL及独立审计
通过：父/子真实ABORTED/false，精确父释放但独立flight fault锁
持续保留，迟到回复前后/持续扣留时后续4类动作均拒绝，实际上下游
停流，无重试或补偿命令。入口及所有所属进程正常清理；之前扣留
夹具observer收尾卡住的记录保留且撤销过早PASS，修正版重新验收。
这只覆盖飞控→桥接服务回复的Land模式事务，不代表arming、桥接
自身故障锁或取消交叉等未知结果全矩阵已完成，也不是实机验收。

取消只取消当前精确handle；收尾取消还要唯一内部Land真CANCELED、父
ownership同UUID RELEASED及新鲜OFFBOARD。原外部接管场景在仿真实际
下降后经MAVROS请求AUTO.LAND；其它模式场景还覆盖普通Land收尾。
`SetMode.mode_sent`只是MAVROS已发送SET_MODE，不是FCU COMMAND_ACK。
必须独立原始FlightStatus与UAVState均新鲜且匹配请求模式，原始模式
源比注入前推进，精降真ABORTED、精确父释放及上下游停流；收尾还要
唯一内部Land精确UUID的GetResult返回ABORTED/false及接管原因。
不是生产指令旁路或RC/未知命令结果全矩阵。
负向场景预期CANCELED/ABORTED不能写成降落成功，不自动追加Land/返航。
持续失标的保持命令按真实lost_hold至最后保持反馈核对，动作失败后
重新捕获安全悬停点另属终态处理，不把ownership查询等待并入失标窗口。

```bash
# 先创建新的空证据目录；此命令明确发起仿真飞行动作。
ros2 run easyfly_sim_launcher d5_simulation \
  --directory /绝对路径/新的空证据目录 \
  --px4-dir /home/jia/PX4-Autopilot-1.16.2 \
  --use-bundled-dds-profile --direct-action --scenario cancel-handoff
```

具体PASS/FAIL、入口运行版差异及未覆盖边界以schedule-v4第25节为准，
不以之后通过删除并发组件回归期间的原输入时序FAIL。源码、飞控/PX4
指纹及所属PID/start_ticks记录保留；新`passed`字段还要求子进程/残留
检查，不能只看预期动作终态。历史semantic退出专项继续暂缓，不自动取栈。

`--observer-rmw-diagnostics`仅记录observer原生接收/take与原始几何证据，
不启用transform/flight的诊断日志，与`--transform-diagnostics`独立且
默认关闭。camera/CameraInfo/tag及landing/guidance/state的wall时间只用于
同机阶段归因，不参与飞行准入。开启后会改变观察者时序，不能以通过
证明普通失败已修复；缺失/无效native字段保持未知。

纯几何/策略、真实ROS进程、SDK/任务及mock MAVROS父子生命周期回归不能冒充完整
图像飞行验收。真实图像SITL必须同时看到有效ID7标签、有效odom观测、对准/下降/
handoff反馈、真实PrecisionLand成功与新鲜disarmed反馈。launch父进程0还须核对
子节点异常日志、GDB、强制终止、残留与端口。单次仿真不认证实机精度或历史偶发退出故障。

仿真夹具使用独立world和另生成的Iris下视相机，不覆写生产机型。标签为代码原生64格
36h11 ID7，显式尺寸0.2m；相机安装/外参同步。使用现有PX4二进制，只读复用插件和
启动脚本，必须显式 `px4 -w` 隔离rootfs，单改PX4_DIR不够。测试原始证据在本地
artifacts归档，验收结果与失败过程登记在schedule-v4，不做系统升级。

SMOKE支持 `--fixture-scale 2 --handoff-height 0.6 --descent-floor-height 0.5`，只放大
生成的标签world和一致配置（0.4m黑边），同步倾斜板高于地面及预期odom平面；
交接与floor必须同时显式给出。源world/生产机型保持不变。理想光照禁用阴影，
不作为光照/遮挡/小标签鲁棒性证明；默认0.2m板配置不能由另一尺寸场景自动签收。

诊断选项 `--unused-camera-rate 1` 仅将生成副本中未参与D5的前视彩色/深度相机
降至1Hz；默认仍为30Hz，下视相机仍30Hz。保留全部物理结构、惯量、杆臂与激光雷达。
它不修改生产机型或时间/安全门槛；该配置的通过不代表全传感器负载通过。
SMOKE结果保留至多10000条观测时序（原source、ROS clock、steady elapsed），
用于区分源过期、实际检测缺失与异步配对，记录不驱动飞机。

正式任务验证使用 `--mission`：启动实际mission_fsm，正式YAML经SDK执行起飞、
15秒hover、精准降落。计时hover不是稳定证据；测试另检查实测稳定状态。验收要求
真实成功、3步complete、同一精降UUID的下降/交接、精确任务UUID RELEASED和新鲜disarmed。

同机仿真需显式 `--dds-profile` 指向 `config/d5_fastdds.xml`：FastDDS SHM 64MiB，
最大消息4MiB，保留UDPv4。测试启动前冻结profile并记录hash，整棵隔离进程树使用
同一副本，不修改系统环境、QoS或源时间。此选项不是生产/跨机配置默认。
转换时序诊断 `--transform-diagnostics` 默认关闭，只记录，不改变时间/准入门槛。

当前签收：SITL23使用0.2m板/.6/.5m区间、三台相机原30Hz、显式DDS，正式任务
完整链成功，3步完成、精确排空、新鲜disarmed及全部进程正常退出。精降至交接的
222条观测全部有效；收尾及启动阶段仍有无效观测，不宣称全时段零失效。
最终相对初始观测水平误差约.159m仅观测参考，非ground-truth精度。
SITL14降负载通过、15/17传输失败、21时序滞后和22裁切失败等原始证据继续保留；
21唯一根因未闭环。全算法负载/光照遮挡鲁棒性/长期稳定性及实机均未验收。
详情与失败过程见schedule-v4第11节；真实设备暂缓，不自动进入D6。

## 后续优化：统一入口与时序诊断（2026-10-06）

安装入口为 `ros2 run easyfly_sim_launcher d5_simulation`，实际参数示例见
[包README](../../src/execution/e3_control/easyfly_precision_landing/README.md)。
默认仅启动，不发飞行Goal；`--mission` 或 `--direct-action` 才显式运动。
必须给现存空证据目录、真实编译PX4源目录或带manifest的隔离staging，以及
`--use-bundled-dds-profile` 或明确profile路径。`--prepare-only` 只准备输入，
不启动Gazebo/PX4/ROS节点；源脚本和安装入口共享同一Python引擎，不再有两套参数逻辑。
旧手工wrapper没有manifest，需重新准备，不能靠目录内有名为px4的文件绕过隔离检查。

生成独立rootfs，实际wrapper显式-w/-s；源PX4参数不复制、不改写，共享启动脚本与
插件仅作输入约定，不宣称OS只读挂载。跨节点配置先验证；DDS按语义/预算校验并冻结。
拥有新仿真进程的独占预留marker、新clock之后才启动桥接/飞控，发现旧图则拒绝。
防重失败实际只启动失败的simulation组，未启动第二套桥接/飞控；锁不是认证或跨UID保护。
D5_READY只表示本轮地面启动状态可信，不代表全部感知或飞行准入已满足。

SIGINT正常停启动模式；SIGTERM始终报告中止，二者均走有界清理及子进程退出检查。
运动阶段尝试精确取消所属Goal并等待真实终态/ownership；不能因进程退出假定远端已停。
实际S31悬停步骤SIGTERM确认所属任务CANCELED/status5、同UUID RELEASED，未追加Land。
这不是handoff中断、准入未知或永久无回应的完整实飞覆盖；原组件取消反例仍保留。
服务管理器应启动安装后的原生入口，或向其进程组发信号，不依赖ros2 run包装PID转发。

时序诊断默认关闭，使用本机Humble原生一次take的RMW信息；只区分软件发布→接收→
取出、回调耗时及车辆配对等待。ROS源年龄/steady TTL/配对窗口/失标门槛不变。
系统wall时间不进入任何飞行判断，异常时间差为未知，不作为硬件采集时间。
S24/S30正式任务成功且未重现S21；新增证据缩小本轮范围，但S21根因尚未闭环。
不为了消除报错而改QoS、扩大有效期或重打源时间戳。后续定向复现应保留此诊断和旧证据。

新增逐帧诊断（2026-10-07）：上述选项同时在生成配置中启用飞控只读
`precision_timing_diagnostics`（生产默认false）。转换端记录原源stamp、generation、
首次receipt、native take/回调入口、pending/selected配对、状态源及receipt、无效原因、
实际publish起止和succeeded；飞控端记录原guidance源、RMW接收信息、回调入口、
flight mutex等待、准入结果、session active/UUID。飞控入口不冒充native take，
飞控generation为当前代、callback_generation为回调所属reader捕获代，保留退休边界。
ready_at_exit不冒充控制循环实际使用。采集端保留receipt steady时间。

两端事件环均硬上限256，累计dropped_events可见；Python采用1.05秒刷新周期，
仍保留至少1秒间隔检查，退出时强制排空尾段，避免整秒定时器轻微提前导致跳过一轮。
飞控退出前未刷新尾段可缺失。缺失/不支持/时间回退/有歧义的段落保持未知，不能填0；
同源时间可能在clock回退后重用，关联还需generation、first receipt及事件顺序。
跨进程steady差值仅在确认同机同时间原点时使用；接收可先于publish返回，
采集端减publish_end可能为负，不表示负网络延迟。全部为诊断，不进入飞行准入。

本轮组件22项观测CTest/9项飞控CTest通过，新增7组非飞行时序实验通过；但唯一
带逐帧诊断的正式任务frame-mission.Drz8q5失败于landing_target_lost，未重试。
精降窗口tag array184帧均detected，其中15个选定pose无效；指导132valid、37几何
拒绝。132valid全部有完整转换及同一active动作的飞控接收链，源年龄-.088至.016秒、
publish最大.118毫秒、飞控回调延迟小；这些有效帧没有复现旧有效流迟到现象。
整轮转换事件drop1416/飞控0，不能声称无效帧与全轮trace完整。下一步需离线检查
具体pose/平面拒绝原因，不放宽门槛；本次不签收模拟鲁棒性、不追认S21。完整失败、
精确释放和正常清理结果见schedule-v4第16.1节及artifacts/d5-frame-timing-20261006/。

## 本地观测队列超限恢复（2026-10-06）

用户确认采用自动重建观测订阅，不采用需人工重启的观测故障锁。真实ROS定向测试
复现了慢仿真时钟下callback receipt不含DDS取出前等待的缺口：阻塞.45秒，
ROS源年龄约.045秒，旧目标原先仍可输出valid。修复不把RMW系统wall时间用于准入。

state、target、watchdog入口均检查本地steady处理连续性；超过原source-age预算
（默认.3秒）或steady时间倒退时，拒绝触发样本，清车辆历史、pending、last_good与
receipt，保留已处理源stamp水位，发布invalid并重建两个显式VOLATILE reader。
原depth10/1和可靠性不变，generation封装使已调度旧回调不能污染新证据；不用可能
排队的ROS now建立虚假的采集屏障。查询不会续处理期限，新reader重新配对才恢复。

控制层原失标停下降、首次失标位置保持、5帧重获和持续失标失败策略不变。
持续处理超限可能导致保守失标/失败，不能用扩大TTL消除。该保护只覆盖本地处理
中断后的队列隔离，不证明上游采集时钟或任意传输延迟安全，也未证明S21唯一根因。
本轮只运行合成观测/真实ROS节点及组件回归，不启动PX4/Gazebo；组件Action用例
使用合成反馈，不执行SITL或实机飞行。
验收及修复前后证据见schedule-v4第13节，真实设备、UI及G9–G11继续暂缓。

## 下游guidance接收与失标恢复链（2026-10-06）

真实飞控＋DDS定向反例确认下游同类边界：接收callback group阻塞.45秒、ROS时钟
只推进.045秒时，原guidance callback给旧目标重新设置steady receipt并判ready。
按已确认自动恢复策略，飞控同接收组增加50ms处理进度watchdog，guidance callback
及watchdog均在取得flight mutex后检查steady间隔。超原target_max_age（默认.3秒）
先清valid/receipt，再重建原可靠depth1、显式VOLATILE guidance reader；退休generation
不影响新证据，保留source水位、Policy及首次失标期限。仅控制timer继续运行不能
掩盖reader组阻塞。重建异常清证据后传播、停止节点，不把它当正常重获。

真实transform＋飞控＋显式合成反馈链已验证失标停止下降、首次悬停点不漂移；
1–4个新独立帧保持reacquire_hold，第5个确认重获转align但仍不下降，之后重新
满足独立对准帧数才恢复下降。持续失标得到真实ABORTED与匹配Goal UUID的RELEASED。
没有盲降或追加Land/上锁。合成反馈不是飞机动力学或实机验证。
同组进度保护不覆盖“组持续运行、某个topic单独饥饿”的任意延迟，也不证明上游
采集或整个遥测链时间可信；S21唯一根因仍未闭环。组件及短时联调结果见schedule-v4
第14节；不恢复UI、实机或G9长稳循环。

本批新增保护后的一次同配置短时SITL正式任务失败于
`landing_target_reacquisition_timeout`，未进入下降/普通Land收尾。失败窗口原始标签
有效但guidance有效与过期交替；两端没有reader重建warning，不能直接归因于新增保护。
所属任务精确释放且所有本轮进程正常退出，但这不是集成通过。下一项需定位源时间/
车辆配对与过期交替，不扩大TTL或重获期限；原历史SITL23/30成功记录不替代本轮结果。

## 有界安全配对优化（2026-10-06）

用户已确认将最新单槽改为最多32帧短历史，原source/首次steady TTL（默认.3秒）和
state_pair_gap（默认.1秒）不变。输入水位防重、独立输出水位防倒序；每次选择最新
安全配对，发布后删掉所有更旧候选，保留更新待配帧。单条过期只剔除该条；非法新
观测/状态、世界几何失败、clock失效或reader重建清历史，不通过旧帧回退绕过失效。
图像尺寸/质量/光学姿态在入历史前检查；不修改飞控5帧重获后再次对准的规则。
原latest_only测试迁移为经用户批准的新语义，保留原stamp、TTL和源单调保护。
受控迟到流修复前0/90有效输出，修复后59/90，普通/诊断executor一致；这确认局部
持续覆盖问题修复，不证明旧SITL过期交替或S21的唯一根因。组件与联调结果见
schedule-v4第15节后续记录，不用一次诊断开启的成功覆盖历史失败。

改后新增14项history边界/6项实际持续流回归通过，观测20项与飞控9项CTest通过。
诊断默认关闭、原三相机30Hz/0.2m板/.6/.5m的一次正式任务SITL成功完成3步及
align→descend→Land收尾，同UUID RELEASED和新鲜disarmed，所有所属进程正常退出。
本轮控制窗口228个guidance均有效；这只是本轮短时仿真签收，不证明旧失败唯一
根因、S21、上游采集、长期鲁棒性或实机全部闭环。完整证据见schedule-v4 §15.1。

## 仿真高度基准修复与当前签收（2026-10-07）

第16节FAIL的离线取证发现高度拒绝；统一仿真入口原先假定world→odom z=-.10m，
但模型碰撞几何给base_link接地高度.055m，独立Gazebo真值实际约.054m，且PX4 odom
起始高度会变。现在从完整已解析collision/include资产推算upright接地位置，并在
disarmed/静止/新鲜状态下与独立world实体配对十个严格推进样本，至少1.8steady秒、
offset span≤.03m、world ground span≤.005m，冻结median(odom_z-world_z)。标签平面
采用倾斜cell顶部中心而非model原点；随后同步生成transform/flight参数并验证，才
启动精降节点。原质量/几何/TTL/失标边界不改，不使用tag结果拟合平面，不在飞行
过程中追随或重校准。未知或失效状态/查询、时钟回退、非静置模型拒绝启动。

该校准只属于隔离统一仿真入口；单独launch和真实设备仍必须显式提供实际odom平面、
外参和安全边界，不把仿真真值引入设备飞行。碰撞工具限定已知primitive/显式URI，
未知include、mesh、frame、scale/非零included-model pose拒绝；不宣称通用SDF解析。
`--prepare-only`的地面零odom配置仍是名义准备产物，不代表运行时reference通过。

当前组件观测26项CTest通过（cppcheck2.7工具skip3项），飞控第一轮queue测试timeout
已定位为测试夹具cancel先于worker实际spin的竞态；新增is_spinning同步及120ms延迟
启动case后全9项通过，生产飞控逻辑不变。两轮正式任务均完成三步/精确RELEASED/
新鲜disarmed/四组exit0及子失败空：诊断开启OXqqor控制guidance229valid+1倾角拒绝+
1过期，无持续失标；默认关闭YT7636控制tag/raw/guidance各240帧全valid，无lost。
不以再运行覆盖原FAIL或降低三相机30Hz/.2m板负载，也不把本轮签收追认成S21唯一
原因、全负载长期鲁棒性或实机验收。完整原始证据与结果见schedule-v4第17节。

## 标签观测入口修复（2026-10-11）

实际DDS缓存取证确认：可靠标签订阅会因未解决的前序序列，将已缓存
的新观测标为future、暂不可读；真实负载曾等待339ms。初始序列缺口
的唯一来源仍未知，详见schedule-v4第27节，旧失败证据不删除。
经独立候选及用户批准，仅LandingNode的`/tag_observations`订阅改为
best-effort、VOLATILE、KEEP_LAST depth1；发布者不变，输出及控制
动作/服务仍可靠。不请求补齐缺失旧帧，允许丢帧；不是扩大缓存、
TTL、状态配对容差、失标期限或重写source。丢帧/无新有效目标仍
按原保护停止下降，重获仍需5帧。此有意变更取代先前“QoS不变”的
阶段性记录，不改变其他链路的可靠性。
正式landing 12/12检查、precision 21/21行为CTest通过；普通安装、
全部诊断关闭的完整任务/短时重获/持续失标/下降取消/收尾取消
五项通过。原外部接管脚本通过，但下游无正向基线，补强工具后的
接管验证发现AUTO.LAND与内部Land收尾竞争、真实FAIL；后续修复见下节。
具体UUID、真实终态、参数与清理证据见
schedule-v4第28节。该已确认的tag reader等待旧帧路径已消除，
不追认历史失败唯一原因、不声称其他输入延迟或实机风险全部消失。

外部接管的下游停流验收必须先有正向观察基线：仿真工具监听桥的
position/velocity/attitude/raw四种真实出口，在接管前一秒内要求
至少两条实际position输出，空记录/过期/未来记录不能通过；记录
各出口计数和真实确认接管后的停流窗口。全轮只监听未使用的raw
话题得到的“无输出”不是证据，历史此类结果保留但不单独签收下游。
这只是验收工具修正，平台/PX4的控制策略和停止期限不变。
补验已取得40条实际position输出，不再是空观察；但接管时飞机
先降低至交接区间，模式新证据到达前内部Land已收尾，父动作真成功
而非预期接管失败。该历史FAIL保留，不能换接管模式或用未改代码的
重跑来追认修复；新版本验收单独记录。

## 独立模式证据与转换入口优化（2026-10-11）

桥接新增FlightStatus，不改原UAVState ABI。保留原MAVROS源header，
需同步构建easyfly_msgs、easyfly_mavlink_bridge及easyfly_flight_control；
缺少独立模式输出不能用聚合header代替，交接等待至原总超时失败。
重复/倒序source不能刷新首次steady receipt。精准降落首次满足
低高度稳定对准时捕获固定悬停点及源时间屏障，发布handoff_wait_mode，
等待严格晚于屏障且原源/接收年龄均可信的独立OFFBOARD证据。
Land准入及实际发送模式请求前仍复核；新外部模式证据可在聚合状态
仍旧OFFBOARD时终止并停流。等待仍受原目标保护、取消及总超时约束。
交给Land之后保留原真实子动作取消与未知结果保锁规则。
这不是PX4模式请求的跨操作者原子事务，也不保证外部接管瞬时可见。

新版本首次原AUTO.LAND场景已真实ABORTED、无内部Land、下游40条
正向基线后停止输出。随后普通任务在尚未到交接阶段时遇另一入口
延迟（上游源年龄52ms、转换输出424ms），完整FAIL保留。独立无飞行
诊断没有复现，不宣称初始序列缺口起因已唯一确定。
用户批准独立候选验证后，仅转换的纯/landing_target订阅也改为
BEST_EFFORT/VOLATILE/depth1；候选普通任务及真实可靠/非可靠发布者
兼容、过期/重放/冻结保护与退出测试通过后合入。
state仍可靠depth10，guidance发布仍可靠depth1；重建保持各自QoS，
没有改变控制发布、TTL、配对或失标安全参数。当前正式六项矩阵
（普通任务、重获、持续失标、两项取消、原AUTO.LAND接管）全部通过，
精确UUID释放、新鲜终态、实际下游基线/停流及进程清理均复核。
普通任务仍出现短时失标并按保护恢复，不宣称全时段零失标或长期
稳定性。原失败、指纹、验收范围与尚未清完的C++格式/lint检查见
schedule-v4第29节；实机、初始序列缺口唯一来源及旧偶发崩溃不签收。

2026-10-11后续C++收尾：桥接与飞控两包全部14个C++文件通过
cpplint/uncrustify/cppcheck，GoogleTest宏使用系统库配置解析，
不排除测试文件；检查已纳入各包CTest，cppcheck实际执行、无skip。
新二进制相关39项CTest及普通任务/原AUTO.LAND接管两项SITL通过，
无控制逻辑或安全参数变更。原六项矩阵仍关联原二进制，不追认
全六项已用本版重跑。短时失标仍出现，性能优化未开始；详见
schedule-v4第31节。这不代表全仓lint或长期鲁棒性完成。

## 原生输入时序诊断（默认关闭）

仿真观察器的普通记录现在也保留所选标签的独立valid/reason、
最多两个所选标签的位姿、LandingTarget位姿和CameraInfo标定；
`observation_geometry_details=true`标识该记录版本。数组的detected
不代表所选标签位姿可信。仍复用原订阅及10000条记录上限，
不自动开启以下原生诊断、不改变飞行准入；这些是observer所见，
不能重建控制端实际接收次序或转换选中的状态配对。
第32节两次任务约8.30/8.40s进入交接、均未复现间歇失标，
只证明本轮通过及记录生效，不证明历史问题消失或性能修复。

隔离仿真入口可显式指定 `--ingress-timing-diagnostics`，仅为原
landing_detection订阅/发布链保留最后8192条事件，退出后写入本次
证据目录 `landing-ingress.tsv`。不在回调内写盘，不新增订阅或改变QoS；
文件已存在则拒绝覆盖，元数据说明截断数。正常析构才保证落盘。
该开关独立于 `--transform-diagnostics` 和 `--observer-rmw-diagnostics`，
不隐含飞行授权；观测DDS出口仍需显式启用observer开关。wall时间只与
wall比较，ROS源年龄只与同域ROS时间比较；native字段为0或时钟跳变时
不能给出传输时延结论。MissionFSM准入拒绝日志使用实际决策快照，
不把外部observer就绪或固定等待当内部SDK就绪证明。

观察节点收到 SIGINT/SIGTERM 时仅请求退出当前单线程executor，回调
返回后再停止executor、销毁节点、关闭context；两种诊断配置的次序
一致。不会捕获或忽略正常执行的RuntimeError。真实native typed take
紧邻两种信号的测试验证转换期间context有效；这只验证退出顺序，
不代表已解决间歇观测延迟、所有历史退出故障或完整D5长期鲁棒性。

## 模式回复未知的两层故障锁（2026-10-12）

隔离仿真入口新增显式 `--direct-action --scenario bridge-mode-late`
与 `bridge-mode-withheld`。只重映射所属bridge的MAVROS客户端，
flight→bridge公共服务及真实MAVROS服务名保持不变。唯一内部Land
的实际AUTO.LAND请求单次原样转发，真实mode_sent回复被迟到释放
或运行期持续扣留；mode_sent不是FCU COMMAND_ACK。原5s等待期限、
所有飞行安全参数和正常launch默认均不变，不默认注入故障。

桥接新增只读 `/platform/mavlink_bridge/capabilities`，独立报告
command_fault及context/clock/mode与arming服务发现状态。它只描述
命令传输，不代表飞行准入、FCU接受或控制权预留；查询不能清锁。
真实SITL两项都确认独立新鲜AUTO.LAND、父子真实ABORTED/false、精确
释放、flight与bridge两层故障锁、新鲜disarmed后动作和合法桥接服务
请求被拒绝，迟到回复及持续扣留都不恢复；正向20/40条平台/下游
基线后的停流已复核。所属五组进程、observer及扣留回调均正常清理，
独立原生PX4日志/UUID/指纹/进程身份审计通过，详见schedule-v4 §36。

这是Land模式回复未知的故障验收，不是降落任务成功或实机签收。
故障后新鲜命令输入的encoder拒绝只有合成ROS组件证据；真实arming
回复未知及取消交叉尚未纳入飞行矩阵。人工核查远端并重启的策略
保持不变，不新增重试、模式补偿、自动上锁或自动清锁。

## 解锁回复未知的显式仿真入口（2026-10-12）

`--direct-action --scenario bridge-arm-late` / `bridge-arm-withheld`
限定真实Takeoff准备阶段，先观察唯一Executing Goal、新鲜独立未解锁
OFFBOARD及平台/下游实际输出基线，才放行单次MAVROS CommandBool(true)。
只扣留实际解锁ACK的回复，success/result原样保留，不制造飞控状态。
真实UAVState/FlightStatus各自源时间推进且均armed，才确认远端执行。
起飞应因未知结果真实ABORTED/false，两层fault独立查询，不开始爬升。

后续探针先等待PX4原配置的保护自行disarm，不发平台补偿上锁；
模式/arming事务应仍各一次，迟到回复不清锁，持续扣留仅在所属
flight/bridge退出后释放清理门。真实精确Takeoff GetResult、查询、
停流和进程身份/原生日志验收记录见schedule-v4 §37。正常任务入口、
5s等待、安全阈值及PX4参数不变。这不是实机或取消交叉的验收入口。

本轮两项真实SITL/独立原生PX4与生命周期审计通过，Takeoff真实
ABORTED/false并保持两层锁，两批动作/直接服务请求被拒绝；先有
20/40条平台/下游正向基线再停流，实际ACK后仍不爬升、不重试、
不补偿上锁。全部所属进程/observer/callback正常退出。初次审计的
每5条采样与精确disarmed帧不匹配FAIL保留，修正审计后复核同一份
raw证据，没有重跑或放宽控制阈值。仅上游arming回复扣留、取消交叉
及真实设备仍未验证；故障后的人工核查/重启策略不变。

## 起飞取消交叉与上游回复丢失（2026-10-12）

显式direct-action场景新增 `cancel-bridge-arm-late` /
`cancel-bridge-arm-withheld`、`cancel-bridge-mode-late` /
`cancel-bridge-mode-withheld`，均仅Takeoff准备阶段。真实远端armed
或OFFBOARD已由独立源推进确认，但原服务回复被扣留时，只取消所属
Goal。四项真实SITL及独立审计通过：精确cancel ACK后的CANCELING/
GetResult未结束及内部预留同时成立，取消等待期间真实停流，原
请求超时后真实CANCELED/false/unknown并保留两层故障锁。模式两项
不解锁，arm两项不爬升；不追加模式补偿、Land或上锁，迟到不恢复。

`upstream-arm-late` / `upstream-arm-withheld` 只重映射flight客户端
到上游代理，正常bridge启动与MAVROS原服务不变。两项真实SITL/
独立审计通过：flight真实ABORTED/false/unknown及持久fault，bridge
三次独立只读查询始终无fault、transport可用。健康transport不等于
飞行权限；不直接命令健康bridge，flight拒绝后续动作。六项均有
实际输出基线到停流、精确UUID GetResult、原生PX4 ACK及正常清理。

一轮在任何Goal前因Gazebo静止而PX4定位估计速度波动被原静止校准
门拒绝。保留原FAIL、空飞行命令和正常退出证据，同指纹新空目录
只再准备一次才完成模式迟到场景；没有放宽阈值或追认波动修复。
详见schedule-v4 §38。正常生产逻辑、5s等待与安全参数不改。
本批不覆盖普通Land/精降收尾取消交叉、上游未知再叠加取消、实机
或故障后新鲜控制输入注入的SITL验证。
