# EasyFly 开发执行记录（schedule-v4）

> 开始时间：2026-10-04 07:33（Asia/Shanghai）
> D0完成时间：2026-10-04 07:51（Asia/Shanghai）
> D1完成时间：2026-10-04 14:09（Asia/Shanghai）
> 计划依据：`plan-v3.md` D0、D1；起点 HEAD：`1860690`。
> 状态：D0、D1均已完成本批开发验收并通过最终只读评审（D1见第7节）；G9-G11复验继续暂停。
> 分工：主 agent 负责范围、协调器、监督、配置、契约、集成检查与记录；easyfly_coder 负责构建脚本及EGO/轨迹会话链限定实现；easyfly_reviewer 负责最终只读评审。

## 1. 目标与验收标准

| ID | 目标 | 验收标准 | 当前进度 |
|---|---|---|---|
| D0-01 | 全量/按层构建入口 | 显式只扫描 src；从真实包名选择层及依赖；支持 cwd 无关调用与 dry-run；非法输入失败 | 完成：脚本3项回归、四层实际发现及dry-run通过 |
| D0-02 | EGO flag_too_far 风险 | 提前退出路径无未初始化读取；保持失败关闭；针对性回归及相关包构建通过 | 完成：真实采样块回归、旧实现反证、5个CTest、单包构建通过 |
| D0-03 | 开发配置集合 | 基础、完整感知、导航、标签/降落开发配置可解析；有效参数可导出；未实现能力明确标记；实机模板禁止启动 | 完成：5个profile、安装CLI导出、配置/子launch离线验证、相关3包构建 |
| D0-04 | 共用安全参数一致性 | frame、点云预算、规划边界、轨迹超时等能跨包核对；错配有负向检查 | 完成：10项源默认契约检查；负向错配/类型测试通过 |
| D0-05 | 契约与第三方来源 | 覆盖生产者/消费者、clock、QoS、轨迹 ID/ACK、动作终态；来源/许可证/补丁入口明确，未知 commit 如实标记 | 完成：核心契约与第三方登记文档；明确未知来源和许可元数据差异 |
| D0-06 | 包成熟度登记 | 登记全部 67 包；区分实现、骨架、配置/资源与第三方；分别记录历史与本次验证 | 完成：67包逐项登记；29个明确TODO骨架；历史/本次证据分列 |

本轮检查限于配置展开、离线逻辑回归、相关包构建与只读评审。不进行 G9 长稳/冷启动循环，不进行 G10/G11，不将历史 G8 结果写成本轮动态结果。

## 2. 初始状态

- 功能基线为 `0724742`，交接提交为 `1860690`。
- 预存用户修改：`.codex/config.toml`、两个 agent 配置及 `codex_cli.sh`；`plan-v3.md` 为此前生成的未跟踪文件。本轮不还原这些内容。
- `build_all.bash` 未显式传入 `--base-paths src`；`build_layer.bash` 将 `c3_media` 等目录名当作包名，不能实现有效层级构建。
- EGO `flag_too_far` 在首次采样参数校验提前退出时可能尚未初始化。
- `easyfly_params` 当前仅安装 config 目录，尚无可使用的配置集合。
- 标签/降落检测、精准降落模块仍是骨架，开发配置不得将其伪装成已可启动的节点。

## 3. 进度记录

- 07:33：开始 D0；已分派 coder 限定任务；主 agent 整理配置加载与跨包一致性检查方案。
- 07:34 起：coder 完成全量/按层构建脚本与 EGO 最小修复，启动 ego_planner 单包构建；主 agent 实现开发 profile、导出工具和跨包核对。
- 07:38：首轮配置测试27项通过，launch测试因ROS默认日志目录不可写失败；复查后将离线测试日志放到独立临时目录，并修正Humble launch location求值方式，32项通过。
- 07:41 起：主 agent 构建 easyfly_params、easyfly_sim_launcher、easyfly_px4_sitl，3包成功；coder 的 ego_planner 构建在约7分31秒后退出0。
- 安装CLI冒烟发现新脚本执行位缺失，补齐后 `ros2 run easyfly_params config_tool` 实际导出成功，10项源码契约核对通过。
- reviewer 首轮独立评审无阻塞问题；独立重跑32项配置/launch、3项脚本及1项采样回归通过，提出整数类型与子launch展开两项非阻塞补强建议。
- 07:48：补齐上述两项：严格整数字段、四个profile的子launch最终参数离线检查；测试辅助求值适配后38项通过。新增两包CTest、既有仿真2项CTest和桥接3项时间契约回归通过。

## 4. 实际交付

### D0-01 / D0-02：coder 实现

- `build_all.bash` 显式 `--base-paths src`。
- `build_layer.bash` 从 `colcon list` 的真实包路径选择层内包，再由 `--packages-up-to` 计算依赖闭包；保留c/p/e/a和长名，新增dry-run，使用argv数组。
- 从 `/tmp` cwd 实测：通信11包、感知18包、执行10包、应用8包。这里是层内选择数量，不是包含依赖后的构建总量；第三方、公共接口、仿真和UI不在这些层内数量中。
- EGO将 `flag_too_far` 初始化为true，首次非法采样间隔提前break后明确拒绝；阈值和正常采样行为保持。
- 新增脚本回归及实际采样块编译/执行回归；EGO CMake注册后者。没有将真实源码替换成仅验证相似实现的独立算法。

### D0-03 / D0-04：主 agent 实现

- `easyfly_params` 新增安装的Python配置模块、`config_tool` CLI、冻结核对表及5个profile：base_sim、full_perception、navigation_dev、landing_dev、hardware_unverified。
- `easyfly_sim_launcher/profile.launch.py` 根据profile组合已有入口，隔离父launch通用配置；基础仿真支持headless，完整链显式透传原3.2m默认上界。
- landing_dev为preparation_only，不启动尚未实现的标签/精准降落模块；hardware_unverified可导出查看但在创建Include前拒绝启动。
- 配置导出覆盖profile元数据、受管launch输入及安全核对值，不声称导出全部运行时节点参数。
- 10项离线源默认值检查：semantic/filter/target/EGO四处odom、生产/消费两处200000点预算、EGO0.5m下界与3.2m上界、8s首帧宽限、0.5s断流常量。采用跨包核对路线，不重写已验收核心参数来源。
- 新增负向检查覆盖未知profile、字段类型/模式、未实现能力伪启用、跨包frame/预算/高度/超时错配、非有限值及整数契约伪浮点类型。
- 子launch离线检查实际EGO Node规范化参数与基础gzclient条件；不执行Node或PX4/Gazebo进程。

### D0-05 / D0-06：文档

- [配置说明](docs/development/d0-configurations.md)：入口、能力边界、覆盖规则与使用命令。
- [接口契约](docs/development/runtime-contracts.md)：生产者/消费者、frame、clock、QoS、轨迹身份/ACK与Action终态。
- [第三方来源](docs/development/third-party-provenance.md)：来源线索、版本、许可证证据、本地补丁入口；未知上游commit不猜测补全。
- [成熟度清单](docs/development/package-maturity.md)：67包逐项登记；实现/骨架/资源/接口分类；本次与历史验证分开。

## 5. 验证与评审

以下除脚本/纯采样回归外，执行前均source `/opt/ros/humble/setup.bash` 与本工作区 `install/setup.bash`。各项是针对性开发验证，不是完整G0-G8复验，也不是G9+。

| 检查 | 命令/范围 | 实际结果 |
|---|---|---|
| Shell语法 | `bash -n build_all.bash build_layer.bash` | 通过 |
| 构建脚本行为 | `python3 scripts/test_build_scripts.py` | 3项通过；非法输入/空集合、外部cwd、argv和构建范围 |
| 实际包发现 | 从/tmp运行绝对路径`build_layer.bash {c,p,e,a} --dry-run`，四个独立调用 | 11/18/10/8包选择成功；无飞行进程 |
| EGO采样回归 | `python3 src/third_party/planners/ego_planner/plan_manage/test/test_initial_sampling.py` | 1项通过；非法间隔/残留点集/合法缩步采样 |
| 原缺陷反证 | coder在内存中的Path.read_text mock里将初值还原成旧声明，执行同一回归；不修改工作树 | C++编译因maybe-uninitialized被拒绝，退出1；证明回归能捕获原缺陷 |
| 配置与launch行为 | `python3 -m pytest -q src/application/a1_sdk/easyfly_params/test/test_configuration.py src/application/a3_mission/easyfly_sim_launcher/test/test_profile_launch.py` | 最终38项通过（29配置+9launch） |
| 安装CLI | `ros2 run easyfly_params config_tool --profile navigation_dev --workspace /home/jia/easyfly_ws` | JSON实际导出，10项源码契约检查通过 |
| CLI启动参数发现 | `ROS_LOG_DIR=/tmp/easyfly-d0-showargs-roslog ros2 launch easyfly_sim_launcher profile.launch.py --show-args` | 5个profile可发现；未启动进程 |
| EGO相关CTest | `ctest --test-dir build/ego_planner --output-on-failure -R '^test_(initial_sampling\|trajectory_seed_safety\|waypoint_admission\|emergency_stop_gate\|swarm_bspline_validator)$'` | 5个CTest通过；初次未source环境缺依赖动态库，补齐环境后通过 |
| 配置CTest | `ctest --test-dir build/easyfly_params --output-on-failure -R '^test_configuration$'` | 通过 |
| 组合入口CTest | `ctest --test-dir build/easyfly_sim_launcher --output-on-failure -R '^test_profile_launch$'` | 通过 |
| 既有仿真静态回归 | `ctest --test-dir build/easyfly_px4_sitl --output-on-failure` | launch与模型物理/相机契约2项通过 |
| 既有桥接时间回归 | `ROS_LOG_DIR=/tmp/easyfly-d0-regression-roslog python3 src/communication/c2_protocol/easyfly_mavlink_bridge/test/test_mavlink_bridge_sim_time_contract.py` | 3项通过，包含既有组合入口的simtime契约 |
| 差异检查 | `git diff --check` | 通过；用户预存配置修改未还原 |

相关包构建：

```bash
colcon build --base-paths src --packages-select ego_planner \
  --symlink-install --cmake-args -DBUILD_TESTING=ON \
  --event-handlers console_direct+

colcon build --base-paths src \
  --packages-select easyfly_params easyfly_sim_launcher easyfly_px4_sitl \
  --symlink-install --cmake-args -DBUILD_TESTING=ON \
  --event-handlers console_direct+
```

- ego_planner：1包完成，退出0；固定日志 `log/build_2026-10-04_07-34-57/`，events.log含JobEnded rc=0；已无本轮flag_too_far警告，仍有已有max_coordinate未使用警告。
- 配置/组合入口/仿真：3包完成，退出0；固定日志 `log/build_2026-10-04_07-41-50/`。
- 原日志为Git忽略的生成物，清理后不能依赖它们仍存在；本文件保留命令、范围和结果摘要。没有宣称D0重新完整构建67包。

评审：easyfly_reviewer首轮及最终复核均无阻塞问题；两项非阻塞建议已实现并新增回归。reviewer独立重跑最终38项测试，实际核对config_tool执行权限与安装CLI的10项源码契约导出，确认D0满足计划验收标准。保留评审边界：子launch参数展开仍是离线证据，不等于运行中节点参数或动态飞行成功。

## 6. 最终结果与剩余项

D0六项实现及本轮开发验证已完成，最终只读复核无阻塞，签收为D0完成；本文件随D0代码及plan-v3一起提交。2026-10-04项目所有者随后授权开始D1，后续进度在本文件追加，G9-G11仍暂停。

明确剩余项：

- D1统一导航在下节完成本批开发验收；D2完整SDK/参数写入、D3正式任务引擎尚未实施。
- 标签/精准降落功能仍未实现，landing_dev只是现有传感器链开发入口。
- 第三方来源缺口、EGO部分TODO许可证和平台/包许可元数据差异只做了事实登记，没有伪造来源或擅改许可。
- 配置核对覆盖源默认值和受管入口；任意自定义launch/运行时覆盖不在保证范围内。
- 本轮不做全量lint清零、长期资源/重启测试、实际传感器联调或动态飞行；历史G8状态保留，G9-G11继续暂停。

## 7. D1：统一导航开发记录

D0已提交：`847dfbf feat(D0): establish development profiles and close baseline contracts`。未包含用户预存的`.codex`及`codex_cli.sh`修改，未push。

### 7.1 目标与用户决策

保留公开`/navigate`及NavigateTo字段；协调器支持配置选择`astar`、`ego`、`combined`，内部A*改为`/navigate_astar`。组合模式是2D全局路线加EGO局部轨迹，不声称完整3D全局规划。每次仅一条执行链，真实子动作终态与规划会话停止均确认后才能切换。

用户确认：RViz“2D Goal Pose”转发统一导航；FollowTrajectory、PositionCommand及B-spline接口没有外部使用者，可同步追加会话标识并重编译。新增字段不改动`/navigate`客户端协议。

后续确认：独立近障自动监督默认关闭、显式开启；查询与手动停止正常提供，EGO自身避障/急停不关闭。

| 子项 | 目标 | 当前进度 | 验收标准 |
|---|---|---|---|
| D1-01 | 公共入口与A*内部代理 | 完成：实现、组件验证与只读复核通过 | 唯一公开server；反馈/成功/失败/取消正确透传；迟到终态不提前释放控制权 |
| D1-02 | EGO受管会话 | 实现、真实节点及旧流隔离验证通过 | 先FollowTrajectory准入再触发规划；目标/轨迹/CMD/ACK会话一致；拒绝旧流 |
| D1-03 | 全局/局部组合与有限重规划 | 静态/动态真实节点软件闭环通过 | 有界子目标；地图/定位失效失败关闭；次数/时间预算；静态/动态障碍短场景 |
| D1-04 | 监督停止与RViz统一准入 | 查询/手动停止/自动失败恢复/RViz回归通过 | 不发布MAVROS setpoint；只取消所属导航；RViz不直接触发EGO |
| D1-05 | 开发验证与只读评审 | 完成：相关构建、定向回归与最终只读评审通过 | 相关包构建、正负向组件回归、短程联调；不恢复G9+ |

主agent负责协调器/组合路线/监督模块/跟踪取消边界/记录，实现agent负责公共接口与EGO→traj_server→flight_control会话链，由只读reviewer独立复核。验收结论见最终记录，未完成项不得按已有代码计为通过。

### 7.2 实现与验证过程（持续更新）

- 三策略协调器已实现；有限输入/准入/总任务/取消预算，公共终态与底层所有权释放分离；迟到START必须先响应、再STOP，不能按超时假定规划没有启动。
- 组合模式保守处理未知格、轴对齐地图、最多256局部目标和3次重规划；换段前检查新鲜有效反馈速度≤0.3m/s。
- 监督包从骨架变成真实查询/停止节点，只使用带Goal UUID的停止请求，无MAVROS或setpoint发布；`/navigation/goal_id`心跳关联监督与当前导航，旧请求不会误停新任务。
- navigation_dev配置默认combined，其他既有完整链默认astar。新增 `navigation_strategy` 透传；RViz仅由协调器转发，EGO正常启动禁用直接入口。
- 公共会话接口/轨迹链追加字段，受管EGO速度限保守换算，保留原急停ACK和时间保护。实现agent发现并修复STOP后的idle时间基线导致新流误判ROS前跳，以及depth1通知漏STOP时新START无法接续的问题。
- 首次主agent构建因StopNavigation生成库未完成而失败；待接口安装后监督包构建通过，协调器因Humble ServerGoalHandle没有SharedPtr别名编译失败，改std::shared_ptr后构建通过。这些失败不记作验收通过。
- 首轮组件检查：A*代理、迟到START、5个已有规划纯逻辑CTest及监督检查通过；局部mock组7项中5失败，发现测试动态障碍落在首目标之后、首个子动作一直等待，及逐case进程清理不完整风险。已调整障碍落点、进程组清理，正在重跑。
- D0配置/嵌套launch38项回归再次通过；既有perception launch静态契约通过；git diff --check通过。
- 局部mock组修正后通过，追加所属UUID停止与急停事件用例；迟到START期间拒绝新任务，直到真实START响应、STOP成功及子动作终态全部确认。
- 只读首轮评审发现4项阻塞：急停未传播、A*预算耗尽后迟到成功可能误报成功、受管flight_type=2仍访问预设航点、自动监督首次失败后永久锁存。分别新增会话急停事件、正常完成标识、受管模式强制MANUAL_TARGET、成功后锁存及失败退避重试；均增加回归。
- 第一轮真实软件plant因初始已armed导致Takeoff拒绝，修正测试初始状态与模拟解锁服务。第二轮暴露EGO自由终点约0.16m偏差超出0.1m到达半径，以及过密合成点云/近距离突发障碍触发真实急停。未放宽半径、未关闭急停、未将失败算通过。
- 为受管模式固定实际局部终点的位置/速度/零加速度，rebound固定尾三控制点、refine重参数化后重新施加约束，保留碰撞检查与最终三维速度范数检查；原非受管模式保持旧行为。同步重编bspline_opt和EGO，避免类布局变化导致混用旧ABI。
- 软件plant调整为41点可信柱体表面、5Hz点云/栅格、新障碍出现在2.5m处；既有EGO膨胀/急停/点云有效性保护不变。仿真目标为(5,0,1.5)，速度请求1m/s；动态场景飞到x>0.25m后同时更新真实点云与栅格，不使用预测输入。
- 14:02：目标跟踪恢复取消移除全量cancel-all，未知句柄保持故障所有权，仅取消所属子Goal；单包构建与2项已有CTest通过。本项不声称完成目标跟踪线程/任务引擎全面重构。
- 14:03：真实EGO+traj_server+flight_control+coordinator静态/动态两场景全部通过（61.34s），含到达、动态换会话、取消停流、点云失效后公开急停失败；开始最终只读复核。
- 14:08：最终reviewer复核未发现阻塞，上轮4项关闭；补充RTL/LAND接管与下游断流失败传播组件回归，局部组最终11用例通过；38项配置回归通过，正常导航入口show-args可发现3策略；测试所属进程无遗留。

### 7.3 实际交付与边界

1. `easyfly_global_planner`新增协调器；原A*改用私有Action，公开协议不变。导航进程每次仅持有一个上下文，子动作取消只按所属句柄；无法确认底层停止时公开失败但继续保留故障锁。A*工作线程可在析构时停止/join，不新增detached线程。
2. 新增NavigationSession消息、SetNavigationSession与StopNavigation服务；FollowTrajectory/Bspline/TrajectoryAck/PositionCommand同步追加会话字段。正常受管链先锁定飞控准入，再启动规划；轨迹服务器匹配STOP停流，飞控在ID水位更新之前过滤异会话，急停ACK仍须通过既有恢复门。
3. combined为2D A*到有限局部目标，未知占据保守处理；当前走廊被新栅格阻断时精确取消+STOP后再规划。总预算/取消预算与重规划次数有限；不存在失败后无避障直飞降级。
4. 监督包提供障碍净距/约束有效性查询和带Goal UUID的停止；旧异步请求不影响新任务。auto_stop默认关闭、成功后锁存、失败1s退避重试。不新增setpoint输出，不把监督停止包装成通用飞行急停。
5. RViz入口转发公开导航；navigation_dev默认combined，其余既有完整链默认astar；开发接口、契约、第三方补丁和包成熟度文档同步更新。67包总数不变，明确TODO骨架从29减为28，不能据此计算功能完成百分比。

### 7.4 定向验证记录

以下均为本次D1开发验证；ROS命令执行前source Humble及工作区安装环境。不同ROS测试使用独立domain，逐测试按所属进程组清理。

| 检查 | 命令/范围 | 实际结果 |
|---|---|---|
| 协调器纯逻辑与ROS代理 | `ctest --test-dir build/easyfly_global_planner --output-on-failure -R '^test_(coordinator\|local_coordinator\|late_session\|astar_deadline\|astar\|map_validity\|waypoint_lifecycle\|goal_validation\|segment_acceptance)$'` | 9项通过（最终组16.02s）；随后扩展的局部组11用例独立通过（9.53s），含ego/combined/动态栅格、拒绝/无效输入/取消、owned-stop、异会话与匹配急停、RTL/LAND接管及下游断流失败传播；迟到START和超时后迟到A*成功各有专门回归 |
| 真实节点软件闭环 | `ctest --test-dir build/easyfly_global_planner --output-on-failure -R '^test_navigation_chain$'` | 1个CTest、静态/动态2用例通过，61.34s；真实4类节点，合成状态/点云/地图和简化位置响应 |
| 闭环断言 | 上述软件plant | 最终水平误差<0.15m；绕障横向偏移>0.8m；柱体表面最小间距>0.8m；至少2个有效局部会话，ACK会话关联；PositionCommand三维速度≤1.001m/s；取消后无TRAJECTORY命令；点云失效后ABORTED/`planner_emergency_stop` |
| EGO回归 | `ctest --test-dir build/ego_planner --output-on-failure -R '^test_(initial_sampling\|trajectory_seed_safety\|waypoint_admission\|emergency_stop_gate\|swarm_bspline_validator\|navigation_session_ros\|managed_navigation_fault_ros)$'` | 7项通过（9.52s）；真实受管flight_type=2启动/执行/急停/STOP；实际轨迹会话隔离；Bspline校验15用例含真实终点位置/速度/零加速度 |
| 飞控回归 | `ctest --test-dir build/easyfly_flight_control --output-on-failure -R '^test_(trajectory_startup_timeout\|navigation_session)$'` | 2项通过；调用真实PositionCommand回调验证旧/空/过长会话不推进水位，匹配新流准入；保留首帧及流断保护 |
| 监督ROS回归 | `ctest --test-dir build/easyfly_obstacle_avoidance --output-on-failure -R '^test_supervisor$'` | 1个CTest、2用例通过；AABB净距/有效空与无效观测/UUID手动停止，以及auto_stop首次失败后的有界重试与成功锁存 |
| 跟踪边界回归 | `ctest --test-dir build/easyfly_target_tracking --output-on-failure -R '^test_(waypoint_lifecycle\|target_frame)$'` | 2项通过；源码精确取消复核，不声称真实跟踪动态场景本次复验 |
| 配置与嵌套入口 | D0相同38项pytest及配置/入口CTest | 38项通过；新增navigation_strategy透传及navigation_dev默认combined，既有安全默认值一致 |
| 导航启动参数发现 | `ROS_LOG_DIR=/tmp/easyfly_d1_final_showargs ros2 launch easyfly_global_planner navigate.launch.py --show-args` | 通过；发现use_sim_time及astar/ego/combined，不启动飞行进程 |
| 既有仿真与时钟契约 | easyfly_px4_sitl的2项CTest；mavlink_bridge sim-time脚本3项 | 通过；属于静态/离线回归，不是启动PX4/Gazebo |
| 差异与清理 | `git diff --check`、测试所属进程检查 | 通过；保留用户预存agent配置修改，测试进程按自身组清理 |

成功构建证据（生成日志受Git忽略，以下保存实际范围；不宣称D1全量67包构建）：

- 公共接口/相关依赖：`log/build_2026-10-04_08-25-53/`中的easyfly_msgs、quadrotor_msgs、traj_utils等成功；同轮flight_control失败、EGO被中断，不记作成功。随后`08-27-25`中flight_control、EGO、local_planner均成功。
- 导航/监督最终源码：`log/build_2026-10-04_09-07-37/`，两包rc0。
- 配置/仿真/旧示例消费者：`log/build_2026-10-04_08-51-57/`，easyfly_params、easyfly_sim_launcher、easyfly_px4_sitl、ego_to_mavros四包rc0；旧直连桥只重编，不进入正常启动、不执行。
- 固定终点最终同步构建：`CMAKE_BUILD_PARALLEL_LEVEL=2 colcon build --base-paths src --packages-select bspline_opt ego_planner --parallel-workers 1 --event-handlers console_cohesion+`，`log/build_2026-10-04_13-52-46/`，两包rc0，8min12s。
- 跟踪边界最终构建：`colcon build --base-paths src --packages-select easyfly_target_tracking --symlink-install --cmake-args -DBUILD_TESTING=ON`，`log/build_2026-10-04_14-01-49/`，rc0。

### 7.5 评审与验收结论

首轮4项阻塞均已修改并有针对性回归。最终easyfly_reviewer独立只读核对源码、测试和已有日志，执行git diff --check通过；确认固定终点公式、优化变量边界、碰撞/速度检查及tracking精确取消无阻塞，未改文件、未启动ROS。主agent真实软件plant与补充回归已全部通过，按plan-v3第6节签收D1本批开发范围。

验收结果：D1-01至D1-05完成；现有公开NavigateTo协议保持兼容，三策略可配置，组合短场景完成，取消/规划拒绝/无效输入/旧流/接管/急停均不误报到达，单执行链与故障所有权约束通过本轮验证。

明确边界及下一步：

- 没有重新开展G9长稳/冷启动或G10/G11；软件plant不是PX4/Gazebo SITL，不验证真实感知、动力学、外部定位注入或实机安全阈值。动态场景为新障碍出现后的重规划，不是完整动态运动预测避障。
- 不宣称全量67包重新构建、全量lint清零或全部外部DDS故障场景已验证。受管消息类型已变化，部署时必须同步重编工作区，不能混用旧接口库；独立自动监督默认关闭。
- D1修改当前留在工作树，尚未git提交或push；D0提交仍为847dfbf。预存用户agent配置修改保持原样。
- 后续可按计划进入D2 SDK/参数与平台接口；本轮未开始D2，也未把后续统一悬停、完整SDK/任务引擎计为已交付。

### 7.6 D1 独立验收（2026-10-04，ZCode 受权执行）

验收基线：工作树未提交的 D1 改动（HEAD=847dfbf/D0 + D1 工作树），install/ 为当日最新构建（关键源码 mtime 核对全部 FRESH）；ROS 测试在独立 domain 执行，与开发记录一致。

按 §7.4 清单逐项独立复跑，全部通过：

| 检查 | 结果 |
|---|---|
| 协调器纯逻辑+ROS 代理 9 项 | ✅ 9/9（coordinator/local_coordinator/late_session/astar_deadline/astar/map_validity/waypoint_lifecycle/goal_validation/segment_acceptance） |
| 真实节点软件闭环 | ✅ test_navigation_chain Passed 55.8s（静态/动态 2 用例） |
| EGO 回归 7 项 | ✅ 7/7（含 navigation_session_ros/managed_navigation_fault_ros 受管会话） |
| 飞控回归 2 项 | ✅ 2/2（trajectory_startup_timeout/navigation_session） |
| 监督 ROS 回归 | ✅ test_supervisor Passed |
| 跟踪边界回归 2 项 | ✅ 2/2 |
| 配置 pytest | ✅ 38/38（configuration + profile_launch） |
| navigate --show-args | ✅ 发现 use_sim_time + navigation_strategy(astar/ego/combined, 默认 astar)，不启动飞行进程 |
| px4_sitl 2 项 + bridge sim-time 脚本（内部 3 用例） | ✅ 全过 |
| git diff --check / 残留进程 | ✅ 通过 / 0 残留 |

独立抽检（超出文档清单的复核）：
1. **监督包无 setpoint/mavros 发布**（D1-04 安全声明）：源码级核验——`obstacle_supervisor_node.cpp` 仅有两个发布器（`/avoidance/constraints_valid`、`/avoidance/near_obstacle`，均为 Bool），全文无 setpoint/mavros 引用 ✅；
2. **策略默认值**：`load_profile` 实测 navigation_dev→combined、full_perception→astar、base_sim→未设置（不启动导航）✅；perception_sitl 入口默认 astar ✅；
3. 接口安装就位：NavigateTo/NavigationSession/SetNavigationSession/StopNavigation 均在 install 的 action/msg/srv ✅。

验收结论：**D1-01~D1-05 按本批开发范围验收通过**。证据与开发记录（§7.2-7.5）一致，未发现声明与实际的偏差。边界确认：本验收为组件/软件闭环级（与 D1 声明范围一致），不含 G9+ 长稳与实机；D1 改动截至本次验收**尚未提交**。
