# EasyFly 开发执行记录（schedule-v4）

> 开始时间：2026-10-04 07:33（Asia/Shanghai）
> D0完成时间：2026-10-04 07:51（Asia/Shanghai）
> D1完成时间：2026-10-04 14:09（Asia/Shanghai）
> D2完成时间：2026-10-04 15:20（Asia/Shanghai）
> D3本批功能验收完成时间：2026-10-04 20:15（Asia/Shanghai）；lint欠账另列。
> 计划依据：`plan-v3.md` D0–D3；起点 HEAD：`1860690`。
> 状态：D0–D3本批功能开发范围完成；D2已提交00d12b8，D3尚未提交；任务服务4项lint欠账保留，非全部注册检查通过；G9-G11复验继续暂停。
> 分工：主 agent 负责范围、协调器、监督、配置/服务、契约、集成检查与记录；easyfly_coder 负责构建脚本、EGO/轨迹会话链及SDK限定实现；easyfly_reviewer 负责最终只读评审。

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
- D1于随后用户授权提交为`dfd6859 feat(D1): unify navigation ownership and managed trajectory sessions`，未push；D0提交为847dfbf。预存用户agent配置修改保持原样。
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

## 8. D2：SDK、参数与平台接口

项目所有者于2026-10-04授权提交D1并开始D2。D1已提交为`dfd6859`，未push；上述独立验收是提交前的历史记录，保留原文。主agent负责参数与A2服务、公共接口、集成检查及记录；easyfly_coder负责C++SDK及Python绑定；easyfly_reviewer只读复核。不恢复G9+。

### 8.1 目标、用户决策与验收标准

用户确认两项边界：任务服务仅管理现有格式的目录校验、列表、执行、查询和取消，正式版本化YAML/搜索/复杂编排留到D3；参数只开放新增服务明确支持的动态白名单，飞行边界、坐标、设备和其他节点参数只读或重启生效。

| ID | 目标 | 当前进度 | 验收标准 |
|---|---|---|---|
| D2-01 | C++异步SDK | 完成：6项组件回归、退出竞态修复与评审通过 | 状态与7类已实现Action客户端；准入、反馈、真实结果和取消分开；executor/析构所有权明确；无setpoint旁路 |
| D2-02 | 类型化参数服务 | 完成：ROS参数及QueryParams回归通过 | 复用D0配置版本/启动加载/导出；明确动态白名单；非法更新不改变原值；QueryParams空值歧义明确 |
| D2-03 | 感知查询与能力 | 完成：真实ROS查询与负向回归通过 | 含源时间和有效性；区分有效空、未就绪、过期、无效和unsupported |
| D2-04 | 任务服务 | 完成：7类后端场景、预校验与安装入口通过 | 目录列表/完整预校验/执行/UUID查询取消；只调用既有执行器，不增加飞行状态机或任意Python执行 |
| D2-05 | Python最小绑定 | 完成：7项回归及3次重复通过，同一C++实现连接真实导航链 | 状态/起降/导航/任务/取消；GIL与对象寿命安全；可运行示例 |
| D2-06 | 开发验证及评审 | 完成：相关构建、组件、最终3场景软件闭环及补充只读评审通过 | 成功/拒绝/失败/取消与迟到响应回归；相关构建；最终独立只读评审；实际结果如实记录 |

### 8.2 实际交付

1. `easyfly_core`由骨架变为C++17共享库，导出`easyfly_core::easyfly_core`；自有独立Context/Node/executor，不接管调用者节点。7个异步动作客户端与状态订阅；Operation分离准入、反馈、真实终态、本地超时和取消响应，SUCCEEDED但success=false也为失败。默认32个未决槽，close不按超时释放远端所有权；仅精确取消所属Goal，包括迟到准入。
2. `easyfly_pybind`绑定同一SDK，不另写飞行状态机；Python只轮询/等待，wait/close释放GIL。C++和Python安装示例默认只查询，运动必须显式选择；SDK的running不等于后端ready。状态分别暴露源时钟/steady接收新鲜度和原始有效位，支持显式use_sim_time。
3. `easyfly_params`增加标准ROS类型化参数服务、受约束QueryParams兼容入口与有效配置JSON导出。动态参数仅operator_note（UTF-8≤512字节）和export_pretty（bool）；空param_value读，JSON编码`""`写实际空字符串。非法/未知/只读/类型错配与原子更新失败不改变原值。
4. `easyfly_perception_srvs`实现目标/障碍查询、源时间与能力列表，VALID空数组保留header；未收到、旧数据、几何/坐标/时间非法和unsupported明确区分。动态max_age限0.05–10s；range>0要求新鲜有效UAV位姿，按中心距离过滤，不混称监督AABB净距。标签/精准降落仍unsupported。
5. `easyfly_mission_srvs`提供list/validate/start/query/cancel；basename/canonical目录边界、名称和真实文件后缀校验、256个目录项及64KiB文件上限。服务与原mission_fsm共享完整旧格式校验，非法后续步骤不先执行前面步骤。执行只发送0600私有不可变快照给既有`/execute_mission`，使用门面ID绑定真实Goal UUID，取消ACK不等于终态，未确认时拒绝新执行；保存最近32项终态记录。正式YAML/search明确unsupported。
6. 三项新增srv类型GetPerception/GetCapabilities/ManageMission；不改D1已有Action/轨迹布局。平台服务launch默认不启动任务执行器、不发运动请求；仿真profile接入3服务且不重复FSM。hardware_unverified在可选执行器Include之前拒绝启动。成熟度表更新：总包数67不变，明确骨架从28降为24，不据包数推算整个平台完成百分比。

接口、示例、白名单及限制见[docs/development/d2-platform.md](docs/development/d2-platform.md)。

### 8.3 过程与失败记录

- 14:38起：主agent新增3服务类型并成功构建，SDK实现与服务实现按限定文件分工推进。
- SDK首轮Python绑定缺少Python Development配置，测试mock的Context.shutdown调用不兼容Humble；修正后相关构建通过。Python反馈首轮因单帧volatile发现窗口失败，mock改为执行期间持续反馈，未删除断言。被中断/失败的构建不记作成功。
- 参数、感知、任务门面和共享旧格式预校验通过组件检查；配置/嵌套launch38项保持通过。任务目录原文在准入后修改，后端仍读取原快照；非法后续步骤拒绝时mock起飞Goal计数为0。
- 安装入口冒烟首次list为空，原因是`--symlink-install`任务文件真实父目录不在安装目录。默认目录改由可信包内示例的canonical父目录定位；显式目录的越界symlink仍拒绝，修正后安装入口通过。
- SDK与真实coordinator/EGO/traj_server/flight_control软件plant首次连接通过；原静态/动态与新SDK场景最终3用例通过（80.62s）。输入仍为合成状态/点云/栅格及简化响应，不是PX4/Gazebo。
- 安装只查询示例暴露空闲SDK快速退出的DDS清理异常；修复SDK析构及Python上下文管理器，加入with/del/隐式退出3种独立进程回归，C++5/Python6及两个安装示例随后通过。
- 两次coder最后构建在TimerEvent处挂起并中断（退出130），不记成功；主agent全权限串行重编SDK两包于15:08完成rc0。
- reviewer发现目录上限只累计可选任务、垃圾文件仍可无限遍历；改为累计所有目录项，在257项立即失败；实际257垃圾项回归通过。另补alias.txt→valid.mission名称后缀拒绝，任务组件与安装入口再次通过。
- reviewer首轮最终复核无阻塞，但建议独立进程覆盖迟到准入销毁；新增第7个Python用例实际发现“close(0)→del client→收到真实取消终态→立即退出”的崩溃。coder复现SIGSEGV；主agent全权限重跑复现SIGABRT和DDS析构错误，确认非权限问题，D2暂不签收，正在修复真实终态通知与运行时清理屏障之间的窗口。
- 15:18：修复完成，Context实际释放后才发布stopped；已关闭且无其他未决任务时，最后Operation.wait在同一原预算内等待DDS清理，超时不改真实结果、不额外取消。主agent串行SDK重编rc0，C++6项通过2.56s、Python7项通过5.18s；随后Python全组连续3次通过（4.31/4.36/4.47s）。coder第三次挂起构建中断130仍不记成功。
- 15:20：补充reviewer只读确认清理屏障/锁顺序/超时语义无阻塞；修复后的3场景导航链再次通过80.02s，两个已安装只查询示例退出0；定向进程检查无所属ROS/build/test遗留。D2本批开发验收完成。

### 8.4 已执行验证

ROS命令均先source Humble及工作区安装环境；测试按独立domain隔离并清理所属进程。以下是针对性开发检查，未执行全量lint或全量67包重建。

| 检查 | 命令/范围 | 实际结果 |
|---|---|---|
| C++ SDK | `ctest --test-dir build/easyfly_core --output-on-failure -R '^test_sdk$'` | 最终6项通过2.56s；含7实际mock动作入口、成功/假成功/拒绝/失败/unavailable/unsupported、wait非取消、取消ACK非终态、容量、迟到准入、状态冻结和清理屏障 |
| Python SDK | `ctest --test-dir build/easyfly_pybind --output-on-failure -R '^test_sdk_python$'` | 最终7项通过5.18s；3种空闲subprocess及迟到取消终态后立即退出均通过；同命令追加`--repeat until-fail:3`连续3次通过13.14s |
| SDK安装示例 | `ROS_DOMAIN_ID=98 ros2 run {easyfly_core,easyfly_pybind} sdk_state_example`（分别运行） | C++/Python默认只查询均退出0，后端不在时明确not received/ready=false；没有发运动请求 |
| 参数 | `ctest --test-dir build/easyfly_params --output-on-failure -R '^test_(configuration\|runtime)$'` | 2个CTest通过0.72s；真实类型化/兼容服务及原子拒绝保值、配置导出 |
| 感知 | `ctest --test-dir build/easyfly_perception_srvs --output-on-failure -R '^test_services$'` | 通过1.03s；有效空/缺失/旧源时间/非法条目/范围原点/能力与参数拒绝 |
| 旧任务完整预校验 | `ctest --test-dir build/easyfly_mission_fsm --output-on-failure -R '^test_(legacy_mission\|prevalidation)$'` | 2个CTest通过1.32s；3项纯校验与13类负输入、超文件/步数；真实FSM非法后步骤无提前起飞、合法hover成功 |
| 任务门面 | `ctest --test-dir build/easyfly_mission_srvs --output-on-failure -R '^test_services$'` | 7场景通过6.69s；成功/失败/拒绝/取消/迟到准入/无后端/取消ACK延迟终态；目录上限、遍历/软链接、非YAML、快照、所属ID与busy保锁 |
| 平台启动 | 同包`-R '^test_(launch\|platform_smoke)$'` | 离线launch通过0.29s；实际安装入口3服务冒烟通过1.09s；无执行器/感知数据时正确not_ready；目录与导出可读，无自动运动 |
| 配置/嵌套入口 | D0相同两文件pytest | 38项通过0.19s；已有profile安全默认值及平台接入 |
| 真实软件导航链 | `ctest --test-dir build/easyfly_global_planner --output-on-failure -R '^test_navigation_chain$'` | 修复后最终3用例通过80.02s（此前80.62s）：原静态/动态与Python绑定→同一C++SDK→真实统一导航链；到达/绕障/速度/取消停流/点云失效急停均断言 |
| 差异与进程 | `git diff --check`及定向进程检查 | 通过；无本次所属测试/服务/导航/构建进程遗留，用户预存agent配置未还原 |

成功构建证据：

- 公共接口：`log/build_2026-10-04_14-38-46/`，easyfly_msgs rc0，15.06s。
- 参数/感知/FSM/任务服务：`14-45-23`及`14-49-55`四包rc0；共享最终校验与任务门面同步构建`14-59-53`两包rc0。
- 平台接入/仿真入口：`log/build_2026-10-04_14-54-06/`，mission_srvs及sim_launcher两包rc0；默认目录修复`15-05-12`任务包rc0。
- SDK：`CMAKE_BUILD_PARALLEL_LEVEL=2 colcon build --base-paths src --packages-select easyfly_core easyfly_pybind --parallel-workers 1 --symlink-install --cmake-args -DBUILD_TESTING=ON --event-handlers console_cohesion+`，`log/build_2026-10-04_15-08-02/`两包rc0，4.33s；退出竞态最终修复同命令`log/build_2026-10-04_15-17-50/`两包rc0，16.6s，随后6/7项及重复回归通过。
- 目录上限修复`log/build_2026-10-04_15-10-00/`任务包rc0；名称后缀最终修复`log/build_2026-10-04_15-13-29/`单包串行构建rc0（4.34s），任务测试与入口再次通过。

生成日志受Git忽略；本文件保存命令/范围/结果，不把中断、失败或旧版本结果当成最终通过。

### 8.5 评审、验收与剩余边界

easyfly_reviewer只读核对SDK所有权/迟到取消/GIL/状态时间、参数原子拒绝、感知状态、共享校验/快照/终态保锁/32项历史以及无自动运动launch；独立git diff --check通过。目录遍历发现已关闭；补充迟到终态subprocess实际发现SDK退出清理问题，修复后新增回归通过，reviewer再次核对锁顺序、强引用寿命、Context清理屏障和同预算等待，未发现阻塞；直接核对最终C++6/Python7日志，未修改文件或自行启动ROS。

验收结论：按plan-v3第7节及用户确认边界，D2-01至D2-06本批开发范围完成。C++/Python示例可运行，异步请求/真实终态/取消区分明确，非法参数保值，感知查询有效性明确，旧任务完整预校验与精确管理通过，SDK真实导航链联调通过。D2修改留在工作树，未自动开始D3。

本批新增SDK/服务均不发布setpoint或绕过执行层。进程退出不能保证外部服务器停止；丢失后端且永远无响应时仍保留未决SDK运行时。任务服务与执行器须共享可读取的文件系统，当前无跨主机快照传输。未确认终态的快照可能留在/tmp，不能据删除文件推断任务已停。

D3正式YAML/搜索/复杂任务引擎及后续标签/精准降落、平台UI尚未开始。未重新开展G9–G11、PX4/Gazebo SITL或实机验证，不宣称自动监督阈值已实机验证。D2目前未提交；用户预存`.codex`和`codex_cli.sh`修改保留，未push。

## 9. D3：任务引擎、搜索与示例（本批功能验收完成）

D2按项目所有者授权提交为`00d12b8 feat(D2): add asynchronous SDK and constrained platform services`，未push；预存agent配置及用户删除codex_cli.sh未纳入提交。D2上节未提交/未开始D3是其验收时点状态，本节为后续更新。

用户确认：第一版严格顺序、失败即终止，不自动追加返航/降落，分支与重试后续加入；搜索条带间距由启动参数提供，面积为已完成扫描条带几何覆盖估计、不是传感器实际探测覆盖；限时跟随到时后精确取消，真CANCELED作为该步骤正常完成，取消失败/终态未决保锁。

| ID | 目标 | 当前进度 | 验收标准 |
|---|---|---|---|
| D3-01 | 正式schema_version=1 YAML与旧格式兼容 | 完成：共享解析库、离线CLI、旧格式兼容与负向检查 | 全文离线校验；单位/frame/字段/范围/预算/能力可校验；未知及非法后步骤整份拒绝 |
| D3-02 | 七类顺序任务及子动作所有权 | 完成：同一SDK、13任务场景、跨层精确UUID排空 | takeoff/hover/waypoint/navigate/track/search/land；反馈真实步骤；取消/超时/失败/接管等待真实子终态；未决保锁 |
| D3-03 | SearchArea弓字覆盖 | 完成：几何检查与8真实ROS搜索场景 | 统一navigate；可飞范围/间距/条带面积明确；取消传播；未支持模式拒绝；新鲜有效稳定ID去重 |
| D3-04 | 模板与SDK示例/任务门面接入 | 完成：4模板、安装C++/Python示例与3真实任务链场景 | 四类模板与C++/Python取消示例可通过正式平台接口；默认只校验、不自动运动 |
| D3-05 | 开发构建、组件/短联调、只读评审 | 本批功能验收通过；4项任务服务lint欠账明确保留 | 正负向校验与动作回归、示例和实际接口联调；如实记录失败及验收边界；G9+仍暂停 |

### 9.1 实现与接口结果

1. 正式格式使用现有 yaml-cpp 依赖，单文档、schema_version=1、odom/m/rad/s、abort策略；1–256步、64KiB、每步有界预算且正式YAML总预算≤7200s。未知/重复字段、单位/frame/范围错误、非有限值和非法后续步骤整份拒绝。旧扁平任务按内容兼容，私有无后缀快照也兼容；不宣称JSON支持。mission_validate默认不初始化ROS、不发送Goal。
2. mission_fsm重构为受管线程＋同一C++ SDK，支持7类严格顺序步骤。全文准入校验及所有所需后端有界发现先于首个运动请求；运行时定位/电池数值、新鲜度、接管与期限失败关闭。限时跟随按用户确认的真实CANCELED语义完成，取消拒绝/迟到终态保锁。hover仍为等待并沿用已有保持，不发布新setpoint；保留原低电量保护。
3. /search_area复用统一导航；只读启动间距、矩形完整边界、最多256条带。真实到达/低速后计整条带面积，进场/转移不计；取消返回已完成部分。对新鲜有效区域内稳定非负ID去重，有界4096身份/每帧10000条。面积为几何估计，不是传感器实际探测覆盖。
4. 为解决公开失败早于内层停止的问题，新增GetActionOwnership、/navigation/ownership、/search/ownership、/mission/ownership。每层精确UUID绑定，只有匹配RELEASED解锁；UNKNOWN/失联/错误回显保锁，最近128已释放历史有界保存。SDK新增Search客户端、goal_id、action_terminal_received与受管查询选项；生产任务链强制require_managed_ownership=true。weak ownership client引用避免DDS清理后资源残留。公开Action终态、递归排空与SDK清理分别表达，不能相互替代。
5. 任务门面接入共享正式/旧解析器与受管排空；ManageMission新增execution_pending。公开结果收到但下层未排空时，保留活动槽及0600私有快照，拒绝新任务。迟到cancel拒绝不覆盖真实结果。目录安全策略保持，打开文件使用有界非阻塞常规文件校验，拒绝FIFO等非任务文件。
6. mission_scripts安装4份版本化模板，不创建第二执行器；demos安装C++/Python只校验默认示例，显式执行可精确取消并等排空，SDK本地清理未确认也返回失败。默认任务门面目录不悄悄改为新模板目录，需显式配置规范父目录。新接口/SDK须同步重编译相关包与消费者；Python直接动作最小集合不扩张，track/search通过execute_mission调用。

实现范围、字段/默认值、迁移与操作说明见[docs/development/d3-missions.md](docs/development/d3-missions.md)。

### 9.2 开发过程、失败与修复

- 主agent负责格式、搜索、接口/门面、模板与真实任务链；coder负责SDK/绑定及FSM限定实现，reviewer只读复核。未修改用户agent配置或恢复用户删除文件。
- 初轮格式单测字符串拼接类型错误、Humble service callback泛型参数无法匹配function_traits导致构建失败，均修为明确类型后重编；失败构建不计成功。
- 首轮只读评审发现公开Action终态不能证明递归子执行已停，已增加上述UUID所有权协议及真实嵌套失败保锁测试；同时补齐定位非法值、电池非法值和迟到成功越过预算的保护。二轮评审补充Search预算先于消费结果、失败及时传播，以及任务服务迟到取消拒绝覆盖真实状态问题，修复均有负向回归。
- 第一次安装示例/四模板任务链因仅等待门面发现、未等全链能力就绪而失败；改为查询实际能力ready后执行，不删掉失败断言，不用固定延时掩盖准入。最终3场景覆盖4模板、安装C++/Python默认/显式取消，以及真实门面→FSM→统一导航→迟到私有子动作的递归取消保锁。
- 额外运行完整mission_srvs注册CTest：行为3项通过，cppcheck/lint_cmake/pep257/xmllint通过，但copyright、cpplint、flake8、uncrustify四项失败（版权声明/代码风格问题）。如实保留质量欠账，不关闭/删除检查，不把全部注册检查写为通过。本轮功能验收不等于风格及许可证声明已全部收口。
- 最终只读源码/契约评审无阻塞；评审建议统一Python示例本地清理超时退出码，已改为失败并再次运行安装任务链。尚未另行实施独立SITL/硬件签收。

### 9.3 验证记录（2026-10-04，本批软件范围）

以下命令先source /opt/ros/humble/setup.bash与install/setup.bash。隔离domain，使用合成遥测/动作mock或软件plant，不接硬件；没有开展G9长稳/冷启动循环。

| 检查 | 实际命令 / 日志 | 最终结果 |
|---|---|---|
| 接口构建 | colcon build --base-paths src --packages-select easyfly_msgs --symlink-install | 新srv及ManageMission字段构建通过 |
| 7相关包构建 | colcon build --base-paths src --packages-select easyfly_core easyfly_pybind easyfly_mission_fsm easyfly_global_planner easyfly_mission_srvs easyfly_mission_scripts easyfly_demos --symlink-install | 全部rc0；log/build_2026-10-04_19-54-22/events.log记录34.78s；随后FSM/demos及服务修复重编分别见19-57-01/19-59-45日志 |
| SDK C++ | ctest --test-dir build/easyfly_core --output-on-failure -R '^test_sdk$' | 9场景通过3.63s；含Search、真实终态早于UUID释放、未知/失联保锁及清理屏障 |
| SDK Python | ctest --test-dir build/easyfly_pybind --output-on-failure -R '^test_sdk_python$' | 7场景通过4.41s |
| 格式/任务/搜索 | ctest --test-dir build/easyfly_mission_fsm --output-on-failure | 6个行为CTest通过19.39s；旧格式3单测、正式格式3组、几何2组、全文真实预校验、任务13场景、搜索8场景 |
| 门面/入口 | ctest --test-dir build/easyfly_mission_srvs --output-on-failure -R '^test_(services\|launch\|platform_smoke)$' | 最终行为3项通过11.90s（10.78/0.29/0.83s）；服务9场景含真实结果后保锁和迟到取消拒绝；完整11项注册检查另有4lint失败 |
| 参数/配置 | ctest --test-dir build/easyfly_params --output-on-failure -R '^test_(configuration\|runtime)$' | 2项通过0.73s |
| profile配置 | python3 -m pytest -q src/application/a1_sdk/easyfly_params/test/test_configuration.py src/application/a3_mission/easyfly_sim_launcher/test/test_profile_launch.py | 38项通过0.20s |
| 协调器回归 | ctest --test-dir build/easyfly_global_planner --output-on-failure -R '^test_(coordinator\|local_coordinator\|late_session\|astar_deadline)$' | 4项通过18.14s；实际UUID未停OWNED、排空RELEASED有断言 |
| 完整任务链/安装示例 | ctest --test-dir build/easyfly_demos --output-on-failure -R '^test_task_chain$' | 3场景通过17.44s；Python退出码收口后再次通过15.30s，安装脚本为源码symlink，确认测到新实现 |
| 真实导航软件链 | ctest --test-dir build/easyfly_global_planner --output-on-failure -R '^test_navigation_chain$' | 静态/动态及Python SDK三场景通过87.31s；不是实际PX4/Gazebo动力学 |
| 最终工作树检查 | git diff --check；ps按任务/搜索/门面/导航/示例进程匹配检查 | diff检查通过，相关测试进程残留0；用户预存修改未恢复/未提交 |

### 9.4 交付边界

D3-01至D3-05按本批顺序任务开发范围功能验收通过，任务服务四项lint欠账未清零。G9–G11保持暂停；未进行PX4/Gazebo SITL、实机、真实相机搜索覆盖或跟随安全签收。分支/重试、额外搜索模式、通用悬停控制出口、更多Python直接动作及D4以后能力不冒称完成。

源码与文档在工作树，D3未提交；D2提交00d12b8未push。用户预存.codex三项修改与codex_cli.sh删除保持原状且排除于D2提交。未通过进程退出、删除快照或公开失败推断飞行已停；未知所有权不自动解锁。后续若清理lint，需单独保持测试与版权归属明确，不以批量删检查处理。

### 8.6 D2 独立验收（2026-10-04，ZCode 受权执行）

验收基线：工作树未提交的 D2 改动（HEAD=dfd6859/D1 + D2 工作树 52 项）；独立 domain 测试。

**新鲜度异常与处置**：验收时发现 `easyfly_core/include/client.hpp`（15:18:34）比最后构建（15:18:03）新 31 秒。按"源码晚于构建必须重编复测"纪律，串行重编 `easyfly_core + easyfly_pybind`（rc0，16.8s）后全部 SDK 测试在重编产物上通过——当前源码状态确认。

按 §8.4 清单逐项独立复跑，全部通过：

| 检查 | 结果 |
|---|---|
| C++ SDK（test_sdk，内部 6 场景） | ✅ Passed 2.54s（重编后） |
| Python SDK（test_sdk_python，内部 7 用例） | ✅ Passed 4.53s + `--repeat until-fail:3` 连续 3 次通过（稳定性声明复验） |
| SDK 安装示例（domain 98，无后端） | ✅ C++/Python 均 exit 0，只查询无运动请求，输出明确 `received=0/ready=false/navigate_server=0` |
| 参数（configuration+runtime） | ✅ 2 CTest |
| 感知（services） | ✅ Passed |
| 旧任务预校验（legacy_mission+prevalidation） | ✅ 2 CTest |
| 任务门面（services，7 场景） | ✅ Passed |
| 平台入口（launch+platform_smoke） | ✅ 2 CTest |
| 配置 pytest | ✅ 38/38 |
| 真实软件导航链（含 SDK 场景 3 用例） | ✅ Passed 89.9s |
| git diff --check / 进程残留 | ✅ / 0 |

独立抽检（超出文档清单）：
1. **五包零 setpoint 旁路**（D2 安全声明"均不发布setpoint"）：`easyfly_core/pybind/mission_srvs/perception_srvs`（+params）源码 grep 无任何 setpoint 引用 ✅；
2. **动态白名单仅 2 参数**：`runtime.py` 仅声明 `operator_note`（UTF-8≤512 校验在案）与 `export_pretty` ✅；
3. **hardware_unverified 拒绝启动**：configuration.py `load_profile` 对该 profile 抛 `ValueError`（"unverified hardware cannot advertise active capabilities"），mission_srvs 的 `service_nodes` 经 `ensure_launchable` 走同一拒绝路径，`test_launch.py:36-38` 有负向回归在案 ✅；executor Include 默认 `start_mission_executor=false` ✅。

验收结论：**D2-01~D2-06 按本批开发范围验收通过**。开发记录（§8.3-8.5）与实测一致；退出竞态修复后的稳定性声明（repeat×3）经独立复验成立。边界确认：本验收为组件/软件闭环级；D2 改动截至验收**尚未提交**。

### 9.5 D3 独立验收（2026-10-04，ZCode 受权执行）

验收基线：工作树未提交的 D3 改动（HEAD=00d12b8/D2 + D3 工作树 52 项）；独立 domain 62。

**新鲜度异常与处置**：`easyfly_demos/scripts/sdk_mission_demo.py`（20:11:45）比最后构建（19:57:44）新 14 分钟。重编 demos 包（rc0 0.83s）后所有任务链测试在重编产物上通过——当前源码状态确认。其余 7 个 D3 相关包全部 FRESH。

按 §9.3 清单逐项独立复跑，全部通过：

| 检查 | 结果 |
|---|---|
| SDK C++（9 场景） | ✅ Passed 3.73s |
| SDK Python（7 场景） | ✅ Passed 4.43s |
| FSM 全量 6 行为 CTest | ✅ 6/6（legacy_mission/mission_format/search_geometry/prevalidation/mission_executor 11.53s/search_action 6.30s） |
| 门面行为 3 项 | ✅ 3/3（services 10.14s/launch/platform_smoke） |
| 参数（configuration+runtime） | ✅ 2/2 |
| 配置 pytest | ✅ 38/38 |
| 协调器回归 4 项 | ✅ 4/4（coordinator/local_coordinator/late_session/astar_deadline） |
| 完整任务链/安装示例 3 场景 | ✅ Passed 15.51s（重编后） |
| 真实导航软件链 3 用例 | ✅ Passed 86.68s |
| git diff --check / 进程残留 | ✅ / 0 |

独立抽检（超出文档清单）：
1. **lint 欠账确认**：`test_(copyright|cpplint|flake8|uncrustify)` 恰好 4 项失败，与 §9.2"4 lint 欠账"声明精确一致 ✅；行为 3 项在环境正确 source 后通过（无 source 时 ctest 包装器会假失败，与 V2-16 验收时同类环境现象）；
2. **所有权协议**：`ownership_registry.hpp` 实现 OWNED/RELEASED 状态机，"Active IDs never expire. Evicted released IDs become UNKNOWN, never a false"——主动 ID 永不自动释放 ✅；
3. **模板 4 份就位**：navigation_return_v1 / search_land_v1 / takeoff_hold_land_v1 / timed_track_land_v1，内容为 schema_version:1 正式格式（含 frame_id/units/failure_policy/有界 timeout）✅。

验收结论：**D3-01~D3-05 按本批顺序任务开发范围验收通过**。开发记录（§9.2-9.4）与实测一致；4 项 lint 欠账如实在册（非阻塞）。边界确认：组件/软件闭环级；D3 改动截至验收**尚未提交**。
