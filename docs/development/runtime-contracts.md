# EasyFly 核心接口契约（D0 / D1）

基线：`1860690` / 功能 `0724742`；D0提交`847dfbf`。本文说明当前生产者、消费者与调用边界；D1导航及轨迹链接口迁移见`d1-navigation.md`，公开NavigateTo字段保持不变。

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
- 地图输出为 reliable + transient_local，便于晚加入者收到最新无效状态；EGO 非地面云为常规有界队列。占据保持是有限记忆，不代表可以无限消费旧地图。
- 各模块会继续在 D0 之后完善共用参数；目前离线一致性检查范围详见 `d0-configurations.md`，没有覆盖全部输入 QoS 和所有运行时覆盖。

## Action 与控制权

| 公共动作 | 当前 server / 下游 | 契约 |
|---|---|---|
| Takeoff / Land / GoToWaypoint / FollowTrajectory | flight_control | 单动作槽、准入状态/数值校验；取消确认后 CANCELED；失败 ABORTED；到达才 SUCCEEDED |
| ExecuteMission | mission_fsm → 飞控子 Action | takeoff/waypoint/hover/land；任务线程受生命周期管理；取消传播子 Goal；当前任务文件并非完整 YAML/JSON |
| TrackTarget | target_tracking → GoToWaypoint | 需已悬停；目标首次等待、丢失、跳变与边界约束；持续操作由调用者定义结束条件 |
| NavigateTo（/navigate） | navigation_coordinator → 内部A*或受管EGO→飞行动作 | D1配置选择astar/ego/combined；无失败降级；详情见d1-navigation.md |

FollowTrajectory 新 Goal 准入时锁存 ID 水位，只消费其后的新有效轨迹；旧预热、旧 Goal 与逆序消息不能激活。首帧宽限约8s，受总 deadline 约束；进入轨迹后0.5s断流阈值独立。ACK只确认 traj_server 准入，飞控 `stream_active` 和动作终态仍需分别观察。

D1受管链进一步以navigation_session_id关联FollowTrajectory/Bspline/ACK/CMD，检查先于飞控ID水位更新。生命周期消息只由受信EGO写入，新START是权威状态并停用旧流（允许depth1队列漏STOP）；STOP只匹配所属ID。该信任边界不替代DDS Security。接口同步重编译和故障锁规则见 [D1说明](d1-navigation.md)。

RTL/LAND 外部接管高于业务动作；对应操作终止并让出控制，不能报告 arrived 或抢回 OFFBOARD。取消、超时、急停、下游失活、析构都必须为已接受 Goal 收尾。导航协调器在D1实现；统一悬停操作和完整SDK仍属于后续开发项。

## 修改时需要同步的范围

变更 frame、时间域、轨迹 ID/ACK 或急停状态时，至少检查 semantic_map、local_planner/EGO、traj_server、flight_control 及上层 Action 传播。新增 SDK/UI 只封装这些契约，不发布 MAVROS setpoint。上游 ego_to_mavros 只作示例，不进入正常平台配置。

新增参数需说明默认值、有效范围、覆盖顺序、是否可运行时修改、仿真/设备差异。新增消息字段需说明旧客户端兼容方式；修改 Action 需覆盖准入、执行、取消和终态，而不是只生成接口。
