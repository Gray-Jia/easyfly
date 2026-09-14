# EasyFly 项目问题清单（question.md）

> 生成时间：2026-09（阶段三 M6 完成后全项目审查）
> 更新时间：2026-09-13 —— **P0 全部修复并实测通过**（见文末"修复记录"）
> 性质：**只记录，不修改**。按"危害程度 × 触发概率"分级，供阶段四开工前排期修复。

---

## 一、控制安全类（P0 — 实机部署前必须修复）

> **状态：本节 Q1-Q10 已全部修复（2026-09-13），修复方案与实测结果见文末"修复记录"。**

### Q1. PID 控制器是死代码（✅ 已修复：移除，架构定位为 setpoint 生成器 + PX4 内环）
- **位置**：`easyfly_flight_control/src/flight_controller.cpp`
- **现象**：`PID::update()` 从未被调用，`control_loop` 里没有任何 PID 计算路径。PID 结构体定义、实例化、reset 都在，但整个控制实际是"setpoint 斜坡 + PX4 内环闭环"，easyfly 自己的控制器没有闭环。
- **影响**：`easyfly_flight_control` 名不副实；将来切 ATTITUDE/ANGULAR_RATE 模式（PX4 外环关闭）时没有任何姿态控制能力，会直接失控。
- **附带**：PID 增益硬编码在构造函数里（kp=2.0 等），`control_rate` 参数化了但增益没有。

### Q2. 低电量安全只报警、不动作（✅ 已修复：RTL + 中止任务 + 取消子 action）
- **位置**：`easyfly_mission_fsm/src/mission_fsm.cpp` `safety_check()`
- **现象**：电量 < 15% 只置 `emergency_` 标志 + 发布 EMERGENCY 状态，**不触发 RTL、不取消当前 action、不通知 flight_control**。且 `emergency_` 只在两个 step 之间的循环检查——若正在执行一个长航点（result 等待最长 120s）或 hover 步骤（`sleep_for` 阻塞），低电量在整个任务期间完全无效。
- **影响**：实机低电量会一直飞到坠机。整个平台也**没有实现任何 RTL 触发逻辑**（flight_mode=6 的映射存在但无调用方）。

### Q3. Land 取消逻辑断裂（✅ 已修复：恢复 setpoint 流 + 切回 OFFBOARD）
- **位置**：`flight_controller.cpp` `handle_land_cancel()`
- **现象**：取消降落时把 `active_` 切回 HOVER，但此时 PX4 已进入 AUTO.LAND 模式，HOVER 发布的 setpoint 位置会被 PX4 忽略——**飞机会继续降落**。同时 `hover_*` 未用当前位置刷新（见 Q4），若之后模式切回 OFFBOARD，setpoint 会跳回旧悬停点。
- **影响**："取消降落"这个操作实际不可用，行为不可预期。

### Q4. 取消航点/起飞后悬停目标 stale（✅ 已修复：守卫反馈刷新悬停点）
- **位置**：`flight_controller.cpp` `handle_waypoint_cancel()` / `handle_takeoff_cancel()`
- **现象**：取消航点后 `active_=HOVER`，但 `hover_x_/y_/z_/yaw_` 还是**上一个任务完成时**的值。若上一个任务在 20m 外，取消瞬间 setpoint 跳变到 20m 外，飞机猛冲。
- **影响**：飞行中取消航点是危险操作。

### Q5. Takeoff / Waypoint 无超时保护（✅ 已修复：deadline 估算 + abort 就地悬停）
- **位置**：`flight_controller.cpp` control_loop
- **现象**：Takeoff 完成判定 `|target_z − z| < 0.5`，Waypoint 判定 `dist < accept_radius`——若因 EKF 异常、气流、目标不可达，判定永远不满足，**action 永远 pending**，没有超时 abort。Land 有 60s 超时，唯独这两个没有。
- **影响**：任务级联阻塞（mission_fsm 的 120s result 超时会兜底 abort mission，但 flight_control 内部的 active_ 状态卡死，无法接受新 goal，需要重启节点）。

### Q6. Land 超时路径会空中 disarm（✅ 已修复：仅落地 z<0.3 允许 disarm）
- **位置**：`flight_controller.cpp` LANDING 分支
- **现象**：降落超时（60s 仍未 disarm）→ `call_arm(false)` 强制上锁。若此时飞机仍在空中（AUTO.LAND 失败、被卡住），**空中 disarm = 电机停转 = 自由落体**。
- **影响**：把一个失败模式升级成了坠机模式。

### Q7. Takeoff 的 yaw 用反馈连续刷新（✅ 已修复：起飞时锁存）
- **位置**：`flight_controller.cpp` TAKEOFF 分支 `cmd.yaw = uav_.yaw`
- **现象**：位置 setpoint 已在 M6 改为"目标渐近式"抗毛刺，但 takeoff 的 yaw 仍每周期取反馈值。mavros 姿态若出现尖峰（与 local_position 毛刺同源），yaw setpoint 会跟着尖峰跳变。
- **影响**：起飞阶段姿态指令可能瞬间大幅跳变。

### Q8. 任务 YAML 解析无异常保护（✅ 已修复：safe_stod + 全串消费校验 + 顶层 try/catch）
- **位置**：`mission_fsm.cpp` `parse_mission()`，`std::stod(val)` 裸调用
- **现象**：YAML 里 `altitude: 2.5米`（中文/空值/字母）→ `std::stod` 抛异常 → 在 **detached thread** 中未捕获 → `std::terminate()` → **整个 mission_fsm 进程崩溃**（正在飞的任务失去状态机监管）。
- **影响**：一个手误就可能让飞行中失去任务管理层。

### Q9. 模式切换结果不校验（✅ 已修复：wait_mode_engaged 轮询确认 + uav_ 加锁）
- **位置**：`flight_controller.cpp` `call_set_mode()` + `mavlink_bridge.cpp` `cb_set_flight_mode()`
- **现象**：只检查 `mode_sent`（MAVLink 命令已发送），不验证 PX4 是否**实际进入** OFFBOARD。若 setpoint 流断（PX4 要求 OFFBOARD 前有 >2Hz setpoint 流），切 OFFBOARD 会静默失败，takeoff 流程照常推进但飞机不动。
- **影响**：起飞失败表现为"action 卡住"而非明确报错。

### Q10. 任务取消无法中断正在执行的步骤（✅ 已修复：轮询等待 + cancel 子 goal + 可中断 hover）
- **位置**：`mission_fsm.cpp` `execute_step()` 各 `wait_for(60s/120s)` + hover 的 `sleep_for`
- **现象**：`handle_mission_cancel` 置 `emergency_` 后，正在阻塞等待的 action result 要等它自己完成/超时才返回；hover 步骤的 sleep 完全不可中断。
- **影响**：取消任务的响应时间最差可达 120s。

---

## 二、控制质量类（P1 — 影响行为正确性/可维护性）

> **状态：Q11/Q12/Q14-Q18 已修复（2026-09-13），Q13 缓做（阶段四按需），详见文末"修复记录"。**

### Q11. flight_control 未设 use_sim_time（✅ 已修复：launch 化注入，Q26 一并解决）
- **位置**：`flight_control_node.cpp`（手动 `ros2 run` 启动，无 launch、无参数）；control_loop 用 `create_wall_timer`；takeoff 进度 `t = now() - start` 依赖节点时钟
- **现象**：节点 use_sim_time=false 时 `now()` 是墙钟。仿真降速/暂停（gzserver 负载高）时，takeoff 爬升速度和 waypoint 步长按墙钟推进，与 sim 时间脱节。
- **影响**：仿真时间不实时时控制行为畸变；实机无影响（但架构上控制周期应统一由时钟策略管理）。

### Q12. dt 固定为 1/control_rate（✅ 已修复：实测周期 + 限幅 [0.5/rate, 2/rate]）
- **位置**：`flight_controller.cpp` control_loop `double dt = 1.0 / ctl_rate_;`
- **现象**：不用实测周期。当前 PID 未启用（Q1）暂无实害，一旦启用 PID，回调延迟会造成积分/微分错误。

### Q13. UAVState 字段时间不同源
- **位置**：`mavlink_bridge.cpp` 20Hz 定时器拼装 pose/imu/battery 等不同频率话题的缓存值
- **现象**：同一条 /uav_state 里姿态（IMU 高频）和位置（EKF）时间差可能几十 ms。下游 odom_tf（M1）用它生成 TF，机动时有对齐误差。

### Q14. ANGULAR_RATE 模式 type_mask 位错误（✅ 已修复：0b10000000，仅忽略姿态位）
- **位置**：`mavlink_bridge.cpp` `att.type_mask = 0b10000111`
- **现象**：0b10000111 同时置位了 IGNORE_ROLL_RATE | IGNORE_PITCH_RATE | IGNORE_YAW_RATE | IGNORE_ATTITUDE——**把想使用的角速率全忽略了**（正确应约 0b11000000：忽略姿态和推力）。代码注释"bit0 使用角速率"对位语义理解反了。
- **影响**：当前未使用该模式，纯埋雷；一旦接 E2 规划层的姿态指令会静默失效。

### Q15. ATTITUDE 与 ATTITUDE_THRUST 无区分（✅ 已处理：msg 注释明确为历史别名，勿新增使用）
- **位置**：`mavlink_bridge.cpp` encoder switch，两个 case 落到同一处理，都发 thrust
- **现象**：语义上 ATTITUDE（姿态+推力）与 ATTITUDE_THRUST 应该不同（后者通常是归一化推力），现在无法区分。

### Q16. Waypoint 完成判定无去抖（✅ 已修复：ramp 完成 + 连续 5 帧双条件）
- **位置**：`flight_controller.cpp` `dist < wp_accept_radius_` 单帧判定
- **现象**：反馈毛刺尖峰（M6 实测 z 尖峰 -10m）理论上可造成瞬时距离虚短 → 误判完成（概率低，但毛刺已被证实存在）。

### Q17. rc_connected 无掉线检测（✅ 已修复：1s 超时置 false）
- **位置**：`mavlink_bridge.cpp` `cb_rc_in()`
- **现象**：收到任何 RCIn 就置 true，永不回落。遥控器断开后 rc_connected 仍为 true。

### Q18. flight_mode 整数映射语义混乱（✅ 已处理：保守文档化，下游仅依赖 3/6/7）
- **位置**：`mavlink_bridge.cpp` `cb_state()`，AUTO.LOITER→2(POSCTL) 等"等同"近似
- **现象**：AUTO.LOITER 和 POSCTL 是不同模式，映射成同一个数；下游无法区分 PX4 真实模式。flight_control 只认 3(OFFBOARD)，目前无实害。

---

## 三、感知类（P1/P2）

> **状态：Q19/Q20/Q23/Q25 已修复（2026-09-13，实测 ID 168→26）；Q21/Q22/Q24 维持文档记录（仿真保真度/实机部署事项，见"九、感知类修复记录"）。**

### Q19. 飞行中跟踪 ID 跳变严重（✅ 调参缓解 168→26；⚠️ M4.1 验收显示 id 轮换仍是主要波动源，建议 M4.2 前专项处理）
- **位置**：`easyfly_multi_object_tracking`（SORT 关联参数）
- **现象**：调参后单次飞行 ~26 个 ID 仍有更替（视野边缘进出/遮挡闪断的自然更替）。M4.1 实测发现→跟随的间隙（数秒视角变化）足以让 SORT 重排全部 id，跟随节点已加"重捕获"缓解，但按固定 id 采样的验收/上层逻辑仍会被打穿。
- **建议**：M4.2 开工前评估 ① SORT 参数再调优 ② 外观特征重识别（ReID）——跟随/跟拍类上层功能对此敏感。

### Q20. pixel_to_3d 深度与 tracks 无时间同步（✅ 已修复：深度环形缓冲 + 最近时间戳匹配）
- **位置**：`pixel_to_3d_node.cpp` `last_depth_`（最新帧）+ tracks 时间戳
- **现象**：两者时间差最多一帧（~70ms），2m/s 飞行下目标 3D 位置偏差 ~14cm。另有 TF 查询失败回退 latest 的已知妥协（代码注释已说明）。

### Q21. 相机视野下半幅被机身遮挡（已知，M1 记录）
- **位置**：iris 模型 iris.stl 视觉 mesh 包络 vs 相机安装 (0.25, 0, 0.22)
- **现象**：视野下半近距区域拍到机身/旋翼。低空小目标（近处行人下半身）检测受影响。

### Q22. MID-360 平放高度 >5m 看不到地面（已知，M6 记录）
- **位置**：mid360 模型安装 + livox 插件坐标系
- **现象**：垂直 FOV 中心朝上，5m 高度地面点为 0。当前用 2.5m 低空飞行 workaround；实机必须倒装/斜装并重标 FAST-LIO 外参，届时仿真外参全部要重做。

### Q23. 仿真相机深度 far=10m 截断（✅ 已修复：far 10→20m，实测 19.45m 目标 3D 恢复）
- **位置**：SDF `<clip><far>10.0</far>` + pixel_to_3d max_depth=9.5
- **现象**：10m 外目标检测框正常但无 3D 位置。阶段四若做远距跟踪/规划需加大 far（性能代价）。

### Q24. livox 仿真插件无噪声模型
- **位置**：`livox_laser_plugin`（CSV 扫描 + 理想点云）
- **现象**：FAST-LIO 在仿真中的表现（全程稳定）不能代表实机（Livox 噪声、运动模糊、雨雾）。SLAM 鲁棒性验证存在仿真-实机鸿沟。

### Q25. 检测层无类别过滤配置（✅ 已修复：tracking.yaml target_classes 配置为关注类别）
- **位置**：detection.yaml 无 target_classes，tracking 有该参数但未配置
- **现象**：全部 COCO 类别都进入跟踪/3D 输出，下游拿到大量无关目标（bench、potted plant 等）。

---

## 四、工程/架构类（P2 — 影响开发效率与部署）

### Q26. flight_control / mission_fsm 没有 launch 文件（✅ 已修复：各自 launch + perception_sitl 集成一键可飞）
- **位置**：`src/execution/` 下两个包均无 launch 目录，靠 `2.txt` 备忘手动 `ros2 run` 启动
- **现象**：与 perception_sitl.launch.py 无集成，启动顺序靠人脑记；use_sim_time 无法统一注入（Q11）；感知仿真起来后还要手动起控制节点才能飞。

### Q27. perception_sitl 用固定 TimerAction 编排，无就绪握手
- **位置**：`perception_sitl.launch.py` 3/6/8/12/14/16/18s 硬延时
- **现象**：机器慢（冷启动、模型加载慢）时，mavlink_bridge 8s 启动时 mavros 可能未就绪；无进程监控，节点崩溃无自动重启、无告警。

### Q28. map→odom TF 单点依赖 FAST-LIO 存活
- **位置**：`easyfly_fast_lio_integration`
- **现象**：fast_lio 崩溃后 `map` frame 失效：RViz fixed frame=map 全部消失、pixel_to_3d（target_frame=map）停止输出。odom 链独立存活，但没有降级策略（如 fast_lio 挂掉后 target_frame 自动切 odom）。

### Q29. 桨叶 collision 置 0.001 的物理失真
- **位置**：`easyfly_iris.sdf` rotor collision radius 0.001（M6 为解决桨叶遮挡雷达所改）
- **现象**：桨叶不再与任何物体碰撞——无人机可以以桨叶"穿过"障碍物；坠落/撞击仿真失真。更好的方案是让 LiDAR 射线忽略桨叶（sensor layer filter）而非砍掉碰撞。

### Q30. 计划内空壳包（非缺陷，盘点）
- C2：`udp_protocol`、`mesh_comm`（骨架）
- P1：`pointcloud_filter`、`time_sync`
- P2：`apriltag/landing/ellipse/color_line/reid` 五个检测包
- P3：`single_object_tracking`、`target_prediction`
- E2 规划层全部
- M6 决策：pointcloud_filter/time_sync 推迟到阶段四按需实现。

### Q31. onnxruntime GPU SDK 与当前机器绑定
- **位置**：`third_party/onnxruntime/`（1.23.2 gpu，CUDA 版本对应本机 RTX 5060 Ti 环境）
- **现象**：换机器/换 CUDA 需重新放置 SDK；无 CPU 回退（代码支持 onnxruntime CPU EP，但打包的库是 GPU 版）。

### Q32. 控制逻辑零测试（✅ 已建回归套件：test/ 目录，T1-T8 覆盖起飞/航点/取消/连续起降/坏任务/低电量 RTL，2026-09-14 实跑全绿；单元级测试仍缺）
- **现象**：SORT 有 `test_sort.cpp`，flight_control / mission_fsm / mavlink_bridge 无任何单元测试。状态机转换、超时路径、取消路径全部只能靠仿真手测。

### Q33. TrackInfo.velocity 字段语义借用
- **位置**：`tracking_node.cpp` L151，像素速度塞进 velocity_x/y 字段（注释说明"像素/frame"）
- **现象**：消息字段语义与名字不符，下游若按 m/s 理解会出错。应加专门字段或文档化。

### Q34. mavros EKF 启动位置毛刺（M4.0 新发现，semantic_map 已防护，其余消费方待查）
- **位置**：`/uav_state` ← mavros local_position/pose（源头在 PX4 EKF）
- **现象**：仿真启动后最初数秒 local_position 报错误位置，实测两次分别为 (0.98,-2.52) 与 (1.08,-2.57)，之后收敛到 (0,0)。与 M6 记录的 z=-10 尖峰同族。
- **影响**：一切消费 `odom←base_link` TF 的节点会把整个场景按错误平移量复制/扭曲。semantic_map 已加"TF 跳变守卫"（帧间平移 >1m 丢帧 + 持续漂移 10 帧重置基线，见 `semantic_map_node.cpp`）；**pixel_to_3d 与 M4.3 的 EGO grid_map 集成时需同样注意**（SLAM odom 系不受影响——FAST-LIO 自己的原点）。flight_control 的渐近式 setpoint 天然免疫。
- **验收影响**：M4.0 验收中"物体位置整体偏移 ~2.4m"的假象即源于此，非聚类/地面剔除问题。

### Q36. X/GLX 资源耗尽导致仿真无法启动（M4.1 复验期新发现，环境怪癖）
- **现象**：同一 X 会话内高频启停仿真 ~10 次后，gzserver 报 `X Error ... GLX / X_GLXCreateContext`（BadValue），世界无法初始化 → spawn 卡住 → PX4 等 TCP 4560 超时 exit 255 → 全链路无数据。杀 gzclient/rviz2、冷却 30s 均无效（gzserver 自身离屏渲染同样需要 GLX）；重启 X 会话（注销/重启）后立即恢复。
- **根因**：Xorg 累积的 GLX 上下文状态损坏/资源泄漏，属桌面 X 会话层问题，非 EasyFly 代码问题。
- **缓解**：① 自动化验收优先在重启后的会话跑；② 长会话多次启停后出现 "PX4 exit 255 + GLX 报错" 组合，直接重启会话，不要排查代码；③ 未来可装 Xvfb 让仿真跑独立虚拟显示（未验证）。

### Q35. ~/.gazebo/models 本地缓存抢优先（M4.1 新发现，环境怪癖）
- **现象**：修改 `src/simulation/easyfly_gazebo_models/<name>/model.sdf` 后仿真行为不变——`~/.gazebo/models/<name>` 存在同名旧缓存时被优先解析（Gazebo 系统模型目录在 GAZEBO_MODEL_PATH 之前）。person_walking 静态化曾因此"静默失效"。
- **处理**：删除 `~/.gazebo/models/<name>` 缓存条目即可；自研模型建议不放入 ~/.gazebo/models。

---

## 五、历史踩坑已修复但值得复测的项（回归风险清单）

| 编号 | 历史问题 | 修复方式 | 复测建议 |
|------|---------|---------|---------|
| H1 | EKF 磁偏角致 local frame 旋转 90°（M6） | 删除 PX4_HOME_LAT/LON 自定义 | 换 home 坐标需求出现时重验 |
| H2 | 增量式 waypoint 控制正反馈发散（M6） | 改目标渐近式 setpoint | 大毛刺场景长时间飞行复测 |
| H3 | 桨叶遮挡 LiDAR（M6） | collision 半径 0.001 | 见 Q29，待更好方案 |
| H4 | RViz 配置 YAML 语法错误（M6 后） | 重写 perception.rviz | 每次手改 rviz 后用 yaml 校验 |
| H5 | gazebo_ros_init 必须 `-s` 加载（M0） | launch 已改 | 新建 world 时勿再写进 world 文件 |
| H6 | libRayPlugin.so 需显式链接（M0） | CMake find_library | 重装系统 gazebo 包后复测编译 |

---

## 六、修复优先级建议（阶段四开工前）

1. **第一批（控制安全，实机前必须）**：Q2（低电量 RTL）、Q6（空中 disarm）、Q3/Q4（取消逻辑）、Q5（超时）、Q8（解析崩溃）
2. **第二批（控制正确性）**：Q1（PID 启用或删除）、Q9（模式校验）、Q11/Q26（launch 化 + use_sim_time）、Q14/Q15（encoder mask）
3. **第三批（感知质量，接 TrackTarget 前做）**：Q19（ID 跳变）、Q20（时间同步）、Q25（类别过滤）
4. **随阶段四做**：Q27（launch 握手）、Q28（TF 降级）、Q29（桨叶碰撞）、Q23（far 加大）

---

## 七、P0 修复记录（2026-09-13 实施完成）

### 修复内容与实测结果

| 问题 | 修复方案 | 实测验证 |
|------|---------|---------|
| Q1 PID 死代码 | 移除 PID 结构与实例，hpp 注释明确架构定位（setpoint 生成 + PX4 OFFBOARD 内环） | 编译通过 |
| Q2 低电量无动作 | safety_check 一次性触发：中止任务 + cancel 子 action + 空中时请求 PX4 RTL | ✅ 端到端：注入 10% 电量 → 任务 abort → AUTO.RTL 成功 → PX4 返航降落 |
| Q3 Land 取消断裂 | 取消时先发布悬停 setpoint 恢复数据流，再切 OFFBOARD | ✅ 降落至 z=1.9 取消 → 恢复悬停 z=3.03 (OFFBOARD) |
| Q4 悬停目标 stale | 取消/超时后用**守卫反馈**刷新悬停点（`safe_axis`：与 ramp 偏差 <3m 才采信，防 M6 型 z=-10 毛刺） | ✅ 40m 航程 4s 时取消 → setpoint 冻结在取消点 → 稳定悬停于 x=13.6，未飞向目标 |
| Q5 无超时保护 | takeoff: 3×名义时间+10s；waypoint: 3×名义时间+15s；超时 abort + 就地悬停 | 逻辑随代码审查（正常飞行 deadline 远大于实际用时，不误触发） |
| Q6 空中 disarm | 超时仅 z<0.3（已落地）允许 disarm；空中只 abort 并交 PX4 AUTO.LAND 继续 | 逻辑审查 + 全流程降落正常（Landing detected → Disarmed by landing） |
| Q7 yaw 毛刺 | 起飞时锁存 yaw，全 程 setpoint 不取姿态反馈 | ✅ 起飞正常 |
| Q8 解析崩溃 | safe_stod + **全串消费校验**（`std::stod("2.5米")=2.5 不抛异常！`必须校验尾随字符）+ detached thread 顶层 try/catch | ✅ 坏文件 → abort + 进程存活（原版必崩） |
| Q9 模式不校验 | `wait_mode_engaged` 轮询 3s 确认 OFFBOARD；uav_ 加 mutex + 独立订阅回调组 | ✅ 起飞成功（修复前校验误判，见 N1） |
| Q10 取消不可中断 | 全部 `wait_for` 改 200ms 轮询（检查 cancel/emergency）；hover 可中断；子 goal handle 加锁管理可异步取消 | ✅ 取消响应 <2s；RTL 测试中 hover 步骤即时退出 |

### 实施中发现的新问题（已同步修复）

| 编号 | 问题 | 修复 |
|------|------|------|
| **N1 回调组饿死** | `/uav_state` 订阅与 action 回调同在默认 MutuallyExclusive 组：`handle_takeoff_accepted` 阻塞（call_arm/模式校验）期间状态订阅完全饿死，OFFBOARD 已切入仍读到永久 stale 的旧模式 → 校验误判失败 → 好起飞被 abort | 订阅移入独立 `state_cb_group_`（实测起飞即恢复正常） |
| **N2 PX4 RTL 模式名** | bridge `set_flight_mode` 用 `"RTL"`——这是 ArduPilot 模式名，**PX4 应为 `"AUTO.RTL"`**，导致 RTL 切换被 PX4 拒绝（success=0） | bridge 改为 AUTO.RTL（关联 Q18 模式映射家族问题） |
| **N3 反馈链延迟竞态** | 新增的"外部接管检测"（HOVER 中发现 RTL/AUTO.LAND 即复位）与取消降落竞态：切回 OFFBOARD 后模式反馈延迟 ~1s，窗口期误判接管 → setpoint 停发 → 取消降落失效 | 接管检测加 **1.5s 去抖**（模式持续 6/7 才判定） |

### 遗留观察项（非阻塞）

- RTL 返航时 PX4 报告 home 距离 ~519m（实际只飞出 10m）——SITL GPS home 与 Gazebo 位置的原点偏差，仿真环境怪癖，实机不适用；不影响 RTL 触发链路正确性；
- 无人机带 2m/s 惯性时取消航点，会过冲 ~1.4m 后拉回（PX4 内环物理特性，正常）；
- 控制链路回归全绿：起飞 ✓ 航点 ✓ 航点取消 ✓ 降落取消 ✓ 正常降落 ✓ 坏任务文件 ✓ 低电量 RTL ✓。

---

## 八、P1 修复记录（2026-09-13 实施完成）

| 问题 | 修复方案 | 实测验证 |
|------|---------|---------|
| Q11+Q26 launch 化 | 新建 `flight_control.launch.py` / `mission_fsm.launch.py`（use_sim_time 参数，默认 true）；`perception_sitl.launch.py` 集成两节点（10s 时拉起） | ✅ `ros2 param get` 两节点 use_sim_time=True；一键启动后节点表含 /flight_controller + /mission_fsm + 全部感知节点 |
| Q12 实测 dt | control_loop 记录上次时刻，`dt = clamp(实测, 0.5/rate, 2/rate)` | 随全流程回归（起飞/航点/降落正常） |
| Q14 encoder 掩码 | ANGULAR_RATE `type_mask: 0b10000111 → 0b10000000`（原值把 bit0-2 三个角速率忽略位全置 1，角速率指令被静默丢弃）；ATTITUDE 模式 `0b111` 确认正确；两种模式的位定义已写入注释 | 代码审查（该模式当前无使用者，为 E2 规划层接入扫雷） |
| Q15 模式语义 | `UAVCommand.msg` 注释明确 ATTITUDE_THRUST 是 ATTITUDE 的历史别名（姿态四元数+归一化推力 [0-1]），勿新增使用 | 消息注释 |
| Q16 完成去抖 | 双条件：① ramp 走完（水平 new_prog≥L 且 z 到位）② 连续 5 帧（0.25s）反馈在验收半径内 | ✅ 正常航点（6m）与短航点（0.71m）均正常 SUCCEEDED，去抖不卡完成路径 |
| Q17 RC 超时 | bridge 记录 last_rc_time_，publish_state 超时 1s 置 rc_connected=false | ✅ 仿真（无 RC）rc_connected=False，语义正确 |
| Q18 映射文档化 | cb_state 注释说明这是 easyfly 语义抽象（AUTO.LOITER≈POSCTL 等），下游仅依赖 3/6/7，精确模式用 flight_mode_name 字符串 | 注释完成 |

**Q13（UAVState 加 pose_stamp）按方案缓做**：当前时间不对齐误差量级（<5cm @2m/s）远小于其他误差源，阶段四做精确轨迹跟踪时一并处理。

回归全绿：新 launch 入口下 起飞 ✓ / 航点(远/近) ✓ / 降落 ✓ / use_sim_time ✓ / rc_connected 仿真语义 ✓ / perception_sitl 一键可飞 ✓。

---

## 九、感知类修复记录（2026-09-13 实施完成）

| 问题 | 修复方案 | 实测验证（75s 飞行: 起飞→10m→折返→降落） |
|------|---------|------|
| Q19 ID 跳变 | ① **双门限关联**：IoU≥0.15 **或** 中心距 < max(两框对角线)×1.5 才允许关联（代价仍 IoU 主导，匈牙利解质量不变）② KF 速度过程噪声 0.01→1.0（适配异步推理不规则帧间隔）③ iou_threshold 0.3→0.15、max_lost 30→45 | **unique ID 168→26（↓84%）**；剩余为自然更替（视野边缘进出、机身遮挡闪断） |
| Q20 时间同步 | 深度帧环形缓冲(10 帧)，按 tracks 时间戳选最近帧（\|Δt\|>200ms 跳过该帧） | /target_positions 3514 帧有效输出，链路正常 |
| Q23 深度截断 | SDF far 10→20m + 插件 max_depth + pixel_to_3d.yaml max_depth 19.5 | 最远 3D 报告距离 9.5→**19.45m** |
| Q25 类别过滤 | tracking.yaml `target_classes: [person, car, truck, bus, bicycle, motorcycle, fire hydrant]` | 飞行统计仅 truck/person/bus（场景实际目标），无杂物 track |

**未处理项及理由**：
- **Q21（机身遮挡下半视野）**：iris.stl 视觉 mesh 包络问题，实机不存在；M1 已尝试三种位姿，进一步动模型收益低风险高（相机再移将影响全部外参链），维持现状；
- **Q22（MID-360 平放 5m 盲区）**：物理 FOV 限制，仿真侧已用 2.5m 低空方案 workaround；实机部署倒装+重标外参（已列入实机检查单）；
- **Q24（livox 仿真无噪声）**：真实 Livox 噪声模型复杂（非重复扫描固有抖动+运动模糊+距离相关噪声），简单高斯噪声无法缩小仿真-实机鸿沟，反而可能误导调参；SLAM 鲁棒性以实机验收为准。

**遗留观察**：消防车在 truck/bus 类别间摇摆导致同目标关联断开（COCO 无 fire_truck 类）——检测层类别抖动，自定义模型阶段自然解决。

---

## 十、全项目复查修复记录（2026-09-13 第二轮）

对 P0/P1/感知修复后的全部代码做逻辑闭环复查，发现并修复 4 个缺陷：

| 缺陷 | 位置 | 问题 | 修复 | 验证 |
|------|------|------|------|------|
| **A 外部接管检测盲区** | flight_control control_loop | 接管检测仅在 HOVER 分支 — 低电量 RTL 若发生在**航点/起飞中**，节点卡在该状态直到 deadline 超时（误报 "waypoint timeout" + 期间无法接新 goal） | 检测上移为 TAKEOFF/WAYPOINT/HOVER 三态通用（LANDING 除外——那是我们自己切的 AUTO.LAND），触发时 abort 当前 goal + 状态复位 | ✅ 任务航点中注入低电量 → "外部模式接管(mode=6)" 即时中止，0 次超时误报 |
| **B 取消窗口子 goal 泄漏** | mission_fsm execute_step | 取消落在 "goal 已接受、future 未返回" 窗口（<1s）时，子 goal 不被取消，任务中止后飞机继续执行该步骤 | 三类步骤的 poll 中断路径补发 async_cancel_goal | 代码审查（窗口极窄，行为防御性） |
| **C goal 被拒后空指针异常** | mission_fsm takeoff/land 步骤 | goal 被 REJECT 时 handle 为空，`async_get_result(nullptr)` 抛晦涩异常 "Goal handle is not known to this client"（waypoint 步骤有判空，这两个漏了） | 补判空 + 明确错误日志（"flight_control 要求 NONE 状态才可起飞"） | ✅ 悬停状态发任务 → 干净报错非异常 |
| **D 降落后无法再次起飞** | flight_control takeoff 流程 | PX4 降落后停留在 OFFBOARD 模式，该模式 arm 要求 setpoint 流活跃（offboardCheck: data_is_recent）→ 永远拒绝。**此前所有测试只做单次解锁循环，从未暴露**。另发现：POSCTL 模式 arm 需遥控器（SITL 无 RC）、切 OFFBOARD 后立即 arm 会被拒（PX4 需先处理一个 setpoint 注册 offboard_control_mode）、EKF 收敛边缘也有拒绝窗口 | 重构为 **"先建流后解锁"**：发初始 setpoint → 切 OFFBOARD → 等 0.5s 流注册 → arm 重试 ×5（10s 窗口，覆盖 EKF 收敛）→ 模式校验 | ✅ 连续起降循环 ×2 成功（修复前第 2 循环必失败）；EKF 边缘拒绝自愈（第 2 次 arm 成功） |

**新发现的环境怪癖（非代码缺陷，记录在案）**：
- **SITL 磁力计退化**：连续 ≥3 次起降循环后 EKF 磁偏估计发散（"Attitude failure (roll)" + "Compass 0 fault" → failsafe）。SITL 理想磁力计的已知局限，实机有真实标定不受影响。连续多循环测试时重启仿真；
- **RTL 虚拟 home**：RTL 报告返回点 519m（SITL GPS home 苏黎世 vs Gazebo 原点偏差，M6 已记录）——RTL 仍会正常执行并降落，但耗时 ~2 分钟。仿真中验证 RTL 链路时耐心等待或缩短注入时机。

复查同时确认无误的关键点：匈牙利算法 `<=` 与双门限 cost=1.0 的语义自洽；URDF 与 SDF 的 mesh 位姿一致（同为原点无偏移）；`rclcpp::Time(0,0,clock_type)` 时钟类型安全；mission_fsm 终态判定顺序（cancel > emergency > success > fail）正确。

---

## 十一、SLAM 多实例僵尸问题（2026-09-13 排查记录）

**用户报告现象**：RViz 中 path 绿色轨迹乱画、点云和飞机（RobotModel）消失。

**根因**：`fastlio_mapping` 进程的可执行文件路径是 `install/fast_lio/lib/fast_lio/fastlio_mapping`——**不含 "easyfly" 前缀**，异常退出时常规 pkill 模式（`lib/easyfly`）匹配不到它。反复启停仿真后累积 **16 个僵尸实例**，新仿真启动后全部复活：16 个 SLAM 同时订阅 `/livox/lidar`、各自独立解算、轮流发布矛盾的 `/Odometry` 和 `/path`（实测单话题上 4 组位姿交替、数十万米量级疯狂值、309 次跳变/160s）。

**传导链**：多实例乱 Odometry → `map_odom_tf` 计算的 `map→odom` TF 每帧跳变 → RViz 中 Fixed Frame=map 的所有显示（点云/RobotModel/Marker）TF 查询在跳变间隙失败 → 显示项清空（"消失"）；`/path` 上 16 条不同轨迹轮流到达 → 视觉乱画。

**修复与防护**：
1. 新增 `easyfly_clean.sh` 一键清理脚本（覆盖 fastlio_mapping 等全部 11 类进程）；
2. test-guide.md 启动前清理必读 + 排查表新增该症状条目；
3. 检查方法：`ros2 node list | grep -c laser_mapping` 应恒为 1。

**干净环境验证**：单实例下完整飞行（起飞→10m→0→(10,5)），跳变 309→1（仅 SLAM 初始化），path 157 点范围与航线吻合、轨迹平滑。

**教训**：凡是 pkill 清理链，模式必须覆盖**所有**子进程的实际路径（按 `install/*/lib/*/` 逐包核对），不能想当然按项目前缀匹配。
