# D1 统一导航开发接口

公开 `/navigate` 仍使用原 `NavigateTo` 字段。启动时选择 `strategy:=astar|ego|combined`，默认 `astar` 保持旧执行行为；不在失败时切成无避障直飞。RViz 的 `/move_base_simple/goal` 仅由协调器转发到公开 Action，必须是新鲜 `odom` PoseStamped；z=0 转成保持当前高度的 NaN。忙碌时拒绝目标，不隐式抢占。

```bash
ros2 launch easyfly_global_planner navigate.launch.py strategy:=combined
# 配合现有完整链：
ros2 launch easyfly_px4_sitl perception_sitl.launch.py headless:=true navigation_strategy:=combined
# navigation_dev受管配置默认选择combined，其他既有完整链配置仍选astar。
ros2 launch easyfly_sim_launcher profile.launch.py profile:=navigation_dev
```

前一命令只启动导航与监督，不启动飞控/定位/地图/EGO。仿真时间默认开启，独立系统时间组件调试需在相关入口统一传 `use_sim_time:=false`。

## 策略与边界

| 策略 | 依赖 | 执行路径 |
|---|---|---|
| astar | 有效栅格、UAVState、GoToWaypoint | 协调器→内部 `/navigate_astar`→分段飞行动作 |
| ego | 新鲜UAVState、odom、可信非空点云 | 协调器→FollowTrajectory准入→受管EGO会话→traj_server→飞控 |
| combined | 上述EGO依赖加有效栅格 | 2D A*路线→≤3m局部子目标→逐个受管EGO会话 |

组合模式只支持轴对齐 `odom` 栅格，未知格保守视为占据，不做2D路线起点“脱困”。栅格至多100万格、局部目标至多256个。目标高度默认限制0.5–2.5m，Z=NaN保持高度。每个局部目标启动前要求有效速度且≤0.3m/s，以确认悬停条件；不以Action终态代替物理速度检查。

局部走廊被新栅格阻断时，取消当前子动作并停止会话，确认两者后从当前位置重新规划，默认最多3次。默认整个公开Goal单调时间预算120s、输入等待5s、子准入/规划响应5s、取消/停止5s。EGO内部重规划仍使用原FSM，但公开任务有总预算。地图/定位失效、断流、接管、下游失败不会变成成功。截止时间只终止公开Goal，不证明底层已停止：未确认的子动作/START/STOP保留故障锁，拒绝新导航，直到迟到真实结果和成功STOP抵达。

## 会话接口与迁移

- `SetNavigationSession` `/planning/navigation_session`：非空≤128字节ID、START/STOP、目标和速度。协调器先确认 `FollowTrajectory` 已接受，再START；STOP只匹配所属会话，不停止别人的会话。
- `NavigationSession` `/planning/navigation_session_state`：可靠、transient-local生命周期通知，traj_server收到匹配STOP立即停流，并拒绝非活动会话B-spline。
- FollowTrajectory Goal、Bspline、TrajectoryAck、PositionCommand均追加 `navigation_session_id`。飞控在推进轨迹ID水位前检查会话一致；ACK也关联会话。空字符串仅用于未受管旧调试链，正常平台受管模式不接受空流。
- EGO本次请求的速度保守换算成逐轴限值，并扣除既有可行性容差，作用于manager、optimizer和B-spline物理约束，使三维指令速度范数不超过请求值；高于配置上限或过小的请求拒绝，非正 `/navigate.max_speed` 使用2m/s默认。这不保证实际PX4反馈速度无超调。
- STOP不绕过已有急停状态/ACK恢复门。急停后新START提供新的目标世代，但仍需重新确认匹配会话的停轨迹ACK、新鲜odom/cloud、稳定低速和保持时间。
- `/planning/navigation_fault`发布关联会话的急停通知；协调器只终止匹配任务，公开结果为ABORTED / `planner_emergency_stop`，不等待EGO自行恢复后误报到达。
- 受管模式强制禁用预设航点路径。局部终点位置/速度固定，refine后重新固定，仍执行原碰撞检查及最终三维速度上限检查；不通过放宽到达半径掩盖终点偏差。

这些ROS接口类型变化需要一起重编译消费者，不能混用旧生成消息库。项目所有者确认没有外部消费者；`NavigateTo`字段保持原样。完整轨迹校验、ID单调水位、独立ACK准入、8s首帧宽限及0.5s流断保护仍保留。ACK只表示traj_server激活，不表示飞控执行成功。

内部A*和目标跟踪的恢复取消均限定于所属子Goal。发送响应丢失且句柄未知时，保留故障所有权，不使用全量取消误停其他客户端；这不是目标跟踪模块的全面生命周期重构。

## 监督接口

`easyfly_obstacle_avoidance`提供 `/avoidance/get_near_obstacles`（GetObstacles）：按UAV球体到障碍轴对齐包围盒的净距筛选，默认机体半径0.3m；范围≤0不限。有效空观测保留非零时间戳，无效/过期/格式错误返回`odom`零时间戳，不能当作自由空间。`/avoidance/constraints_valid`与`/avoidance/near_obstacle`必须一起读取。

`/avoidance/stop_navigation`（Trigger）请求停止当前导航，响应成功仅表示协调器已收到请求，不是任务已经终态。监督请求携带 `/navigation/goal_id` 心跳中的公开Goal UUID，经 `/navigate/_stop_owned`（StopNavigation）匹配后才执行，迟到的旧停止请求不能停止新任务。公开结果为ABORTED / `supervisor_stop`，区别于用户取消的CANCELED。手动调试亦可调用 `/navigate/_stop`（Trigger）。这些操作仅针对导航，不是通用飞行紧急停止，不直接取消跟踪/降落。

近障自动监督默认 `auto_stop=false`；查询/手动停止始终可用。显式开启后，仅对已知活动导航在观测失效或净距≤0.5m时请求停止。不替代EGO轨迹避障，不预测动态障碍未来运动，不发布MAVROS setpoint。阈值不是实机安全认证。

自动停止仅在请求成功后锁存同一Goal；超时、异常或拒绝后按1s退避重试，未完成请求超时清理，不无限累积服务请求。

## 验证范围

组件测试与短程软件闭环是D1开发验证，不能代替PX4动力学、真实定位、传感器噪声或G9–G11验收。具体实际命令、结果与未完成项以 `schedule-v4.md` 为准。
