# EasyFly 核心接口契约（D0 / D1 / D2 / D3 / D4 / D5）

D4七方向的独立感知/融合契约见[d4-perception.md](d4-perception.md)。新增输出不自动接入实测、跟随或占据地图；标签/降落感知需要显式尺寸/ID/内参。D5已接入显式配置的精准降落控制与独立模拟云台，契约与验证边界见[d5-landing.md](d5-landing.md)，默认不自动启用精准飞行。

基线：`1860690` / 功能 `0724742`；D0提交`847dfbf`。本文说明当前生产者、消费者与调用边界；D1导航及轨迹链接口迁移见`d1-navigation.md`，公开NavigateTo字段保持不变。

D1提交`dfd6859`；D2提交`00d12b8`，SDK、受约束参数、感知及任务门面见[d2-platform.md](d2-platform.md)。D3版本化任务与搜索见[d3-missions.md](d3-missions.md)。这些客户端/服务不新增控制出口。SDK wait/close本地结果不替代远端终态；服务accept/request成功不代表执行成功。感知查询VALID空观测与未就绪/过期明确分开；任务门面和执行器共享正式YAML及旧格式校验器。

## 数据与控制流

| 接口 | 生产者 | 消费者 | frame / 时间 / 关键有效性 |
|---|---|---|---|
| /uav_state | mavlink_bridge 聚合 MAVROS | flight_control、mission_fsm、coord_transform、规划/跟随/地图 | odom、ENU/FLU；仿真 ROS stamp；connected 与 pose/velocity 等有效标志独立 |
| /uav_command | flight_control | mavlink_bridge | odom、ROS stamp；唯一业务 setpoint 出口；bridge 超时停流 |
| /odom 与 odom→base_link | coord_transform，由 UAVState 生成 | EGO、FAST-LIO 对照与 TF 组合 | pose 在 odom，twist 在 base_link；不能将它声称为 FAST-LIO 输出 |
| /Odometry、/cloud_registered | FAST-LIO | map_odom_tf、显示/定位消费者 | 上游 camera_init/body 语义按各自 header；经 TF 接入 map，不自动注入 PX4 |
| map→odom | map_odom_tf | TF 消费者 | SLAM pose 与 MAVROS odom 的相对变换，并做平滑；不是飞控定位源切换 |
| /detections | object_detection | multi_object_tracking | 图像 stamp 与归一化 bbox；图像尺寸来自配置/相机；专用推理线程 |
| /tracks_raw | multi_object_tracking | pixel_to_3d（当前配置） | 原始 SORT ID；与稳定 /tracks 输出不同 |
| /tracks | multi_object_tracking | 显示/跟踪观察者 | 经身份整合的稳定 ID；不能混用 raw 与 remap ID |
| /target_positions | pixel_to_3d | target_tracking、身份整合、显示 | 数组和每目标 header 都为 odom；深度按检测时间配对；position_valid 必须检查 |
| /target_predictions | target_prediction（独立显式启动） | 后续可视化/评估，不自动连飞行/地图 | odom参考时刻、原实测header、有限时域与模型方差；invalid/过期不能当新观测 |
| /time_sync/color/image_raw、/time_sync/depth/image_raw | time_sync（独立显式启动） | 显式选择的配对消费者，不自动重映射主链 | 原header/frame/data保留；软件容差配对，非空间配准/硬件同步 |
| /camera/calibration/status | camera_info_checker | 运维/后续UI | 持续内参/时间/frame诊断，非自动飞行准入闸门 |
| /single_tracks、/single_track/state | single_object_tracking（显式ROI） | 可显式接pixel_to_3d/显示，不自动重映射 | 原光学图像header、独立身份、归一化框；confidence=0未知，丢失空/invalid |
| /tag_observations、/landing_target | apriltag_detection、landing_detection | 独立感知；D5显式转换消费 | 原光学图像header、Tag→camera pose/尺寸；yaw光学XY，Z非离地高度，valid必查；完全等值且原上下文有效的重复图像不发布/不续期 |
| /landing/guidance_target | landing_transform | 显式配置的flight_control精准降落 | odom中心/法向；原光学source_header/尺寸/ID，完整固定外参与源时刻姿态配对；不是setpoint |
| /gimbal/state | gimbal模拟后端 | 显示/验证，不参与降落外参 | FLU角度（度）与真实模拟运动/连接状态；失联/失效不复活旧命令 |
| /lidar_camera/colored_points、/lidar_camera/depth | lidar_camera_fusion | 独立显示/评估 | 双源时间TF；着色云原XYZ/frame/stamp，稀疏深度图像header，NaN未投影 |
| /obstacles_classified | obstacle_classifier | 独立显示/评估 | 原几何完整副本；geometry_valid及association_valid/源TTL分别检查，unknown不删除占据 |
| /pointcloud_filtered | pointcloud_filter | semantic_map | 当前配置 output_frame=odom（部分旧注释仍称 base_link，以配置为准） |
| /obstacles、/occupancy_grid | semantic_map | global_planner、查询/显示 | odom；invalid/not-ready 必须传播；类别缺失不代表几何障碍消失 |
| /pointcloud_nonground | semantic_map | EGO grid_map | odom 原坐标输入；可信地面模型未就绪时空/无效；无原始点云回退；点数预算200000 |
| /planning/bspline | EGO FSM/manager | traj_server | ROS start_time、单调轨迹身份、完整控制点/knots/运行期验证 |
| /trajectory_ack | traj_server | EGO 急停恢复门 | 校验并激活后才发；ID、activation_sequence、来源身份匹配；PositionCommand 不替代 ACK |
| /position_cmd | traj_server | flight_control | odom、ROS stamp、READY/轨迹ID；先校验准入与时限，再发控制输出 |

## 时间与 QoS

- 仿真各有关节点使用 `use_sim_time=true`；MAVROS timesync 仿真策略为 NONE/0，硬件策略独立，不照搬。
- 数据 header freshness 与轨迹 start/deadline 比较保持 ROS 时钟域。已有 A*/跟随等模块使用 steady_clock 衡量到达间隔/等待，独立标注用途，不能与 ROS stamp 相减。时钟暂停/跳变场景未在 D0 做长期复验。
- 相机/深度/IMU等使用传感器 QoS；检测图像订阅可选 reliable/best_effort。订阅兼容性必须核对实际发布端，不能以节点存在代替数据到达。
- D5观测转换与下游guidance接收独立检查本地steady处理连续性，超各自原目标TTL时
  清证据并重建volatile reader，退休generation不续新证据；飞控检查在flight锁后且
  watchdog同接收callback group。原depth/可靠性、source stamp与失标期限保留。
  此保护不是所有上游排队、每topic饥饿或硬件采集时间的认证。
- D5待配对目标历史最多32帧，每帧原source/首次steady receipt预算不变；最新安全
  配对输出严格递增，不外推状态。非法新证据、几何失败、clock失效或reader重建
  清历史；容量不是额外有效期，输入水位与已发布水位分离。
- MAVLink桥接遥测fresh及setpoint watchdog同时检查ROS域和steady接收间隔；正Clock冻结
  不能令缓存永久有效，回退会使旧缓存失效。`motion_freshness_s`默认1秒，
  `slow_sensor_freshness_s`默认5秒（状态心跳/电池/GPS），RC默认1秒；这些是最后接收
  时刻，不是硬件采集时间认证。`setpoint_timeout`默认1秒，停流需经过该桥接期限，
  不承诺失效瞬间原子停止所有DDS在途样本。三个期限启动时必须有限且>0、仅启动生效，
  D2受约束参数服务不开放写入。
- 地图输出为 reliable + transient_local，便于晚加入者收到最新无效状态；EGO 非地面云为常规有界队列。占据保持是有限记忆，不代表可以无限消费旧地图。
- 各模块会继续在 D0 之后完善共用参数；目前离线一致性检查范围详见 `d0-configurations.md`，没有覆盖全部输入 QoS 和所有运行时覆盖。

## Action 与控制权

| 公共动作 | 当前 server / 下游 | 契约 |
|---|---|---|
| Takeoff / Land / GoToWaypoint / FollowTrajectory | flight_control | 单动作槽、准入状态/数值校验；取消确认后 CANCELED；失败 ABORTED；到达才 SUCCEEDED |
| PrecisionLand（/precision_land） | 同一flight_control → 所属普通Land | 父动作全程独占，观测失效停下降/接管停流；真实子终态排空后释放，未知模式另保故障锁 |
| ExecuteMission | mission_fsm → 同一SDK → 下层动作 | schema_version=1 YAML及旧格式；七类步骤严格顺序、失败即终止；精确取消所属子Goal并保留未决锁 |
| SearchArea | search_area → 同一SDK → /navigate | 弓字条带；已完成条带几何覆盖估计；真实到达后累计；有效稳定ID去重 |
| TrackTarget | target_tracking → GoToWaypoint | 需已悬停；目标首次等待、丢失、跳变与边界约束；持续操作由调用者定义结束条件 |
| NavigateTo（/navigate） | navigation_coordinator → 内部A*或受管EGO→飞行动作 | D1配置选择astar/ego/combined；无失败降级；详情见d1-navigation.md |

四个飞控Action在准入和accepted阶段都检查同锁状态/steady接收时刻：最近1秒、
connected、定位/姿态有效、有限值，以及正且不过期的ROS header（允许未来0.2秒，
不与steady时刻相减）。模式确认及真实到达同样门控；Waypoint/Trajectory的五次
到达观测只由新接收的UAVState推进，不能靠重复timer tick伪成功。这是聚合状态
消息计数，不宣称五个独立原始传感器测量。

Takeoff先确认实际OFFBOARD，再请求arm、确认实际armed，服务success不替代反馈。
显式Takeoff可从已识别且disarmed的初始模式启动（含MANUAL/降落后残留LAND），
准备中偏离所属模式的接管会终止；失败不再按低odom Z或模式确认失败主动disarm。
Land取消仅在该事务仍拥有新鲜armed/AUTO.LAND时恢复OFFBOARD；外部模式接管前后
检查不通过就停流，不抢回控制权。

状态超过1秒无更新、断连/定位或姿态失效时，终止所属动作并停止本平台setpoint，
不自动RTL/LAND/disarm，也不在反馈恢复后复活旧动作。PX4如何处理OFFBOARD-loss取决于
PX4自身配置；不能假定一定悬停、降落或返航。已有arm/mode请求仍需本地排空，取消
确认不允许与新Goal重叠；正常运行期且反馈可信的取消保留原悬停语义。

Land的完成例外只需新鲜、正/不过期header、`connected=true, armed=false`，不依赖
落地后定位；这只确认飞控已上锁，不替代接地检测。`land_timeout`按steady墙钟计算，
超时返回ABORTED、保留PX4 AUTO.LAND，不根据本地odom Z强制上锁或伪报成功。

模式确认、arm/mode服务等待使用steady有界期限并检查context，超时/退出清理pending。
已经发送的请求超时不能证明远端没执行：飞控和桥接各自锁存故障，停止输出、拒绝后续
飞行动作/arm/mode，`command_result_unknown:`消息传播此状态。真实CANCELED不代表
未决服务的远端副作用已排空。锁不自动解除；人工核查原请求不再待执行及飞控状态后，
才重启相关控制节点，不提供自动重试、盲目上锁或模式补偿。

FollowTrajectory 新 Goal 准入时锁存 ID 水位，只消费其后的新有效轨迹；旧预热、旧 Goal 与逆序消息不能激活。首帧宽限约8s，受总 deadline 约束；进入轨迹后0.5s断流阈值独立。ACK只确认 traj_server 准入，飞控 `stream_active` 和动作终态仍需分别观察。

D1受管链进一步以navigation_session_id关联FollowTrajectory/Bspline/ACK/CMD，检查先于飞控ID水位更新。生命周期消息只由受信EGO写入，新START是权威状态并停用旧流（允许depth1队列漏STOP）；STOP只匹配所属ID。该信任边界不替代DDS Security。接口同步重编译和故障锁规则见 [D1说明](d1-navigation.md)。

RTL/LAND 外部接管高于业务动作；对应操作终止并让出控制，不能报告 arrived 或抢回 OFFBOARD。取消、超时、急停、下游失活、析构都必须为已接受 Goal 收尾。D3的hover沿用既有保持行为并等待，不新增统一悬停控制出口。

D3明确公开终态不等于递归排空。/navigation/ownership、/search/ownership、/mission/ownership及D5新增/precision_landing/ownership以精确UUID查询GetActionOwnership，仅RELEASED确认动作槽释放；UNKNOWN/失联继续保锁。SDK的action_terminal_received与remote_execution_pending、ManageMission的execution_pending分别表达两种状态。生产任务链强制受管查询；新服务字段和SDK API须同步重编译各消费者，详情见D3及D5迁移说明。动作槽释放不解除独立的未知远端命令故障锁。

## 修改时需要同步的范围

D5逐帧时序诊断为默认关闭的只读启动选项。RMW系统wall、ROS源年龄、steady接收
间隔分别记录，不混作飞行准入；实际publish返回不替代飞控接收或控制循环使用。
两端256条环的累计丢失计数必须保留，缺失/歧义阶段为未知，不补0或据聚合最大值
拼接不同帧。转换、飞控和采集端字段及同机差值边界见[D5说明](d5-landing.md)。

统一D5仿真入口的plane必须由静置未解锁车辆的实际odom与独立Gazebo world
base_link真值建立固定高度偏移，在precision启动前冻结并同步到两个只读启动参数。
world模型原点不自动等于odom原点，机体接地高度也不应写死.10m。该步骤不使用
标签结果或调整质量/时间/几何容差，失败不启动precision，不在飞行中重新拟合。
它不改变生产/实机显式外参和odom平面配置责任，也不是硬件自动校准接口。

变更 frame、时间域、轨迹 ID/ACK 或急停状态时，至少检查 semantic_map、local_planner/EGO、traj_server、flight_control 及上层 Action 传播。新增 SDK/UI 只封装这些契约，不发布 MAVROS setpoint。上游 ego_to_mavros 只作示例，不进入正常平台配置。

新增参数需说明默认值、有效范围、覆盖顺序、是否可运行时修改、仿真/设备差异。新增消息字段需说明旧客户端兼容方式；修改 Action 需覆盖准入、执行、取消和终态，而不是只生成接口。
