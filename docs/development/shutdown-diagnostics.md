# D4 退出诊断记录（2026-10-05）

2026-10-09新增独立[semantic_map退出专项](semantic-shutdown.md)，原根因仍
未确认，专用捕获默认关闭；没有恢复本页已搁置的Gazebo/EGO退出工作。

## 判定标准

只有真实节点终止、全部子进程正常退出且未强杀，才算退出通过。
ROS2 launch 自己 exit0 不代表子进程成功。未重现事故不等于修复事故。
所有实验只作用于隔离的仿真/录包输入；没有连接实机、升级或覆盖系统库。

## 三个独立事故，不能混为一谈

| 事故 | 已有证据 | 当前结论 |
|---|---|---|
| EGO 停止 SIGSEGV | `/tmp/easyfly-d4-fix.shb1Vx/console.log:920`，PID79661、exit-11 | 无真实故障栈；独立点云、实录回放和后续完整 SITL 均未重现，未闭环 |
| Gazebo 停止 SIGABRT | `/tmp/easyfly-ego-gdb.IneHOQ/console.log:889` 起，PID85829、boost trying joining itself、exit-6 | 无真实故障栈；不能由另一个旧 core 解释，未闭环 |
| Gazebo 相机加载 SIGSEGV | 07:53:21、PID74082；重复 `/camera/color_camera_plugin` 日志、apport core 与寄存器 | 10-07真实最小场景重现该路径，项目局部相机插件已加空节点加载保护；旧事故的重复加载来源仍未知 |

### 相机加载事故的新增证据

原始报告 `/var/crash/_usr_bin_gzserver-11.10.2.1000.crash` 保持不变。
本轮再次只读解包，文本证据保存于 `/tmp/easyfly-gazebo-registers.Vum5jj/`：
核对结束后只删除了本轮生成的3.6GiB临时CoreDump，可从原报告重新解包。

- `registers.log`：主线程在 `QoS::get_publisher_qos+38`，指令 `mov (%rsi),%r15`；
  `rsi=rbx=0x3a0`，不是有效对象地址。
- `camera-qos-address.log`：已安装相机库先读取 `ros_node_`，然后加 `0x3a0`
  获得 QoS 成员地址。寄存器值与空节点加该偏移一致。
- `camera-node-pointer.log`：在真实 core 的相机调用者栈帧中，保存的 QoS 地址
  确认为 `0x3a0`，`impl_->ros_node_` 原始指针确认为 `0x0`。
- 同 PID 日志 `console-fixture-second.log:864` 明确报告重复的相机节点；同文件
  36–37 行显示该相机此前已经成功加载，约69秒后再次尝试加载。
- [gazebo_ros 3.9.0 Node::Get](https://github.com/ros-simulation/gazebo_ros_pkgs/blob/3.9.0/gazebo_ros/src/node.cpp)
  遇到重复节点返回 nullptr；
  [Camera::Load](https://github.com/ros-simulation/gazebo_ros_pkgs/blob/3.9.0/gazebo_plugins/src/gazebo_ros_camera.cpp)
  随后没有空指针判断便使用该节点的 QoS。

这些证据定位了空指针崩溃路径，不是证明所有 Gazebo 问题都来自重名。
没有在本轮修改系统 camera/node 库；也没有以改节点名掩盖未知重复加载来源。

## 本轮新增复验

1. 传感器独立实验：复制现有场景、RGB/深度相机和 MID-360 传感器到临时静态模型，
   不加载 PX4/MAVLink/电机/飞行控制，domain127、Gazebo端口11357。
   每次确认 `/clock`、RGB、深度、Livox 均收到至少3条消息，再向真实 gzserver
   发送 SIGINT。6次无调试器＋6次GDB，全部exit0，退出约0.264–0.314s，无强杀。
   证据：`/tmp/easyfly-gazebo-isolation.JmdRLF/probe.py`、`results.log`、12份trial日志。
   这是缩小范围的隔离实验，不能排除高负载或其它插件组合的偶发问题。
2. 完整基础 SITL：CPU/headless/best_effort、domain121、Gazebo11355，显式临时PX4
   rootfs；EGO和Gazebo均由父级GDB捕获。Takeoff/Land真SUCCEEDED、最终disarmed；
   8个D4节点、EGO、traj_server、Gazebo及launch均正常退出，无异常子进程或强杀。
   软件配对1919、预测351、非空着色72、类别关联367、tag有效空帧550；ROI第一次
   接受、tracking有效10、随后lost8，不声称持续跟踪、真实标签位姿或精准降落验收。
   证据：`/tmp/easyfly-full-shutdown-check.TbFaKs/observation.log`、`console.log`。

## 可复用的故障捕获配置

仓库新增 `scripts/shutdown_capture.gdb`。它透传正常 SIGINT/SIGTERM，正常退出
保持子进程返回值；遇到崩溃或异常停止时打印当前栈、所有线程栈及寄存器并exit1，
不让调试器自身exit0遮蔽失败。默认不生成可能数GiB的core。

```bash
gdb -q -batch --return-child-result \
  -x scripts/shutdown_capture.gdb --args <真实可执行文件> <原参数>
```

可选core要求显式设置 `EASYFLY_CAPTURE_CORE=1` 和已经存在的
`EASYFLY_CAPTURE_DIR`；仅在inferior仍有threads时生成，文件名包含真实PID。
本轮用 `/bin/true` 验证正常exit0，用独立shell自发SIGABRT验证打印栈且exit1；
这是夹具验收，不计为平台行为验收。

后续优先捕获两个未闭环事故的真实栈，再针对栈中的组件建立最小复现。
部署/测试前确认隔离端口无人占用，不并行启动使用同一master和相机namespace的
实验；只回收自己启动的进程。若需要修补系统依赖，使用可回滚的独立overlay，
不直接改 `/opt/ros` 或升级系统；升级/迁移须另行确认范围。

## 单机 SITL 启动防重（专项修复）

`px4_sitl.launch.py` 和 `perception_sitl.launch.py` 在启动任何子进程前共用
`session_guard`。它只接受本地、显式端口的HTTP `GAZEBO_MASTER_URI`
（默认 `http://localhost:11345`），拒绝连接已有master。先取得当前UID独占的
`/tmp/easyfly-sitl-<uid>/single-vehicle.lock` 内核锁，再预检Gazebo master TCP、
PX4 simulator TCP4560、MAVROS FCU UDP14540，不向现存服务连接或发送数据。
临时目录实际采用 `tempfile.gettempdir()`；目录/文件必须属于当前用户且不可公开访问。

即使改Gazebo端口或ROS domain，当前两个入口也只允许一个车辆会话，因为PX4与
MAVROS端口仍固定。多机支持需要另行设计端口配置，不能通过删除锁文件绕过。
锁保持到launch context销毁（CLI退出时由内核释放），不是收到Shutdown时就释放。
文件残留本身不阻塞；不自动删锁、不杀旧进程。程序化使用者应在所有子进程终止后
销毁旧context及持有它的action，再启动新会话。

Gazebo/PX4在Shutdown前退出（包括exit0）和模型生成命令非零退出会终止后续启动，
launch返回非零；Shutdown后关键进程异常退出同样失败。`gz model` exit0仅证明生成
命令成功，不代替传感器/飞控就绪检查。原延迟启动、CLI参数及正常控制命令保持不变。

锁对同UID协作的EasyFly入口原子防重；非协作或其它UID进程仍可能在端口预检后抢占，
不能宣称杜绝所有启动竞态。它降低重叠启动风险，不证明旧相机重复加载的具体来源，
也不是历史EGO SIGSEGV/Gazebo self-join的修复。验收和最新证据见schedule-v4第10.12节。

## 2026-10-07 有界排查与修复

用户授权先处理历史退出故障。本轮不用复跑成功抹掉旧事故，也未恢复G9长循环。
旧`/tmp`退出实验目录当前已不存在；相机apport报告仍保留，未删除/重写。
新证据集中在`artifacts/shutdown-20261007/`，部分完成状态见schedule-v4第18节。

### 确定修复：相机重名空指针

`camera-original.vf86DS`是系统相机的真实GDB SIGSEGV反例：两个传感器保持同一
plugin name/ROS namespace，Node::Get拒绝后，栈落QoS::get_publisher_qos和
GazeboRosCamera::Load。辅助探针`passed=true`只表示符合预期崩溃反例，不是平台PASS。

项目新增独立`libeasyfly_gazebo_ros_camera.so`，不覆盖系统库、不改节点名称以避重。
它保留官方3.9.0源/头版权、Apache-2.0和原图像/位姿/QoS/时间行为，仅独立命名和
Node::Get后null guard。第二个同名插件明确拒绝，不发布第二条流；原相机继续运行。
Iris模型的两相机显式采用新库，下视模型从同一源克隆自动继承。两SITL入口plugin
搜索位置改为实际package prefix/lib，而不是不存在的share/package/lib。
回滚只需显式恢复SDF旧库名，系统安装未变；派生来源/SHA见safe_camera/README。

`camera-safe-pidfix2.GIZ61B`拒重名/首流收到数据后，真实gzserver SIGINT退出0约
.214s。`sensors-safe.kcnAB6`保留原RGB/depth30Hz、MID-360 10Hz，五话题分别收到
26/42/22/9/29条后退出0约.314s，无强杀。它们是传感器隔离证据，不是全动力学或
重复模型来源的证明。最初safe探针未识别gzserver版本化二进制，强制收尾FAIL保留；
随后原端口TIME_WAIT预检拒绝也保留，未删锁/连旧master。

### 独立EGO内存缺陷及退出检查

真实GridMap深度project方法的两个ASan红栈分别证实固定640x480 floor采样容量
不足（skip3时34240写入>34133）和filter末像素读下一像素越界。现在按实际输入尺寸
ceiling分配、以当前u索引读取当前像素，亦消除最后步越界指针算术。
五个actual-source ASan case覆盖容量/末像素/非标准尺寸/stride大于尺寸/后继零值
不污染当前深度。测试直接编译原grid_map.cpp，而不是只验证重写公式；泄漏检查
关闭，不能声称完成全栈ASan。plan_env全5CTest通过。

默认local_planner无depth/pose生产者，仅可信cloud/odom，所修深度路径不能解释
旧EGO退出SIGSEGV。没有猜测性添加析构/线程补丁。实际EGO接受合成trusted cloud/
odom且无goal，GDB下SIGINT/SIGTERM分别正常退出约.214s，无残留，证据
`ego-cloud-shutdown-aom09nkh`。plan_env当前明确Debug构建，ASan仅新测试目标；
生产库并未整体启用ASan。历史退出唯一原因仍未知。

### 完整组合退出检查与剩余问题

`full-stack.sUIm2s`最初探针向组发SIGINT、launch又转发，多个真实child exit-2，
整轮FAIL保留；不能只删正常SIGINT INFO行后签全体正常退出。
修正探针为仅通知launch，新`full-stack-owner-signal.ldy8cl`使用独立PX4 rootfs、
原两相机/MID-360、CPU检测/跟踪/SLAM/地图/桥接/飞控/任务/导航/EGO组合，未发Goal
或解锁。观察到各输入≥3条、EGO存在、connected/pose/velocity有效且receipt新鲜
disarmed后发退出；24个进程正常退出，GDB的真实Gazebo/EGO均exited normally，
launch0、退出约1.617s、无强杀/所属残留。disarmed新鲜度仅steady receipt判读，
未保存完整UAV源时序，不冒充完整ROS-source准入或任务签收。

**仍未闭环**：历史EGO stop SIGSEGV、Gazebo stop boost self-join未重现且旧真栈
缺失；旧相机重复加载来源未定位。相机guard是已确认路径修复，不能归因这两个
独立退出事故。将来需捕获自然故障/精确配置，再建最小复现；不以臆测系统依赖补丁
或升级ROS/Gazebo来消除日志。UI、实机、真实云台与G9–G11继续暂停。

## 2026-10-07 self-join真实API反例及局部兼容修复接续

第18节批次之后，真实已安装transport::Connection的last-owner反例证实：最后
引用在IO回调中释放时，Connection析构计数归零并删除IOManager，IOManager尝试
join自身，真实boost异常/SIGABRT。原栈在
`artifacts/shutdown-root-20261007/connection-before-gdb.log`，不追认缺旧真栈的
自然历史stop事故唯一原因。进展/验收详细登记schedule-v4第19节。

`safe_transport`完整私有transport＋独立easyfly_gzserver已接入两个SITL入口。
旧库内部直接绑定IOManager调用，单纯外部同名符号方案确实失败并已弃用；不是
仅靠传感器exit0签补丁。新库自身IO析构完整state交给独立清理线程，join后free；
main释放Server后drain/live0/pending0并join清理线程，绝不detach/free或吞异常。
版本及实际core/原transport指纹不匹配拒绝启动，不升级/覆盖系统库。

7生命周期case、同7case隔离完整transport ASan、原插件4CTest及SITL3CTest、
新库传感器组合和一次24进程无Goal完整平台退出全通过。ASan detect_leaks=0，
系统库未instrument；无Goal不签飞行/长循环/实机。残留进程已核对无；新增代码
定向lint通过，不是全仓lint。原日志/失败保留，当前仅主agent执行，未提交git。

两个入口通过独立server私有RPATH选副本；不要把其transport目录加入通用环境
路径。回滚只需恢复两个入口server命令为系统gzserver并重建SITL包。后续仍需
处理独立EGO历史SIGSEGV和原相机重复加载来源，整体退出故障保持部分完成。
