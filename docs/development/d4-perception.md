# D4 感知与融合扩展

D4 依 plan-v3 实现七个子方向的第一版软件功能。用户确认预测独立输出、AprilTag 36h11＋显式尺寸、CSRT＋显式ROI重定位，以及独立障碍语义副本。这些扩展默认不加载到既有飞行/占据链；启动、implemented、ready及飞行准入是不同概念。构建、行为测试、审查与未覆盖边界以schedule-v4第10节为准。

## 时间配对

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
# 默认模拟时钟；非模拟图显式 false：
ros2 launch easyfly_time_sync time_sync.launch.py use_sim_time:=false
```

time_sync_node 默认订阅 /camera/color/image_raw 与 /camera/aligned_depth_to_color/depth/image_raw，分别向 /time_sync/color/image_raw、/time_sync/depth/image_raw 发布软件配对后的原消息。它不修改 stamp/frame/data，不做深度配准/重采样，不宣称硬件同步；不自动重映射既有 pixel_to_3d 输入。更换输入可通过启动参数/ROS remap，但两个输入及输出须保持互异，避免意外自反馈。

输入按各自严格递增正时间入队，使用有序 FIFO 在容差内配对，不宣称全局最近邻最优；超差丢较早的一侧。源年龄用 ROS 时间，接收年龄/时钟进展用 steady 时间。未来超过 0.2s、旧数据、重复/乱序、零时钟、暂停过久或时钟回退不能形成可信新配对；回退清队列和旧配对，并允许新时钟域重新建立。几何/字节布局异常、超单帧预算、队列满、总排队字节超限、过期均有丢弃计数。传输消息只做布局预算检查，不解释像素编码或证明两个传感器空间配准。

| 只读启动参数 | 默认 | 范围/含义 |
|---|---|---|
| tolerance | 0.03s | 0–0.5s，且 ≤ max_age |
| max_age | 0.5s | 0.05–10s，同时约束源、接收及暂停时限 |
| queue_size | 8 | 每侧 1–32 条 |
| max_queued_bytes | 67108864 | 1–134217728 字节，应用层两队列合计 |
| max_image_bytes | 4194304 | 1–16777216 字节；宽/高另限 1–8192 |
| first_topic / second_topic | 上述相机输入 | 非空、互异 |
| first_output / second_output | 上述独立输出 | 非空、互异且不与输入相同 |

预算是应用处理队列/载荷预算，不包含 DDS 反序列化前已分配的消息和中间件缓冲；不是对恶意 DDS 发布者的完整内存安全防线。输出仍为 SensorDataQoS，接入时消费者须兼容 best_effort。

/time_sync/status 的 TimeSyncStatus 提供最后成功配对的两份原 header、signed delta_seconds（第二源时间−第一源时间）、当前 pair_valid、原因、累计配对/两侧丢帧/排队计数。pair_valid 表示最后成功配对仍新鲜且时钟有效，不代表图像内容可信或飞行准入；后续异常输入单独报告原因/丢弃，不能将一份历史 header 解释为当前新观测。两个输出话题不是原子复合消息，消费者仍应按原 header 做关联。

/platform/time_sync/capabilities 区分 software_image_pairing 实现/当前配对 ready 与 hardware_clock_sync unsupported。

## 标定加载与持续诊断

```bash
ros2 launch easyfly_camera_calib calib_tf.launch.py use_sim_time:=false
# 可显式选择可信本地标定文件（不是在线求解器）：
ros2 launch easyfly_camera_calib calib_tf.launch.py use_sim_time:=false calib_file:=/path/to/sensors.yaml
```

沿用包内 sensors.yaml 的安装外参/相机内参。calib_tf_publisher 先解析并校验整份常规文件（≤64KiB、单文档、有限值、字段/向量、frame、重复 child 与 TF 环），全部通过后才发布完整静态树；后半份非法不能先发布前半份 TF。相机/雷达 translation 范围 ±100m，RPY 范围 ±π；frame 非空、有界、不含空白/前后斜线，不允许 self/重复 child/cycle。

第一版相机内参 width/height 1–8192、fx/fy 0.001–100000、cx/cy 在图像范围；只支持现有 plumb_bob＋5 个有限畸变系数。其它畸变模型明确拒绝，不声称支持 fisheye/rational-polynomial。修改标定文件要求重启同一标定入口，不提供任意运行时外参写入，也不监控文件自动更新。

CameraInfoChecker 不再只检查第一帧。/camera/calibration/status（DiagnosticArray）持续报告 not_received、valid、frame/分辨率/K/内参/畸变失配、非法/未来 stamp、stale、clock_not_ready/paused/reset；附 source_age_seconds。默认订阅 /camera/color/camera_info，SensorDataQoS；tolerance=1 像素（0–10），max_age=1s（0.05–10），与 calib_file / camera_info_topic 均为只读启动参数。

源和接收年龄独立检查；模拟未收到 /clock 不可 valid，重复收到同 stamp 不能掩盖暂停时钟，回退清掉旧缓存。该诊断是校验结果，不是替换飞控准入的自动闸门；既有 pixel_to_3d 的接入/内参更新逻辑本批未重构，不把校验节点存在等同于整条感知数据已安全。

## 独立目标预测

```bash
ros2 launch easyfly_target_prediction target_prediction.launch.py use_sim_time:=true
```

仅订阅实测 /target_positions，向 /target_predictions 发布 TargetPredictionArray。不写 /target_positions、实测跟踪话题、UAVCommand、导航动作或障碍地图。恒速模型至少需要两次同身份真实观测；源/接收新鲜度、odom、数组/条目完全同 stamp、非负唯一 ID、position_valid、有限位置/置信度和三维速度范数均检查。

非法整帧（含一个非法目标）、重复/乱序时间、过量输入保守清空全部历史；空帧/身份消失立即清掉模型；类别变化、跳变/过速重建基线。缓存和输入量默认 256（1–1024），源/接收与 clock-progress 时限默认 0.5s（0.01–5）；过期、零/暂停/回退时钟不能靠新 receipt 延续旧预测。

TargetPrediction.header 是当前 ROS 参考时刻；observation_header 保留原实测时间/frame；horizon_seconds 默认 0.5（0–2），表示参考时刻之后的时域。位置 = 原观测 + 估计速度 ×（观测年龄 + 时域）。等轴方差为 base_variance + variance_growth×间隔²，默认 0.04m²、1m²/s²；这是模型参数化估计，不是传感器标定协方差或经统计校准的可靠概率。invalid/空输出不能继续用于跟随或占据推断。

/platform/prediction/capabilities 报告恒速模型 implemented，仅有当前有效模型时 ready；ready 非飞行许可。完整参数范围见 [预测包 README](../../src/perception/p3_tracking/easyfly_target_prediction/README.md)。

## 单目标跟踪

本轮 lint/SITL 修复统一了 CSRT、标签与降落感知的源时间准入：允许最多
`min(0.2s, max_age_seconds)` 的小幅未来时间差，以处理 Gazebo 图像与 `/clock`
经 DDS 到达顺序不同的情况。原 header 不改写；超预算未来帧、旧帧、接收过期、
零/暂停/回退时钟及身份隔离仍拒绝。真实 Clock 回归覆盖 +69ms 图像/观测、
+36ms CameraInfo 通过及 +201ms 拒绝。这不是飞行控制授权。

```bash
ros2 launch easyfly_single_object_tracking single_object_tracking.launch.py use_sim_time:=false
# 实际相机在 /camera/color/image_raw 时，请显式 remap /camera/image_raw：
ros2 run easyfly_single_object_tracking single_object_tracking_node --ros-args \
  -p use_sim_time:=false -r /camera/image_raw:=/camera/color/image_raw
```

OpenCV C++ CSRT输出独立`/single_tracks`（TrackInfoArray）、`/single_track/state`（SingleTrackState），`/single_track/manage`（ManageSingleTrack）接受initialize/reset/query。初始化必须给出所显示最新图像的精确header、归一化左上角/宽高ROI（完全位于图内，至少8×8像素）。每个接受的新ROI分配新身份；accepted只表示排队，不代表CSRT已初始化。丢失不自动猜测身份，必须显式重定位；reset回idle。状态含initializing/relocalizing/tracking/lost；失效输出空数组，不能把旧框继续当当前目标。

所有帧要求配置的optical frame、正且递增原图时间、packed mono8/rgb8/bgr8，16×16以上、最多2073600像素。源与接收年龄及clock progress默认0.5s（0.05–5s，参数max_age_seconds）；参数只读，optical_frame默认camera_color_optical_frame。DDS depth1、可替换latest工作槽、worker-owned CSRT与generation隔离新ROI/reset/旧工作，退出join，不在ROS回调里做重计算。

置信度0表示**未知**，不是检测失败概率或伪造的1；没有标定概率、3D位置或速度输出。既有pixel_to_3d的`tracks_topic`可显式改为`/single_tracks`，仍须提供时间匹配的真实深度、正确光学TF及有效3D状态。该接入不自动启用，不与SORT主链混发身份；目标预测默认置信度阈值也不会把未知置信度自动解释为可靠。未做真实飞行跟随效果签收。`/platform/single_tracking/capabilities`只报告独立算法状态。

## 标签与降落目标

```bash
ros2 launch easyfly_apriltag_detection apriltag_detection.launch.py \
  use_sim_time:=false tag_size_m:=0.2
ros2 launch easyfly_landing_detection landing_detection.launch.py \
  use_sim_time:=false selected_tag_id:=7
```

标签默认订阅`/camera/image_raw`、`/camera/camera_info`，真实color话题须显式remap二者；不得把命令示例0.2m当实物标定。tag_size_m默认0（未配置，范围0–10m）；selected_tag_id默认-1（未选择）。不配置可信尺寸/ID时不输出可信降落目标，不自动挑“第一个标签”。

标签使用36h11字典及IPPE_SQUARE：输出Tag→camera optical位姿、原图header、ID、尺寸、角点RMS重投影误差与有效性。多个有正深度的位姿候选只有明显更优时才接受；数值等价候选去重，真实不同且误差近似时拒绝。正对标签也可能因平面位姿歧义保持invalid，这是保守行为。支持匹配尺寸/frame/时间的常规K及plumb_bob/rational_polynomial、0/5/8个有限畸变系数；本批加载器仅plumb_bob5，与此检测器支持范围不混淆。图像布局/预算同CSRT，至多64检测；generation＋有界latest worker丢弃旧工作。

`/tag_observations`（TagObservationArray）valid空帧意味着有效图像无标签；缺内参、尺寸、坏frame、旧/重复/乱序帧、零/暂停/回退时钟等是invalid。单条位姿也必须检查valid。阈值只读：max_age_seconds=.5、max_reprojection_error_px=2（0–20，开区间下界）、ambiguity_margin_px=.2（0–5，开区间下界）。误差不是标定质量概率。

D5后续经用户确认追加受限重复传输例外：仅完整字段/像素相同且原TTL、源时间、
时钟与标定上下文仍有效的重复图像静默忽略，不发布、不续期、不计新证据。
异内容、倒序、过期或上下文失效仍invalid；详见[D5说明](d5-landing.md)。

降落适配器在`/landing_target`（LandingTarget）保留原图header；必须恰有一个有效且显式选择的ID，重复ID/无标签/上游invalid/非单位四元数/非正深度/不可观测方向/失配或过期均invalid。中心pose在相机光学坐标；yaw_rad为标签局部X轴在光学XY平面的方向，**不是ENU航向**；optical_depth_m是相机Z，**不是离地高度**。没有机体/地面坐标转换、降落动作或下降命令。原`GetPerception`仍只查询targets/obstacles；`/platform/perception/capabilities`的landing_detection已实现，但ready必须有实际新鲜有效LandingTarget；precision_landing保持未实现。静态landing_dev profile不自动变为飞行就绪。

## 独立雷视投影

```bash
ros2 launch easyfly_lidar_camera_fusion fusion.launch.py use_sim_time:=false
```

输入color Image、color CameraInfo与`/pointcloud_filtered`，以fixed_frame=odom进行双源精确时间TF：camera@图像时间←点云frame@点云时间，不用latest TF回退。有序图像队列8、latest cloud槽、joinable worker、epoch作废保护；只读max_age=.5s（.05–10）、tolerance=.05s（0–min(.5,max_age)）、max_points=20000（1–200000）。另可配置三个输入话题、camera_frame与fixed_frame。

纯几何Brown-Conrady plumb_bob5投影，正深度且在图内点按最近像素Z-buffer保留最近点，RGB来自原图；只处理同像素遮挡，不宣称完整表面/动态目标运动补偿。独立`/lidar_camera/colored_points`保留原点云frame、时间和源XYZ，额外packed UINT32 RGB；`/lidar_camera/depth`保留图像header、32FC1相机Z（米），未投影像素NaN，**不是原有对齐深度替代物**。有效空投影与失败由`/lidar_camera/status`区分；无TF、超容差、坏K/布局/预算、过期/时钟异常无可信新输出，能力ready=false。

图像≤2048×2048且≤1048576像素、≤4MiB（允许行padding）；CameraInfo有限常规K、正焦距≤100000、主点在图内。点云≤8MiB、point_step≤256、≤32 fields；支持有padding行、大小端FLOAT32/64 xyz，禁止xyz字段重叠；非有限点过滤，有限坐标绝对值≤100000。四元数有限且近单位。预算是应用层检查，不替代DDS安全/反序列化限额。该节点不发布地图/飞行输入。

## 独立障碍类别副本

```bash
ros2 launch easyfly_semantic_map classification.launch.py use_sim_time:=false
```

独立obstacle_classifier读取`/obstacles`（reliable/transient_local）和实测`/target_positions`，发布`/obstacles_classified`（ClassifiedObstacleArray），不改变既有semantic_map_node.cpp、原几何障碍、非地面云或占据栅格。原header、ID、中心、尺寸、动态状态及速度完整保留；仅副本obstacle_type和独立类别元数据可变化。

关联使用expanded AABB：margin默认.3m（0–2）、min_confidence=.7（0–1）、max_age=.5s/association_ttl=.5s（.05–10）、time_tolerance=.15s（0–min(.5,age,ttl)）；全为只读。数组及条目须odom、同正源时间；每侧最多256，目标非负唯一ID/有限且position_valid。**候选图两个方向均唯一**才贴类别，不因另一个框歧义就忽略其候选边。observed_at保留目标源时间，expires_at=源时间+TTL，不用重复publish延长有效期。

坏/低置信度/过期/丢失目标、重复几何ID、多对一/一对多关联输出unknown并保留有效几何；几何本身非法/过期或时钟异常则geometry_valid=false，不能将其空副本理解为“没有障碍”。消费者必须同时检查geometry_valid及association_valid/有效期，不能凭类别取消避障。`/platform/classification/capabilities`只有当前有效关联时ready，unknown有效几何不表示分类ready。

## 接口迁移与验收边界

新增九消息：TargetPrediction/Array、TimeSyncStatus、TagObservation/Array、LandingTarget、SingleTrackState、ClassifiedObstacle/Array，及ManageSingleTrack服务；旧Target3D/Array、ObstacleInfo及飞行动作字段不变。需生成easyfly_msgs并重编译相关包；不要把新类型或新话题冒充旧实测消息。已有profile不自动加载新扩展；各launch默认以源码为准，仿真显式use_sim_time=true，非模拟显式false。新增实现使用已安装C++ OpenCV；当前Python cv2与NumPy版本不兼容，未修改系统环境，图像夹具由C++生成、ROS测试不依赖cv2。

验收使用纯核心与真实ROS节点/Clock输入，包含合成纹理CSRT、标定倾斜36h11图像、几何投影/遮挡、分类丢失/歧义及旧地图回归；合成数据不代表真实视觉精度。未做硬件时钟同步、实际标定求解、真实跟随/相机搜索覆盖、SITL或实机签收。主/子agent分工及实际结果见[schedule-v4第10节](../../schedule-v4.md)。D3四项lint欠账仍保留；未运行完整linter，不把行为通过记作所有注册检查通过。

2026-10-05后续按用户授权实际跑lint/SITL，见schedule-v4第10.9节：79注册lint中40失败；PX4基础起飞/降落通过；时间配对、预测、雷视投影与类别副本出现有效真实仿真输出。single/tag严格拒绝source_stamp大于now的消息，在Gazebo图像先于/clock到达时误拒绝（实测36–69ms超前），landing因上游invalid而未就绪；这些模块的SITL集成未通过。traj_server及perception_srvs退出另有问题。未修或用改stamp绕过，不据此前组件通过宣称全链可用；完整SITL及实机仍未签收。

2026-10-05修复与后续排查见schedule-v4第10.10–10.11节：三视觉时间准入、
traj_server/perception_srvs退出及本轮格式问题已修复验证；用户选择自有代码
Apache-2.0后，原11包的79项注册lint与32项行为回归全部通过。基础SITL起降、
新增感知输出及一次完整退出复跑通过；历史偶发EGO退出段错误和Gazebo线程
self-join仍未捕获真实故障栈，不将复跑通过当成已修复。
另已由原core确认旧Gazebo相机重复节点后的空指针路径，属于独立的加载事故，
详见[退出诊断记录](shutdown-diagnostics.md)。真实标签、精准降落与实机边界不变。
