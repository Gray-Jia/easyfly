# EasyFly 开发执行记录（schedule-v4）

> 开始时间：2026-10-04 07:33（Asia/Shanghai）
> D0完成时间：2026-10-04 07:51（Asia/Shanghai）
> D1完成时间：2026-10-04 14:09（Asia/Shanghai）
> D2完成时间：2026-10-04 15:20（Asia/Shanghai）
> D3本批功能验收完成时间：2026-10-04 20:15（Asia/Shanghai）；lint欠账另列。
> D4第一版软件功能验收完成时间：2026-10-05 07:04（Asia/Shanghai）；全lint/SITL/实机不在本批签收范围。
> D5仿真第一版完整链验收：2026-10-06；限定配置与证据见第11节，真实设备继续暂缓。
> 计划依据：`plan-v3.md` D0–D5；起点 HEAD：`1860690`。
> 状态：D0–D4本批组件软件功能范围完成；D2已提交00d12b8，D3已提交87ac9e5，D4未提交。10.9初次lint/SITL失败及后续修复保留；当前安全修复结果见10.13。D5仿真第一版在显式限定配置下完整链通过，组件与实际任务结果分层记录在第11节；真实设备暂缓，G9-G11复验继续暂停，全仓lint及实机未签收。
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

本节D3验收时源码与文档在工作树、D3未提交；后续按用户授权提交为87ac9e5，见第10节。D2提交00d12b8未push。用户预存.codex三项修改与codex_cli.sh删除保持原状且排除于开发提交。未通过进程退出、删除快照或公开失败推断飞行已停；未知所有权不自动解锁。后续若清理lint，需单独保持测试与版权归属明确，不以批量删检查处理。

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

## 10. D4：感知与融合扩展（七方向第一版软件功能完成）

2026-10-04 20:18 起，按用户“提交，然后开始D4”授权提交D3为`87ac9e5 feat(D3): add versioned missions and managed search execution`（51文件），未push。预存`.codex`三项修改及用户删除`codex_cli.sh`未纳入提交。第9节的未提交状态属于D3验收时点，本节为后续更新。

依据plan-v3第9节，D4共七个子方向。首批两方向记录保留在10.1–10.4，用户“继续完成D4/继续执行”后，2026-10-05续批补齐其余五方向，记录见10.5以后。用户确认：预测独立输出；AprilTag 36h11＋显式尺寸；CSRT＋显式ROI重定位、丢失不猜身份；类别仅独立语义副本，保留原`/obstacles`与占据地图。沿用主agent/coder/只读reviewer分工与root＋一个子agent并发限制。

| ID | 目标 | 进度/结果 | 验收标准 |
|---|---|---|---|
| D4-01 | 时间配对、内外参加载校验与持续诊断 | 首批实现通过：time_sync独立节点；全配置验证后发布TF；持续CameraInfo与时钟有效性诊断 | 保留原采集时间；容差/丢帧/队列预算可查；配置后半份非法不部分发布；内参失配、非法与过期不可信；非硬件同步/在线标定求解 |
| D4-02 | 独立有界目标预测 | 首批实现通过：恒速模型、独立输出、身份/时间/跳变保护 | 两次真实观测；有限时域/模型方差；过期/消失/空帧/非法/暂停/回退失效；不写实测/地图/飞行命令，不绕过跟随保护 |
| D4-03 | 单目标跟踪 | 实现/功能回归及审查通过：CSRT、显式ROI/状态/新身份 | 一个后端、ROI初始化/重置、丢失/重定位及身份切换明确，可显式接3D链 |
| D4-04 | 标签检测 | 实现/功能回归通过：36h11、显式尺寸、IPPE及歧义拒绝 | 校验内参/尺寸/图像时间/frame，已知几何可定位，缺尺寸或非法观测不输出可信位姿 |
| D4-05 | 降落标志 | 实现/功能回归通过：显式标签ID→独立LandingTarget | 中心、光学方向/深度与有效性明确；光学Z非地面高度，不等于D5精准降落控制 |
| D4-06 | 雷视融合 | 实现/功能回归通过：双源时间TF、着色云/稀疏深度独立输出 | 附近时刻点云投影可核对；同像素Z-buffer遮挡、超时差、无TF失败明确；不接占据/飞行 |
| D4-07 | 障碍类别融合 | 实现/功能回归通过：独立副本、双向唯一关联/源TTL；原地图不改 | 可靠目标与几何关联、置信度/有效期；未匹配unknown，类别失效不删除几何占据 |

### 10.1 首批实现事实

- 主agent实现time_sync、标定配置/诊断、三项新消息、ROS测试、契约与集成记录；coder限定负责target_prediction目录及核心/ROS测试；reviewer只读审查首批源码、风险修复与日志，不签收未开发的其他方向。
- time_sync提供两个显式配对输出，使用严格递增源时间、有序FIFO/容差与旧侧丢弃，原图像header/frame/data完全保留。/time_sync/status记录有符号时间差、当前有效性、配对/两侧丢弃/队列统计；应用层每侧8条/单图4MiB/两队列64MiB默认预算，可只读配置。源、接收和暂停时限独立，回退清缓存；不混称硬件同步、深度配准或中间件完整内存防线。默认不重映射现有感知主链。
- 标定配置常规文件≤64KiB，完整解析有限值、字段/向量/frame/内参/畸变和重复child/TF环后才创建广播器发送整树。沿用现有sensors.yaml，plumb_bob＋5系数第一版边界明确。CameraInfoChecker由一次性确认改为持续诊断，检测后续失配、非法数值/时间、过期、零/暂停/回退ROS时钟；不冒称在线求解器或自动飞行准入闸门。原pixel_to_3d相机更新逻辑本批未重构。
- 目标预测至少两次同身份真实观测，整帧保守校验，输入/缓存默认256；来源、接收与clock-progress分别有界。空帧/消失/类别变动/非法/过速/跳变/过期重建或失效；输出header为当前参考时刻，observation_header保存原观测，位置按age＋horizon外推，等轴模型方差明确不是传感器标定协方差。只发布/target_predictions，不接飞行或地图。
- 新增TargetPrediction、TargetPredictionArray、TimeSyncStatus消息，既有Target3D/Array及飞行动作字段不变。新增能力服务区分软件配对/硬件同步unsupported，以及预测implemented/当前模型ready；ready不代表飞行许可。已有profile不自动启用配对/预测；calib launch维持模拟默认并允许显式use_sim_time/calib_file。
- 文档见[docs/development/d4-perception.md](docs/development/d4-perception.md)，成熟度、接口契约及包README同步更新。总包67不变；明确TODO骨架20（仅按CMake实际计数，不推算项目完成百分比）。

### 10.2 失败、修复与只读评审

1. 首次3包构建因Humble没有rclcpp::Time::to_msg及泛型service callback不匹配function_traits失败；coder改为明确类型和消息转换后统一重编3包通过。其余被中止包不计成功。
2. 预审P2指出CameraInfoChecker零/暂停/回退时钟可能在重复receipt下误报valid；已加独立steady进展门和回退清latest，新增真实ROS未clock、暂停重复样本和rollback回归通过，评审确认关闭。
3. 初轮time_sync ROS测试错误使用自建Context＋默认全局executor，fixture在setup失败留下3个仅配对测试进程；已改同Context专用executor和addCleanup，核对PID/PGID后SIGINT停止本测试进程，不涉及飞行节点。后续进程残留检查为0。
4. 实际配对测试发现C++函数参数求值顺序使两次wall()调用造成receipt晚于检查时刻，真实输入全被拒绝。已改先捕获一次received及reference再传入，重编并用真实ROS普通/异常/clock场景验证；不是只调整测试掩盖代码错误。
5. 模拟clock测试另有浮点转ns少1ns和单帧volatile发现窗口问题，改为整数round、等待实际clock订阅发现，并在建立配对时显式推进输入/clock，随后真实冻结/回退；断言未删，应用时间预算未放宽。
6. 首批最终只读复核无剩余阻塞；三类ROS回归各追加until-fail:2连续两次通过，仅为本批短重复稳定性证据，非G9长稳复验。

### 10.3 实际构建与验证（首批）

先source /opt/ros/humble/setup.bash及install/setup.bash。使用domain104/105/106与合成图像、CameraInfo、观测、clock；不接飞行硬件，不启动PX4/Gazebo。

| 项目 | 命令/证据 | 结果 |
|---|---|---|
| 三新消息 | colcon build --base-paths src --packages-select easyfly_msgs --symlink-install | rc0，15.92s；log/build_2026-10-04_20-32-11/events.log |
| 三功能包 | colcon build --base-paths src --packages-select easyfly_time_sync easyfly_camera_calib easyfly_target_prediction --symlink-install | 全部rc0，5.63s；log/build_2026-10-04_20-47-41/events.log；配对取值修复后再次单包rc0 4.70s，20-52-10日志 |
| 时间配对 | ctest --test-dir build/easyfly_time_sync --output-on-failure -R '^test_(pairing\|time_sync_ros)$' | 2行为CTest通过2.06s；5纯核心+3真实ROS场景；真实ROS再重复2次通过2.05/2.09s |
| 标定/内参 | ctest --test-dir build/easyfly_camera_calib --output-on-failure -R '^test_(calibration\|calibration_ros)$' | 2行为CTest通过2.58s；3纯检查组+3真实ROS场景；真实ROS再重复2次通过2.25/2.24s |
| 预测 | ctest --test-dir build/easyfly_target_prediction --output-on-failure -R '^test_(predictor\|prediction_ros)$' | 2行为CTest通过4.99s；7纯核心+5真实ROS场景；真实ROS再重复2次通过4.93/4.93s |
| 配置/嵌套launch | python3 -m pytest -q src/application/a1_sdk/easyfly_params/test/test_configuration.py src/application/a3_mission/easyfly_sim_launcher/test/test_profile_launch.py | 38项通过0.19s，既有profile安全默认保持 |
| 既有3D/frame | ctest --test-dir build/easyfly_pixel_to_3d --output-on-failure -R '^test_frame_contract$' | 通过0.04s |
| 感知服务 | ctest --test-dir build/easyfly_perception_srvs --output-on-failure -R '^test_services$' | 通过1.03s |
| 最终检查 | git diff --check；按4类新/修改感知进程匹配ps检查 | diff通过，相关测试进程残留0；用户预存修改保持未提交 |

以上为选择的行为测试，不是所有注册linter都通过。D3的4项版权/格式lint欠账未清零，D4本轮未运行完整lint组合，不能据diff检查通过推断格式/版权签收。

### 10.4 首批验收时点的边界（续批见10.5以后）

D4-01/02首批源码、相关构建和组件/真实ROS回归完成；D4整体继续进行，D4-03至07待开发。下一步按现有计划推进单目标跟踪与已确认语义的标签检测，再接降落标志/雷视及类别融合；不提前启用未实现landing/precision_landing profile能力。

D4修改尚未提交；D3已提交87ac9e5、未push，预存用户修改保持。未进行G9–G11、SITL、实机标定/硬件同步、真实跟随或相机/雷达融合安全签收。预测统计可靠性与真实视觉效果未经过实际数据评估，不将模型输出解释为实测。

### 10.5 续批目标、分工与实现事实（2026-10-05）

目标：补齐D4-03至07第一版软件功能，按已确认边界保证独立输出、输入有效性、时钟/过期保护及可重复的真实ROS验证；不扩展到D5飞行控制或G9+复验。

- coder限定负责single_object_tracking、apriltag_detection、landing_detection三个目录及其测试/README；主agent负责六个新增消息及ManageSingleTrack服务、独立fusion/classification、应用能力桥接、统一构建与记录。reviewer只读最终审查；任何时点只root＋一个子agent运行。
- 单跟踪CSRT由精确最新显示header＋归一化ROI初始化。新ROI新ID、lost必须重定位、reset回idle；接受仅排队，worker成功后才tracking。独立TrackInfoArray可显式接既有pixel_to_3d配置，但不自动替换SORT。confidence=0未知、没有虚构3D/速度/概率；latest工作槽、generation、水位及join隔离旧工作。
- 标签36h11/IPPE_SQUARE，必须显式物理尺寸与匹配CameraInfo，有限正深度/单位姿态/角点RMS与位姿歧义门。独立TagObservationArray保留原图header，valid空标签与invalid区分。尺寸默认0不可信；相似误差的真实不同位姿不任意挑选。
- 降落感知只选显式ID（默认-1无选择），重复选中ID/上游非法/过期/不可观测方向均invalid。LandingTarget中心/方向/深度在相机光学frame，yaw非ENU航向、Z非离地高度；无动作/下降/模式切换。perception_srvs保留原查询结构，仅动态报告landing_detection implemented、真实新鲜有效目标时ready；precision_landing仍false。静态profile默认不启用。
- 雷视融合只输出独立着色云/稀疏32FC1深度。TF使用两个实际源时间经fixed odom转换，不用latest；保留源云XYZ/header，深度保留图像header、未投影NaN。同像素最近Z遮挡处理，不宣称完整动态场景补偿。源、receipt、clock进展/回退与epoch验证发布，有界预算/worker；无TF/坏K/超差/过期不ready。
- 类别融合新增独立obstacle_classifier，原semantic_map_node.cpp不改。expanded AABB候选两侧均唯一才关联；原几何ID/header/形状/动态速度保留。标签的confidence、observed_at/源TTL独立，丢失/歧义/低置信度unknown不删除有效几何；geometry_valid=false不能解释成没有障碍。没有原obstacles、占据栅格或飞行publisher。
- 原接口字段不变，共九新消息＋一服务；easyfly_msgs依赖同步声明。新增包README、D4契约、plan-v3及成熟度同步；67包保持，明确TODO骨架16，不据包数估算项目完成率。启动参数只读且范围/时钟/frame在D4契约中记录；预算不替代DDS Security/反序列化限制。

### 10.6 续批失败、修复与验证边界

1. 当前Python cv2与NumPy2环境不兼容（_ARRAY_API/ImportError）；未擅改系统依赖，使用已安装OpenCV C++实现/生成图像，ROS夹具仅标准字节，不依赖cv2/numpy。
2. 首次标签包构建缺imgproc头导致tag_fixture失败；补齐后3包定向build通过。缺尺寸测试曾用整数0传入double参数导致节点拒绝启动，已改0.0并真正验证size=0时invalid，没有删除断言或放宽阈值。
3. coder发现任意能力/worker入口先消费ClockGate回退后，其他入口可能漏清水位；统一good_clock执行回退reset。三个模块均实际use_sim_time验证0→100正常→暂停失效→恢复→回退50失效→新域重建；单跟踪恢复始终需显式新ROI/身份。
4. Fusion第一次真实ROS暴露Humble Python DiagnosticStatus.level须bytes，整数造成timer assertion；改bytes([0/2])并重新运行真实投影/负向。测试setup失败清理注册提前，节点/线程/进程不会留存。投影时差负向测试改为未来+0.1s，避免误匹配合法旧缓存图像；应用容差保持0.05s。
5. 分类候选最初只对单匹配框统计可能漏掉另一个歧义框的候选边；改为对全部候选边计算双向唯一性，新增一框歧义同时阻止另一框错误贴类回归。
6. 应用landing能力增加steady timer，持续检测clock进展，避免稀疏能力查询掩盖冻结；正/invalid/receipt过期及真实clock0、暂停、回退重建均通过。完整lint注册保留（含补回prediction原注册），未运行的版权/格式检查不记通过。
7. 最终只读审查发现两项P2：fusion无效cloud没有清pending，worker可能给旧排队任务重标新epoch；tag旧结果ready与发布没有完整复验实际使用的CameraInfo。主agent修fusion为提交即绑定epoch、非法/超预算cloud清pending；新增RLock确定性阻住真实worker验证隔离（夹具初次height=0未触发预算，纠正height=1，未放宽应用检查）。coder修tag为结果保存实际image＋CameraInfo及各receipt，ready/timer/发布前复验两份来源，坏/变模型即时失效，同模型正常更新不误撤销。新增真实ROS坏K无新图、模型变更与旧K过期回归。reviewer复核关闭两P2，无剩余阻塞。

### 10.7 续批统一构建、行为验收与只读审查

先source `/opt/ros/humble/setup.bash`和`install/setup.bash`，只使用隔离domain、合成图像/观测/TF/Clock。首次三包以及主agent两融合包构建分别16.7s/12.6s通过；coder最终三包构建8.00s通过，原8行为CTest通过，真实image→tag→landing第9项通过3.20s；清理注册修改后三ROS又通过。最终统一验证另列如下，不混用历史签收。

| 项目 | 命令/范围 | 结果 |
|---|---|---|
| 最终11包构建 | colcon build --base-paths src --packages-select easyfly_msgs easyfly_time_sync easyfly_camera_calib easyfly_target_prediction easyfly_single_object_tracking easyfly_apriltag_detection easyfly_landing_detection easyfly_lidar_camera_fusion easyfly_semantic_map easyfly_perception_srvs easyfly_params --symlink-install | 11包rc0，6.01s；log/build_2026-10-05_06-56-14/events.log |
| D4八功能包统一行为复跑（首次最终审查前） | 各包ctest --test-dir build/<package> --output-on-failure -R '^test_'，串行 | 24/24通过：time2=2.09s、calib2=2.46s、pred2=4.98s、single3=5.19s、tag3=11.31s、landing3=8.72s、fusion3=5.48s、semantic6=2.18s；只选行为不含全部lint，评审两问题修复后再定向复跑 |
| P2修复后构建 | coder单tag及root单fusion分别colcon build --base-paths src --packages-select <package> --symlink-install | tag通过6.94s；fusion通过1.39s，log/build_2026-10-05_07-03-03/events.log；test_pending已实际注册，无隐藏跳过 |
| P2修复后复跑 | fusion/tag -R '^test_'；landing -R '^test_landing_e2e$'；perception_srvs -R '^test_services$' | fusion4/4=6.10s（含pending隔离）、tag3/3=14.59s（含标定生命周期）、真实image→tag→landing=3.18s、能力服务=3.17s；累计D4八包当前25行为CTest全部实际通过 |
| 感知能力桥接 | ctest --test-dir build/easyfly_perception_srvs --output-on-failure -R '^test_services$' | 1 CTest、2用例通过3.22s；真实源有效/非法/过期与clock回退 |
| 参数动态受限 | ctest --test-dir build/easyfly_params --output-on-failure -R '^test_runtime$' | 通过0.40s；原限制保持 |
| 配置与嵌套launch | python3 -m pytest -q src/application/a1_sdk/easyfly_params/test/test_configuration.py src/application/a3_mission/easyfly_sim_launcher/test/test_profile_launch.py | 38项通过0.20s，profile默认不误启用 |
| 原3D/frame契约 | ctest --test-dir build/easyfly_pixel_to_3d --output-on-failure -R '^test_frame_contract$' | 通过0.04s；没有宣称coord_transform无注册测试的包通过 |
| 只读审查 | /root/d1_review限定D4续批五方向、消息与能力桥接 | 首轮无P1、2项P2；修复复核均关闭，无剩余阻塞；不签收未运行lint/SITL/硬件 |
| 最终检查 | git diff --check；新/修改感知进程PID检查；colcon list与CMake TODO计数 | diff通过，相关测试进程残留0；67包、16明确TODO骨架；原semantic_map_node.cpp无diff；用户预存改动保持 |

### 10.8 当前交付边界

七方向第一版源码、统一构建、当前25行为CTest及P2修复后的最终只读审查完成，按10节表中软件边界验收通过。D4未git提交、未push；D3 HEAD仍87ac9e5。预存.codex三文件与用户删除codex_cli.sh保留不动。完整lint未验收，D3四项lint欠账保留。

上述为07:04组件验收时点；后续用户明确授权lint/SITL试跑见10.9，不追溯改写为此前已签收。仍不启动D5或G9–G11/实机签收。真实视觉成功率、CSRT身份可靠性、相机/雷达外参精度与动态场景融合、预测统计校准尚需真实数据评估。独立降落感知不是精准降落控制；分类副本及预测不进入现有避障/飞行链。

### 10.9 用户授权的lint及SITL试跑（2026-10-05 07:09–07:22）

用户要求“跑一下lint、sitl试试”。范围：D4八功能包及相关参数/感知服务的注册lint，复验D3任务服务已知lint；现有headless perception_sitl短冒烟＋独立D4观察，以及一次低高度Takeoff/Land。不修功能源码、不自动格式化、不假定版权主体、不提交git、不做导航/任务/精准降落、G9–G11或实机。

分工：只读reviewer运行lint并汇总实际日志；主agent独立执行SITL。Lint命令为各包`ctest --test-dir build/<package> --output-on-failure -R '^(copyright|cppcheck|cpplint|flake8|lint_cmake|pep257|uncrustify|xmllint)$'`。共79项注册检查，**39通过、40失败**，不是通过79个测试，也不是40个独立缺陷。

| 包 | 注册lint数 | 通过 | 失败 |
|---|---:|---:|---:|
| easyfly_time_sync | 8 | 4 | 4 |
| easyfly_camera_calib | 8 | 3 | 5 |
| easyfly_target_prediction | 8 | 4 | 4 |
| easyfly_single_object_tracking | 8 | 4 | 4 |
| easyfly_apriltag_detection | 8 | 4 | 4 |
| easyfly_landing_detection | 8 | 3 | 5 |
| easyfly_lidar_camera_fusion | 5 | 3 | 2 |
| easyfly_semantic_map | 8 | 4 | 4 |
| easyfly_perception_srvs | 5 | 3 | 2 |
| easyfly_params | 5 | 3 | 2 |
| easyfly_mission_srvs | 8 | 4 | 4 |

所有注册cppcheck及xmllint通过；所有包copyright/flake8失败，C++包cpplint/uncrustify失败。另camera_calib launch/calib_tf.launch.py:1文档字符串标点（pep257），landing_detection CMakeLists.txt:10括号空格（lint_cmake）。主要为缺版权声明、行长/缩进、include顺序和格式；例如apriltag的include/safety.hpp、src/tag_node.cpp及launch/test缺声明；fusion launch/fusion.launch.py:11、perception test/test_services.py:10、params configuration.py:57行长，mission_services.cpp:11–13 include顺序。D3已知四类失败复现，未清零。fusion/perception_srvs/params仅注册5类，没有C++三项覆盖，不记为通过。

证据在各包`build/<package>/Testing/Temporary/LastTest.log`及`build/<package>/test_results/<package>/*.xunit.xml`（07:09运行）。已有新旧源码都纳入对应注册扫描，不声称全部失败都由D4新增。

#### SITL环境、启动与隔离

Gazebo Classic11.10.2、已构建PX4-Autopilot-1.16.2及传感器插件实际存在，初始无PX4/gzserver/MAVROS占用；ROS_DOMAIN_ID=121、GAZEBO_MASTER_URI=http://127.0.0.1:11355，GUI/RViz关闭、检测强制CPU及best_effort。入口：`ros2 launch easyfly_px4_sitl perception_sitl.launch.py headless:=true detection_use_gpu:=false detection_input_qos_reliability:=best_effort`，不使用串口，MAVROS仅本机UDP仿真连接。

首次临时目录`/tmp/easyfly-d4-sitl.cHL0bn`采用bin链接；第二次`/tmp/easyfly-d4-sitl.HgJNcs`复制bin。实际检查/proc发现两者仍进入PX4编译常量指向的原`/home/jia/PX4-Autopilot-1.16.2/build/px4_sitl_default/rootfs`，单改PX4_DIR/CWD不足以隔离。前两次因此产生原rootfs仿真日志、参数自动更新（日志明确UXRCE_DDS_DOM_ID 0→121）；未手工覆盖/删除原BSON或擅自回滚用户状态。

第三次用仅位于临时目录的wrapper明确`px4 -w /tmp/easyfly-d4-sitl.HgJNcs/build/px4_sitl_default/rootfs -s /tmp/easyfly-d4-sitl.HgJNcs/build/px4_sitl_default/etc/init.d-posix/rcS -d`，从现有BSON副本启动；实际/proc/PID61200/cwd确认临时rootfs。插件/Tools复用只读链接，测试日志重定向文件避免高频PTY输出。没有改项目launch或PX4源码；保留临时目录便于审计。

#### 实际输出与短飞行

- 首次12秒真实订阅收到color117帧、CameraInfo292、depth69、pointcloud94、uav_state232、target_positions103、obstacles97；连接/位置/速度有效、未解锁，640×480 rgb8/camera_color_optical_frame。观察器初次/clock可靠QoS不兼容，后续改sensor QoS；不把观察器QoS错误记成Gazebo未发布时钟。
- 第三次45秒独立启动D4节点（显式use_sim_time=true，single/tag remap到color，tag_size_m=.2、selected_tag_id=7，仅测试配置，不冒充场景标签实测尺寸）。没有重映射飞行或地图输入。8子进程在观测结束前均未退出；实际color454帧、uav_state898、/clock355、calibration有效诊断。
- 时间配对有效状态1600次；预测有效数组453次；着色点云59次非空、有效投影状态154次；分类有效几何1667次、有效类别关联582次。最终相应四能力ready=true。此为收到有效输出的次数，非独立场景数/准确率/性能签收。
- **单目标/标签SITL集成未通过**：单跟踪6次精确显示header ROI请求均拒绝，始终idle；标签`image_time_or_frame_invalid`，ready=false；降落`source_invalid`。只读探针实测Image stamp117.569而节点clock117.500，CameraInfo117.736而clock117.700（超前69/36ms），frame/K/尺寸/packed payload均常规。三个模块的safety.hpp要求source_age≥0，没有其他D4节点的有限未来容差；Gazebo图像与/clock DDS到达顺序造成保守误拒绝。没有通过伪改header、放宽运行阈值或注入假图像绕过。场景本身没有选中36h11标签，也未验证真实标签有效位姿/降落目标。
- 之后独立ActionClient仅对本次仿真发一次`/takeoff {target_altitude:1.0,climb_speed:0.5}`；准入前状态新鲜、connected/pose/velocity有效且disarmed。Takeoff accepted，真实status=4/SUCCEEDED、success=true；进入OFFBOARD且armed。继续等待高度接近目标，采样hover z=.8517m、vz=.0736m/s，整个采样最大z=.8604m；起飞接口使用既有0.5m成功阈值，**不宣称准确达到1.000m**，亦不把odom Z当经校准离地高度。
- `/land {landing_speed:0.0}` accepted，真实SUCCEEDED、success=true、message=landed，最终armed=false；PX4日志同时有Takeoff detected、Landing detected及Disarmed by landing。基础虚拟起飞/保持/降落冒烟通过，未执行导航/任务或精准降落。

证据：[/tmp/easyfly-d4-sitl.HgJNcs/d4-observation.log](/tmp/easyfly-d4-sitl.HgJNcs/d4-observation.log)、[flight-smoke.log](/tmp/easyfly-d4-sitl.HgJNcs/flight-smoke.log)、[console-isolated.log](/tmp/easyfly-d4-sitl.HgJNcs/console-isolated.log)及同目录各新增节点日志；临时日志为运行产物，不随git提交。

#### 退出与当前结论

所有本次进程均已停止，核对无PX4/gzserver/新增感知/服务/轨迹进程残留。**退出验证未通过**：初次及最终运行traj_server在SIGINT5s、SIGTERM10s后仍不退，launch最终SIGKILL（最终PID61940，exit -9）；perception_srvs手动SIGINT退出出现KeyboardInterrupt后再次rclpy.shutdown、context已shutdown异常，退出码1。后者发生在观察结束的主动清理阶段，不是观测期间崩溃，但仍是生命周期欠账。

本次结果是“lint失败＋基础SITL起降通过＋D4部分模块有有效实际输出＋三视觉模块时间准入/退出问题待修”，**不是完整SITL验收通过**。发现项未修复；下一步应经用户确认处理统一时间准入、退出收尾和lint（版权主体需确认），再复跑。G9–G11、D5与实机保持未执行；D4源码未git提交，用户预存.codex改动及codex_cli.sh删除保持。

### 10.10 用户授权修复轮（2026-10-05）

**目标与验收标准**：修复 10.9 的三视觉节点未来时间误拒绝、traj_server 与
perception_srvs 退出错误、原注册格式 lint；复跑真实 Clock 与行为回归及隔离 SITL。
不改源 header，不撤销零/暂停/回退、receipt/水位/身份门控；退出不能以强杀或忽略
子进程非零状态算通过。用户要求功能优先、稍后讨论版权，因此保留原许可与第三方声明。

#### 已实现与软件回归

- coder 负责 single_object_tracking、apriltag_detection、landing_detection：三份
  safety.hpp 统一允许 `source_age >= -min(0.2, max_age_seconds)`；+69ms 图像/观测、
  +36ms CameraInfo 的真实 Clock 回归通过，+201ms 拒绝，原零/暂停/回退与 ROI 隔离仍通过。
- 主 agent 修 traj_server 全局 ROS 对象在 spin 返回后显式释放，避免晚于 context/middleware
  析构；独立进程系统时钟、正值冻结/运行仿真时钟下 SIGINT/SIGTERM 六场景正常退出。
- perception_srvs 正常处理 KeyboardInterrupt/ExternalShutdownException，避免二次 shutdown；
  Humble executor 在信号关闭 context 时初始化 wait set 还可能抛 RCLError，只在 context
  已失效时视为正常退出，活跃 context 错误继续抛出。六个真实进程退出场景及两个针对性
  异常/清理单测通过。验证范围是节点就绪后停止，不宣称构造期间任意信号均已覆盖。
- 按原规则整理 11 包 C++/Python/launch/CMake 格式、include、namespace 与 braces。
  原 semantic_map.cpp 及部分既有头/测试有机械格式差异和等价布尔拆分，未改变占据/几何
  契约或安全阈值；不是只改新文件。未删测试、skip 检查或修改规则。
- 3 视觉包 build 通过；其余 8 包与 ego_planner 的 9 包统一 build 通过（8min8s，EGO
  GNU ld 链接耗时较长）；最终 ego/perception 两包重新配置构建通过（2.71s）。
- 11 包完整 CTest：**32 行为全通过，原 79 lint 为 61 通过、18 失败**。剩余失败仅
  copyright 11 项和 cpplint 7 项的 legal/copyright，格式类错误已清理；不得称 lint 全绿。
  另外 EGO 8 项定向行为/生命周期回归通过，包含会话隔离、实际 managed fault、四组安全
  gtest 与新增退出回归；mission_srvs 三项行为再跑通过。
- 第一轮 XML 校验曾因 download.ros.org schema 网络失败。使用 ROS 官方 rep 仓库固定
  commit `11ca24a41f31480dfb9562ba99f2a5b93d3ebda5` 的 format3/common XSD 和临时 XML catalog
  复跑完整校验，没有删除 PI 或弱化检查。XSD SHA256 分别为
  `f096a197ed6d7878984bb2501a55f7f1bd4895d254399fb7857e154bfb644f41`、
  `941ea8645344f3c4b7b9d7e68799898309d65a18225fa9cbef4169d95d1a3211`。
- reviewer 只读复核关闭测试域名拼写问题（193/194 独立 ROS 域）；时间门控、等价拆分、
  context 错误区分及真实信号退出测试无剩余阻塞。`git diff --check` 通过。

复跑：source ROS 与 workspace 后，设
`XML_CATALOG_FILES=/tmp/easyfly-d4-fix.shb1Vx/catalog.xml`，对 10.9 原 11 包执行
`colcon test --executor sequential --ctest-args --output-on-failure`；EGO 的
`test_traj_shutdown_ros`、`test_navigation_session_ros`、`test_managed_navigation_fault_ros`
及四组安全 gtest 另定向执行。临时 catalog/XSD 与结果在同目录，未加入产品运行配置。

#### 实际 SITL 功能与退出证据

仍使用 CPU、headless、best_effort、独立 domain121/Gazebo11355，PX4 `-w/-s` 显式指向
上轮临时 rootfs/staging，原 PX4 工作目录未新增写入。观察脚本前几次有执行名/字段错误及
信号发送到 CLI 包装层的错误，失败日志保留；已核对清理实际进程并纠正夹具，不计这些
尝试为平台验收通过。最终直接启动 8 个节点的真实可执行文件，而非只监督 ros2 run。

- 实际图像小幅超前 /clock 555 次，ROI 第一次请求接受、ID1、初始化后有 14 次有效
  tracking；随后 lost 9 次，未自动猜测身份或重初始化。**不宣称 CSRT 持续跟踪性能已通过**。
- 实际软件配对有效2061、预测有效356、非空着色云49、几何有效1655、类别关联有效303。
  标签有效空图553，landing 为 selected_tag_missing 553；不再持续误报时间无效。
  仍有启动/过期等 invalid 输出，均保守失效。场景没有选中真实36h11标签，不声称真实
  位姿或精准降落验收通过。
- 首个功能正向尝试的 takeoff 被拒绝，未解锁；夹具此前只检查 pose/velocity、遗漏
  flight_state_ready 必需的 attitude_valid。保留拒绝记录，最终等待 connected、pose、
  attitude、velocity 有效且 disarmed 后请求：Takeoff 真 SUCCEEDED，armed/OFFBOARD；
  hover z=.871643m、vz=.075898m/s；Land 真 SUCCEEDED/landed，最终 disarmed。保持既有
  0.5m 成功阈值，不宣称精确达到1.000m或把 odom Z 当离地高度。没有导航/任务/精准降落。
- 八个新增实际节点均 exit0；traj_server SIGINT 正常退出，未用 SIGKILL，原退出问题闭合。
  **另发现 ego_planner_node 在停止阶段 exit -11**；launch 主进程 exit0 不能覆盖这个失败。
  全套退出验收尚未通过，新增问题正在进一步捕获真实栈，不能算已修复。

证据：[/tmp/easyfly-d4-fix.shb1Vx/sitl-observation.log](/tmp/easyfly-d4-fix.shb1Vx/sitl-observation.log)、
[console.log](/tmp/easyfly-d4-fix.shb1Vx/console.log)、[tests-offline-schema.log](/tmp/easyfly-d4-fix.shb1Vx/tests-offline-schema.log)、
[ego-shutdown-fault-tests.log](/tmp/easyfly-d4-fix.shb1Vx/ego-shutdown-fault-tests.log)及各节点日志。

版权建议见[作者署名与许可选择](docs/development/copyright-options.md)：仅提建议，署名主体及
MIT/Apache-2.0 选择待用户确认，18 个声明类检查不伪记通过。D5、G9以后与实机未开展；
本轮未提交 git，用户既有 .codex 修改及 codex_cli.sh 删除保留。

#### 继续排查偶发退出（用户要求继续）

- coder 对同参数独立域119的 EGO 做 8 次无调试器活跃点云退出、1 次 GDB 空闲和3次
  GDB 活跃点云退出，均 exit0，未重现原 SIGINT 后 -11；因此未盲改 FSM/manager。
- 主 agent 接手真实 SITL，使用 ROS2 launch 的 launch-prefix/filter 只调试 EGO；
  真实起降再通过，EGO inferior 正常退出。记录 `/clock`463条、`/odom`2465条、
  `/pointcloud_nonground`314条，62.217s、8.7MiB，可重放。录制器 exit0，8个D4节点 exit0。
  该轮 Gazebo 停止出现 boost thread trying joining itself、exit -6，独立登记为未闭环。
  初始 GDB 夹具在正常 inferior 退出后仍无条件 generate-core，产生调试器自身 exit1；
  已改为仅在仍有 inferior threads 时生成栈/core，不能把这个夹具错误当 EGO 崩溃。
- 主 agent 对真实录包的飞行期间不同偏移做 8 次独立域119回放（含 SIGINT/SIGTERM，
  bag publisher 先停/保持发布两类时序），每次日志确认真实 trusted cloud accepted，
  均 exit0。首次偏移40s尚未到地图准入高度，无可信点云，未计入有效的8次。
- 接着对 EGO 与 Gazebo 同时加 GDB 前缀做整套 SITL：ROI接受、真实tag有效空帧581，
  配对2041、预测356、着色53、关联381，基础起降真SUCCEEDED/最终disarmed；
  EGO与Gazebo两个 inferior 均正常退出，8个D4节点及launch exit0，无子进程异常或强杀。
  CSRT只有1次有效tracking后lost，不宣称持续跟踪性能；GDB改变时序，不能关闭偶发问题。
- `/var/crash` 的现有 Gazebo报告是07:53:21启动/加载阶段的另一事故，不是上述停止事故：
  栈在系统 `gazebo_ros::QoS::get_publisher_qos` ← `GazeboRosCamera::Load`，不能拿它解释
  boost self-join。只读解包在临时目录，未覆盖原报告、未改ROS/Gazebo系统包。
- 完善退出夹具使运行Clock在就绪后仍单调推进，不因测试重置tick意外回退；两份真实
  进程回归最后再跑通过（traj7.79s、perception3.22s及flake8）。

证据目录：[真实录包/调试](/tmp/easyfly-ego-gdb.IneHOQ)、
[回放结果](/tmp/easyfly-ego-gdb.IneHOQ/replay-results-final.log)、
[双调试器SITL](/tmp/easyfly-shutdown-gdb.p95f1M/observation.log)、
[其完整日志](/tmp/easyfly-shutdown-gdb.p95f1M/console.log)、
[旧Gazebo报告回溯](/tmp/easyfly-gz-core.ePoxxg/backtrace.log)。
目前所有该批诊断进程均已回收；正在补一次不带调试器的最终复跑。历史偶发 EGO/Gazebo
退出失败未找到可验证的源码根因，不能将未修改的源代码标成“修复了偶发崩溃”。

**最终无调试器复跑结果**：观察脚本严格要求所有 side nodes exit0、launch exit0、日志
没有任何 process has died 或 SIGKILL；本次进程退出0，检查通过。真实 takeoff/land 均
SUCCEEDED，hover z=.874451m/vz=.074110m/s、armed/OFFBOARD，最终disarmed；八个D4
节点、EGO、traj_server、Gazebo及其它核心进程均正常退出，无残留。本次ROI第一次接受，
tracking有效285、随后lost4（没有自动重定位）；软件配对1975、预测421、着色49、关联417、
tag有效空帧560，landing selected_tag_missing560。保留正常失效/失踪行为，不宣称实际
标签位姿、精准降落或持续跟踪性能已验收。

证据：[最终观测](/tmp/easyfly-final-sitl.n6gOMx/observation.log)、
[最终完整日志](/tmp/easyfly-final-sitl.n6gOMx/console.log)。**结论是原时钟/两个节点退出/格式
修复已验证，本次完整基础SITL含退出通过；但历史偶发EGO/Gazebo崩溃仍作为已知未闭环
保留**，没有用本次通过覆盖之前的失败。已向用户询问是否扩展下一轮为底层组件独立调试
和可回滚源码补丁；当前未升级/覆盖系统安装，未改未定位的FSM/Gazebo源码。

### 10.11 Apache-2.0 落地与继续退出排查（2026-10-05）

**用户决策**：自有代码采用 Apache-2.0，继续排查。此前10.9–10.10是历史检查记录，
其中“版权待确认/18项声明失败”由本节的新结果取代，不删除历史失败证据。

**执行目标**：统一自有代码许可并清零原lint；隔离Gazebo传感器与完整插件链路，
继续捕获两个偶发退出事故；只对有证据的路径作结论，不盲改FSM或系统组件。

**验收标准**：

- LICENSE/README/自有包元数据一致，第三方原许可保留；原79项注册lint全部通过。
- 原11包32项行为回归及EGO定向退出/会话/安全回归不退化。
- SITL真实动作与各子进程终态均检查，任何非零退出、异常日志或强杀都判失败。
- 偶发崩溃只有获得真实故障栈、可复现路径、针对性修复及回归，才能标成闭环。

**进度及结果**：

1. 根 `LICENSE` 使用完整Apache-2.0文本（与系统标准副本逐字比对一致），README
   说明仅覆盖自有内容。51个自有EasyFly包许可元数据统一，本轮11个lint包及新增EGO
   退出测试补齐缺失声明，署名沿用既有EasyFly Project。两个混合来源包
   gazebo_plugins/gazebo_models暂保留原元数据并登记来源核对事项；第三方目录、
   Livox驱动及RealSense嵌套仓库许可未改，不声明全仓库依赖均采用Apache-2.0。
2. source ROS/workspace，以同一官方固定schema临时catalog复跑原11包：
   **79项lint全部PASS，32项行为回归全部PASS**，未新增跳过或关闭检查。
   53个EasyFly包XML另外全部通过format3 schema，51个自有元数据一致、2个例外保留。
   证据：`log/test_2026-10-05_10-39-30/`；测试耗时1min18s。
   EGO另复跑退出、初始采样、会话、managed故障及四项安全测试，**8/8 PASS**，
   耗时17.08s，证据：`build/ego_planner/Testing/Temporary/LastTest.log`。
3. Gazebo传感器隔离：真实RGB/深度/MID-360持续输出后，6次无GDB＋6次父级GDB
   的SIGINT均exit0、约0.264–0.314s；无飞控/PX4/MAVLink插件，无强杀。
   仅表明该隔离组合未复现，不排除高负载/其它插件组合。
4. 新增完整基础SITL：EGO与Gazebo同时父级GDB，Takeoff/Land真SUCCEEDED、最终
   disarmed；8个D4节点及核心全体正常退出，launch0且日志无子进程异常/强杀。
   软件配对1919、预测351、非空着色72、类别关联367、tag有效空帧550；
   ROI第一次接受，tracking10后lost8。未宣称真实标签、精准降落或持续跟踪性能。
5. 进一步定位旧Gazebo加载事故（07:53:21/PID74082）：同PID重复相机节点错误，
   原core在QoS地址0x3a0解引用；实际调用者栈中ros_node_原始指针确认0x0。
   已安装相机库计算成员偏移0x3a0，与官方重名返回nullptr后无判空的代码一致。
   **确认空指针崩溃路径，具体重复加载来源仍待核对**；它不是退出self-join事故。
6. 新增 `scripts/shutdown_capture.gdb` 可复用捕获栈/线程/寄存器。正常子进程保留
   返回值，崩溃或异常停止显式exit1；默认不生成大core，显式启用才生成、拒绝覆盖。
   正常true与独立shell自发SIGABRT分别验出0/1，夹具验收不算平台行为验收。

**未闭环项**：EGO停止SIGSEGV、Gazebo停止boost self-join仍无真实故障栈。
本轮未改这些未定位的组件，也未升级/覆盖ROS/Gazebo/PX4安装。后续优先真实栈
捕获＋最小复现；如需系统依赖补丁采用单独可回滚overlay，升级/迁移另确认。

证据：[12次传感器退出](/tmp/easyfly-gazebo-isolation.JmdRLF/results.log)、
[完整SITL观测](/tmp/easyfly-full-shutdown-check.TbFaKs/observation.log)、
[完整日志](/tmp/easyfly-full-shutdown-check.TbFaKs/console.log)、
[旧core寄存器](/tmp/easyfly-gazebo-registers.Vum5jj/registers.log)、
[实际空节点指针](/tmp/easyfly-gazebo-registers.Vum5jj/camera-node-pointer.log)。
本轮解包生成的3.6GiB临时CoreDump在完成寄存器核对后已删除；原始apport报告
与文本证据保留，可随时从原报告重新解包。
详见[退出诊断](docs/development/shutdown-diagnostics.md)与[许可说明](docs/development/copyright-options.md)。
本轮未提交git，D5、G9以后与实机未执行，用户既有.codex改动及codex_cli.sh删除保留。

### 10.12 有边界的启动/退出/飞控专项审查（2026-10-05）

**执行目标**：按用户确认完成一轮有边界的专项审查，只修有源码证据的缺陷。
主agent负责SITL启动防重、集成验证和记录；coder负责飞控补丁和定向测试；
reviewer独立只读审查。不开启G9以后的复验、不升级系统依赖、不盲改历史崩溃组件。

**验收标准**：

- 第二个单机SITL入口在创建任何子进程前拒绝；不连接/终止已有服务，不因残留锁文件误拒绝。
- Gazebo/PX4提前退出或模型生成失败使launch失败并停止后续启动，不被launch exit0掩盖。
- 模式确认及服务等待在ROS时间冻结或context退出时仍有界，退出后不追加飞控请求。
- Land不能依据本地Z推断落地并强制上锁；成功必须确认新鲜、connected、armed=false反馈。
  超时必须真实ABORTED并保留PX4 AUTO.LAND，真实CANCELED仍优先。
- 对应回归和一次正常基础SITL均检查真实动作终态与所有子进程退出；强杀或异常日志不算通过。

**进度及结果（本轮完成）**：

1. 已修复ROS时钟冻结时模式确认无限等待、Land低Z超时强制上锁且忽略失败的
   两项确定缺陷。模式等待和arm/mode服务等待均steady有界且检查context；
   服务超时/退出清理pending。Land移除所有按Z猜落地的强制disarm与伪成功，
   使用steady超时、同锁状态/接收时间快照的新鲜connected/armed=false确认。
   超时真实ABORTED、保留AUTO.LAND，取消仍以真实CANCELED确认优先。
2. 两个SITL入口共用UID级内核锁，启动前预检本地Gazebo TCP、PX4 TCP4560、
   MAVROS UDP14540，拒绝远程/无效master，不连接或停止已有服务。锁保持到
   context销毁，残留文件无锁时不误拒绝；关键进程失败/提前退出显式返回非零。
   即使ROS domain/Gazebo端口不同也拒绝第二个单机入口，因其它端口仍固定。
3. 两包定向build通过；飞控4项登记CTest全部通过，JUnit共14个用例
   （旧6＋新6项gtest＋2项真实节点pytest）。覆盖冻结正Clock、context退出、
   正常5s服务响应超时和退出时pending清理、低/负Z仍armed、旧/断连false、
   新鲜false成功及取消与过期deadline重叠。SIGINT/SIGTERM真实退出均exit0<2s。
4. SITL包3项登记CTest全部通过，新增session_guard的9项unittest覆盖真实
   TCP/UDP占用、跨进程锁、残留文件、失败释放、安全目录、启动动作前预拒绝、
   关键进程运行中/Shutdown后异常退出、延迟动作取消及CLI参数可见性。
   新Python文件copyright/flake8/pep257及新C++测试cpplint/uncrustify通过；
   两包package.xml通过原固定官方schema/catalog校验，全工作区diff-check通过。
5. 独立reviewer对飞控与启动防重补丁未发现阻塞/新增回归，独立回跑7项初版
   guard测试及飞控新增CTest；其两项非阻塞补测建议均已实现并通过。
6. 本轮仅一次完整基础SITL，CPU/headless/best_effort、domain121/master11355、
   隔离PX4 rootfs、EGO/Gazebo父级GDB。Takeoff/Land真实status4/SUCCEEDED，
   hover z=.875854m/vz=.063724m/s、armed/OFFBOARD，最终确认disarmed。
   八个D4节点与核心全部exit0；观察器exit0，无process has died/SIGKILL，无残留。
   软件配对1841、预测351、非空着色134、类别关联318、tag有效空帧469；
   ROI第一次接受，tracking有效9后lost22。没有实际标签位姿/精准降落或持续跟踪验收。
7. 首会话运行期间实际调用两种已安装入口：perception同master/domain与px4不同
   master/domain均exit1，未创建任何子进程，原Gazebo/PX4/飞控PID仍存活且随后
   起降成功；退出后实际重新取得锁并预检三端口成功，验证正常释放和可复用。

**验收结论**：上述专项标准全部通过，本轮有边界审查/修复完成。新鲜armed=false
只确认飞控已上锁，不是独立接地或AGL证据。内核锁只对同UID协作入口原子防重，
非协作进程仍可在预检后抢占；模型生成命令exit0不代替传感器/飞控就绪检查。
不将防重声称为旧相机重复加载来源的定位，也不标记历史EGO SIGSEGV/Gazebo
self-join已修复。那些事故仍需真实故障栈；本轮没有擅自扩大排查或升级系统。

证据：[本轮SITL观测](/tmp/easyfly-bounded-safety.Em5JCK/observation.log)、
[完整日志](/tmp/easyfly-bounded-safety.Em5JCK/console.log)、
[两入口实际防重](/tmp/easyfly-bounded-safety.Em5JCK/duplicate-launch.log)、
[飞控回归](build/easyfly_flight_control/test_results/easyfly_flight_control/)、
[启动防重回归](build/easyfly_px4_sitl/Testing/Temporary/LastTest.log)。
契约与操作边界同步至runtime-contracts.md、shutdown-diagnostics.md；plan-v3.md
更新D4当前状态，保留10.9–10.11历史失败记录。未提交git；D5、G9以后与实机未执行，
用户既有.codex改动及codex_cli.sh删除保留。

### 10.13 反馈失效与外部接管专项修复（2026-10-05）

**目标**：继续有边界审查，修复起飞失败主动上锁、过期/重复状态伪到达、旧降落
取消抢回外部控制权的确定缺陷。主agent负责桥接停流链与集成/记录，coder负责飞控，
reviewer只读审查。本轮不做G9以后复验、实机或系统升级；保留所有用户已有改动。

**用户决策**：状态超过1秒无更新、断连或定位无效时，终止动作并停止本平台setpoint，
由PX4自身已配置的失控保护处理，不自动返航、降落或上锁。恢复反馈不自动恢复旧动作。
已发送arm/mode服务结果不明时保留飞控/桥接故障锁，拒绝后续飞行动作；人工核查
原请求不再待执行及远端状态后再重启相关控制节点，不以新鲜反馈自动解锁。

**验收标准**：

- Takeoff失败/接管后不发送缺乏接地证据的disarm，不继续发arm/OFFBOARD；模式与
  解锁必须由新鲜实际状态确认，不能只信服务接受。
- 四Action准入及模式/到达确认拒绝失效反馈；Waypoint/Trajectory需新的观测推进
  到达计数，同一条缓存被多个timer tick消费不得伪成功。
- 运行中失效真实终止并停流，取消不能以恢复hover之名绕过门控；外部RTL/MANUAL
  接管后的旧Land取消不重新OFFBOARD，也不伪报正常取消恢复。
- 桥接遥测fresh与setpoint watchdog必须在ROS时钟冻结/回退时仍有效；实际MAVROS
  setpoint停止，而非只检查上层不发。新增定向回归需验证补丁前失败、补丁后通过。
- 原相关回归、独立只读review及一次基础SITL/反馈故障联调检查真实终态与退出。

**进度与实现结果**：本轮定向修复、行为回归、基础SITL及最终独立只读审查已完成。

- 飞控移除Takeoff准备失败时的自动disarm；arm/OFFBOARD副作用前重查当前UUID、
  新鲜状态及模式所有权。实际OFFBOARD与armed反馈确认后才进入爬升；失效、取消或
  外部接管后不追加补偿命令。初始未解锁且模式已知的MANUAL/残留LAND仍允许显式起飞，
  未知模式拒绝。
- 四Action在goal和accepted阶段均校验状态：steady接收年龄不超过1秒，正且合法的
  header时间，ROS源年龄在[-0.2, 1.0]秒内，以及连接、姿态/定位和数值有效性。
  Waypoint/Trajectory到达计数只由新的UAVState接收序号推进；这是聚合观测，不能
  声称为五个独立原始传感器采样。Land完成要求新鲜可信的已上锁反馈，可不依赖定位。
- 运行中失效/接管终止动作并停流，恢复反馈不复活旧动作。Land取消前、等待期间及
  请求恢复OFFBOARD前重查实际模式；外部RTL/MANUAL接管不会被旧取消抢回。
- Reentrant动作回调以UUID、goal handle及在途事务标记保护动作槽；取消先停流，
  已发本地arm/mode事务需返回或到达steady期限后才释放本地动作槽。未知远端结果
  另由持久故障锁保护：公开CANCELED或本地future清理不等于远端命令已撤销。
- 桥接遥测有效期和setpoint watchdog同时检查ROS时间与steady接收时间；冻结、
  回退时钟不能让旧状态/命令永久有效。默认运动1秒、慢遥测5秒、RC1秒、setpoint1秒；
  接收新鲜度不等于硬件采集时间保证。三个可配置超时必须有限且为正，启动时生效。
- 桥接服务发现/响应分别用steady 3秒/5秒期限并响应context退出；未发送或明确拒绝
  不误锁，已发送但结果不明以`command_result_unknown:`标记。飞控与桥接均保持故障锁，
  桥接拒绝后续arm/mode且停setpoint；迟到响应或新鲜遥测不会自动解锁。

**验证结果**：

- 飞控构建通过；5个注册CTest全部通过，对应29个实际JUnit案例：原6个gtest、
  20个FlightSafety、2个真实节点SIGINT/SIGTERM退出、1个完整停流链pytest。
- 桥接构建通过；3个注册CTest全部通过，含8个BridgeFreshness gtest、2个真实节点
  在途服务退出pytest、3个静态仿真时钟契约案例。新增定向测试文件版权、
  C++格式/cpplint及Python flake8/pep257检查通过；`git diff --check`通过。
- 桥接A/B：使用HEAD原桥接源码在独立临时目录编译，同一组冻结遥测、冻结旧setpoint、
  回退时钟案例补丁前3/3失败，当前实现通过。飞控没有保留本轮开始前的脏工作区快照，
  因而只记录源码反例及真实补丁后回归，不将HEAD旧阶段冒充其准确前版。
- 完整停流链使用真实flight/bridge节点与fake MAVROS，在持续正冻结Clock下停止原始
  遥测：Waypoint真实ABORTED，实际MAVROS setpoint在watchdog/传输排空后停止；
  不发补偿disarm，恢复遥测不恢复旧输出，后续不符合条件的goal拒绝，两节点退出0。
  fake动力学不作为实飞精度证据。
- SDK的9个行为gtest通过，Mission FSM的6个注册CTest通过（含真实子动作终态与
  ownership回归）。额外SDK全包lint不通过：5个文件缺版权、169项cpplint问题、
  5个文件uncrustify失败；为既有自有代码问题，本轮未混入大范围格式改写。
- 一次CPU/headless/best_effort真实SITL通过：Takeoff和Land均SUCCEEDED且success=true，
  悬停z约0.912米、vz约0.033米/秒，最终确认已上锁；核心launch及8个D4侧进程均退出0。
  EGO与Gazebo的GDB inferior正常退出，未发现SIGSEGV/SIGABRT/SIGKILL或process-has-died；
  退出后会话锁与端口复用检查通过。本次不是G9以后长循环，也未实飞Navigate/ExecuteMission。
- 最终reviewer逐段检查在途请求、取消、Reentrant所有权、外部接管及故障锁，
  未发现本轮新增阻塞缺陷或可确认回归；结论仅限本轮范围。

**排查过程保留**：新测试初期出现Humble回调类型不兼容、测试executor启动竞态及fake
MAVROS协程退出排空问题，均修正测试夹具后重跑；曾挂起的自有pytest包装进程已清理，
不能将首次超时记作通过。首次联调observer就绪早于飞控DDS/Clock就绪导致goal拒绝，
补齐夹具同步后通过，未放宽生产准入。基础SITL之后生产逻辑未再改动。

**证据与验收结论**：本轮定向验收通过，全仓lint和历史退出故障仍未闭环。历史
EGO stop SIGSEGV、Gazebo boost self-join/相机空指针路径不能由一次正常退出关闭；
精准降落、实机及D5未执行。契约已同步runtime-contracts.md，plan-v3.md保留这些边界。
未提交git；保留用户既有.codex修改、codex_cli.sh删除和其他阶段未提交内容。

证据：[飞控结果](build/easyfly_flight_control/test_results/easyfly_flight_control/)、
[桥接结果](build/easyfly_mavlink_bridge/test_results/easyfly_mavlink_bridge/)、
[任务回归](build/easyfly_mission_fsm/test_results/easyfly_mission_fsm/)、
[SDK行为与lint结果](build/easyfly_core/test_results/easyfly_core/)。
本轮SITL记录位于`/tmp/easyfly-feedback-safety.PxcEze/observation.log`与`console.log`，
桥接前版反例位于`/tmp/easyfly-bridge-prepatch.7pYPht/prepatch.log`；临时目录非长期归档。

## 11. D5：云台与精准降落（2026-10-05开始）

本节表格和末尾SITL23为当前签收状态；中间逐轮记录保留当时进度与失败，
其中“继续执行/尚未签收”不覆盖后续结果，也不删除历史问题。

**目标**：按用户授权开始D5第一版仿真功能链。主agent负责范围决策、接口、
坐标/降落策略、飞控/SDK/任务集成、验证及记录；coder负责云台实现及定向回归；
reviewer在实现后只读评审。保留D4及安全修复未提交内容和用户.codex改动；
不自动提交git，不开展G9–G11、真实设备协议或实机验收。

| ID | 工作与验收标准 | 进度 |
|---|---|---|
| D5-01 | 云台统一设备抽象、角度/速率限位、真实状态与通信超时；模拟后端故障注入及恢复不复活旧命令 | 模拟实现与组件验证完成，无硬件协议 |
| D5-02 | 显式目标身份跟踪；有效odom目标/UAV姿态转换为FLU角度；仅控制云台，不驱动飞机 | 实现与模型/真实ROS回归完成 |
| D5-03 | 固定相机外参、源时间与车辆姿态配对，将LandingTarget转换为odom降落板位姿；光学Z不冒充离地高度 | 实现；几何/时钟/实际转换节点回归通过 |
| D5-04 | 获取→对准→有条件下降→普通Land语义收尾；全程飞控单动作槽，无第二setpoint出口 | 组件/生命周期通过；SITL23小板、原30Hz、显式DDS及.6/.5m区间完整链通过 |
| D5-05 | PrecisionLand长时Action，真实反馈/取消/终态；TriggerLanding仅兼容启动；SDK/任务接入 | 实现与回归通过；SITL23正式YAML经任务层/SDK完成3步、真实成功与精确排空 |
| D5-06 | 标签失效、时钟异常、超时、取消、接管及故障锁定向回归；固定标签短时仿真与退出记录 | 定向回归通过；SITL23限定仿真签收，所有进程正常退出；历史失败与未覆盖项保留 |

**用户已确认**：固定下视相机/静止36h11标签板；云台仅模拟且不参与动态相机外参。
标签丢失立即停止下降，可信且仍拥有OFFBOARD时悬停/重获后重新对准，长期丢失失败，
不盲降/返航/上锁。外参/尺寸/下降边界必须显式有效；稳定低高度才普通Land收尾。
handoff后取消沿用普通Land，只在确认仍拥有新鲜AUTO.LAND时恢复OFFBOARD，
外部接管或未知命令结果停流/保锁，不抢回控制权。

**实现结果**：

- 新SetGimbalTracking、PrecisionLand、LandingGuidanceTarget；LandingTarget新增
  tag_size_m元数据，Land Goal新增内部precision_landing_session_id默认空字段。
  消息与受影响包同步构建；普通客户端不得伪造内部会话。迁移需重新编译。
- 云台设备抽象＋限速模拟后端；FLU度数角度，显式身份目标结合完整姿态转换；
  失效/失联停止并禁用旧跟踪，恢复不复活；角度服务成功仅是接受，非达到。
- 固定外参含杆臂，原图像时间与新鲜UAV状态配对，输出odom中心/单位法向与
  原光学source_header；frame/ID/尺寸/倾角/plane约束一致。原光学Z不当离地高度。
  ROS＋steady期限、正时间戳、重复源/时钟冻结回退失效，不重新打戳续命。
- PrecisionLand在现有飞控持有全程父动作槽，是唯一业务setpoint出口；策略本身
  不输出命令。真实内部普通Land收尾前多阶段重查，取消只取消所属子Goal。
  精确UUID查询只有RELEASED证明动作排空；远端mode结果不明的全局故障锁独立保留。
- TriggerLanding只允许NaN XY/默认速度且仅报告准入；迟到准入/结果/ownership未知
  保留pending，不盲重试。C++/Python SDK和正式YAML任务接入precision_land＋显式ID，
  原legacy不扩展，不成功后追加额外Land。能力implemented和当前ready分开。
- 显式仿真launch/config、独立静止标签world与生成下视相机副本；默认不启动飞控，
  不发Goal，不修改生产Iris或旧profile自动启用。真实设备/移动板/动态外参未实现。

**组件验证与排查（当前）**：

- 精准专用包13个CTest通过：7策略gtest、9几何、配置/启动/非覆写/FOV pytest，
  两种信号各2个真实转换/gateway案例及8项lint；配置测试未执行Node或飞行。
  随后补静止标签64格/材质/理想光照XML保护，配置纯测试19项通过，最终整包结果另记。
  gateway测试覆盖迟到准入、公开终态但OWNED、错UUID与最终精确RELEASED。
- 对准每tick追随实测Z的反例新增测试在修前失败，修后保持固定高度；下降失准时
  捕获一次实测保持位，丢失/恢复需重新对准。独立review未发现该切换的阻塞问题。
- 云台19模型＋2真实节点退出/服务案例已通过；本轮xmllint间歇因远端ROS schema
  不可读取失败，单独重跑曾通过，完整重跑又失败。缓存原官方HTTP schema并使用
  XML_CATALOG_FILES后7个CTest全部通过，没有删除schema校验或修改系统环境。
  缓存SHA256为585201809cbf8c81ec5a4d7d84d827f4676dd62a4bc0a812da7a485dea2ad43a。
  飞控6精准gtest与8真实ROS案例已通过，
  包括mode在途父取消、子cancel拒绝与真实排空、5秒未知命令deadline和迟到故障锁。
  fullCTest两次随机起飞response DDS超时在启动fixture中复现；修为每case唯一实例、
  实际端点匹配连续稳定1秒、只读capabilities往返后才发首次Goal。
  没有重试任何已发送未知Goal，也未改生产准入/4秒observer/5秒服务deadline。
  修后独立8/8及完整飞控7/7CTest通过（完整60.60秒）；不证明所有高负载DDS行为。
- SDK 10行为gtest、Python绑定6行为案例、Mission FSM 6CTest（含15执行器案例）
  通过；相关检测/params/PX4 launch回归通过。SDK/绑定旧全包lint版权/格式欠账仍有，
  不将D5定向通过写成全仓lint清零。
- 首轮SITL前置模式/源时间与退出信号fixture不完整导致拒绝/重复SIGINT；修fixture，
  不放宽飞控。后轮真实Takeoff成功但no_tags；实际图像表明标签inline材质未渲染编码，
  改为Gazebo/Black/White后真实检测ID7、odom转换与align反馈出现。其后失标真实ABORTED，
  没有盲降；该轮Gazebo GDB捕获历史boost self-join异常，退出不通过。
  相机-.25试验低高度视野不足，已回-.08且补handoff视野校验；理想光照fixture禁用阴影，
  不作为遮挡/光照鲁棒性验收。当前继续完整链排查，不认定D5全部完成。

**后续SITL证据分层**：本轮evidence6真实PrecisionLand SUCCEEDED、新鲜disarmed、
水平相对观测误差约0.023m，全部launch/子节点/Gazebo GDB正常退出，但反馈只有
align/lost_hold/land_handoff，无受控descend，故不签收完整下降链。修fixture为实际
稳定1m悬停后再发精准动作、必须出现descend/handoff；evidence7进入descend但
观测间歇失效/重新对准，90秒期限真实ABORTED，退出正常。稳定门槛补connected、
有限值、ROS/steady源年龄和至少5个不同源状态，旧缓存不冒充持续稳定。
更大标签仅修改生成的测试world与显式配置；同步板平面与交接高度，不放宽生产
倾角/重投影/时钟/静止锚点阈值。放大后的倾斜板必须完整高于地面，首次未同步板高
的fixture no_tags失败保留为evidence8。

**用户确认后的高度区间修复**：evidence9在稳定1m悬停、0.4m标签、0.6m交接高度
配置下累计222次descend反馈，下降阶段最低相对高度约0.60635m，未handoff，90秒真实
超时ABORTED，退出正常；交接门槛兼作最低指令目标会依赖闭环误差穿越，标签间歇失效
也是影响因素。用户明确同意拆成显式区间后，新增readonly
`precision_descent_floor_height`，默认NaN，启用时要求有限且
`0.15 ≤ floor < handoff ≤ 1.0`。下降目标不低于观测板Z＋floor，handoff仍需实际高度
进入门槛、稳定独立观测与全部既有校验；失标/失准停止下降规则不改。floor是指令目标
边界，不保证实际飞机不下穿，也不约束捕获实测悬停或普通Land的同一高度。

修后精准包13/13CTest通过（9策略、9几何、27配置/启动/FOV/world、4实际ROS进程案例，
加8项lint）；飞控7/7CTest通过，对应44行为案例（4原控制、2导航、20安全、7精准gtest，
2退出、1停流链、8精准ROS），完整61.06秒。build两包通过；只读review未发现该增量
阻塞问题。新配置必须同步补floor，旧未启用精降的默认飞控不受影响。
证据已归档`artifacts/d5-20261005/flight-band-full-pass.log`及专用包band测试日志；
原failed logs与SITL1–9不覆盖。当前继续以0.4m标签、0.6/0.5m显式区间做最后全链验证。

**间歇重获补充修复**：evidence10在显式floor区间下进入descend，但末端横向误差约
0.194m，持续失标真实ABORTED；三组launch/全部子节点/Gazebo均正常退出。
原策略单帧有效就清losing，下一次invalid重新捕获移动位置并续期；该路径可能使
悬停点漂移，不认定它是唯一失败原因。用户确认连续五个独立有效观测才能重获后，
修改为首次失标锁定保持点和期限，invalid只清连续计数，重复时间不累计。
五帧确认前reacquire_hold，不横移/不下降；到期仍失败，第五帧不计入对准，确认后
需后续独立对准才下降/交接。新任务重置，不复活旧Goal。
新增交替有效/无效、重复帧、恢复后另行对准3项gtest；专用包13CTest全部通过
（策略现在12项），飞控7CTest/44行为案例再次全部通过（60.98秒），build两包通过。
独立review未发现该增量阻塞问题；真实全链签收仍以随后联调为准。

**异步状态配对修复**：evidence11在五帧重获策略下仍持续失标真实ABORTED，全部
launch/子节点/Gazebo正常退出。实际相机末帧离线检测仍识别ID7；该轮存在48条
source_pair_gap，无对应状态时立即丢弃观测，随后到达的匹配状态无法再配对。
新增真实转换节点用例在修改前两种退出信号下均失败，证明该异步路径缺陷。
转换节点现仅缓存最新一个待配对样本，保留原源时间和原steady接收时刻；状态到达
后仍检查原TTL/源年龄/配对间隔，不外推、不续期。等待发布invalid不提前推进飞控
源watermark；已过期样本、无效观测/状态与时钟异常均不可由迟到状态复活。
新增延迟配对与过期不复活回归，修后专用包13/13CTest通过（8.04秒，12策略、
9几何、27配置、4实际ROS进程案例及8lint）；独立只读review未发现阻塞问题。
原失败与修后日志分别归档为easyfly-d5-pair-prepatch.log和easyfly-d5-pair-final-tests.log。
完整图像SITL12单独执行，不把组件通过写成飞行通过。

SITL12仍真实ABORTED（landing_target_reacquisition_timeout），无descend/handoff，
全部launch/子节点/Gazebo正常退出；pending配对仅3条，但标签/降落观测上游过期仍
频繁发生。没有放宽时间阈值或五帧重获。新增显式诊断夹具选项unused-camera-rate=1，
只降低生成副本两个未使用的前视/深度相机频率，默认仍30；下视相机/惯量/碰撞/杆臂/
激光雷达不改，纯XML/源字节一致性两项测试通过（配置29项），相关flake8/pep257通过。
SMOKE记录有上限的原始观测时序用于后续判断，SITL13单独使用该诊断配置；其成功也
不能代替生产全传感器负载或原0.2m板的验收。

**SITL13诊断结果（未通过）**：降频副本实际Takeoff成功，PrecisionLand真实
ABORTED（landing_target_lost），无descend/handoff；三组launch及全部子节点/
Gazebo正常退出、无强制清理或异常子日志。精准动作期间下视图像90条，间隔最大
约0.198秒，上游detected 60条，但同源时间重复输入引起28条image_time_or_frame_invalid，
向下游传播invalid，打断连续重获。记录中可见有效目标后约3毫秒同时间戳的相机
输入立即失效；该轮没有逐帧内容哈希，不能据此证明所有重复图像完全相同。
因此不认定负载是唯一原因，也不修改原重复输入失效语义。已向用户询问是否仅忽略
同源且内容/尺寸/编码完全相同的重复，保持原TTL、不发新观测、不计稳定帧；异内容/
倒序/过期仍失效。等待确认期间保留现有生产行为；诊断记录追加逐帧SHA256供后续核验。
诊断fixture独立review未发现阻塞问题。D5仍部分完成，未签收完整飞行下降链。
最终精准包13/13CTest再通过（9.27秒，配置29项），source-only SMOKE脚本flake8/
pep257通过；git diff --check通过。结束检查无本轮飞控/Gazebo/PX4残留或占用端口，
未提交git，未开始D6。原始evidence12/13及最终测试日志已归档。

**用户确认重复传输例外，开始实施**：仅对同源且完整图像字段/像素相同，并且原
source age/receipt TTL/clock/calibration上下文仍有效的重复输入忽略。不得刷新原TTL、
发布新观测或累计稳定帧；同源异内容/倒序/过期/标定或时钟异常仍invalid。
coder负责AprilTag节点及反例/实际ROS回归，主agent负责SITL集成与记录，reviewer只读。
完整SITL终态验收补独立新鲜connected+disarmed证据，源年龄[-.2,1]秒与原接收年龄
不超过.3秒，不能仅以旧缓存not armed签收；无可信最终pose时不计算水平误差。
新增纯回归通过，配置/夹具测试现在30项；不改生产Land终态语义或飞行安全阈值。

AprilTag受限重复修复已实现，最多保留一个合法原始图像（像素字节上限6,220,800），
比较完整Header、width/height、encoding、is_bigendian、step和data，不凭哈希准入。
原source/receipt/clock/calibration/generation仍有效才忽略，invalid清重复资格；工作线程
在途结果不由重复输入撤销或续期。新增实际节点14项反例，旧实现identical用例失败
留证，修后全通过；包含持续推进ROS clock并更新同模型标定时原图receipt仍到期，
坏/变化标定、冻结、异内容、每项metadata、倒序、过量输入等。
AprilTag最终build通过，全包12/12CTest（19行为案例、8项lint，32.89秒）；
精准包13/13CTest再次通过（8.86秒，配置30项）。源码/完整日志归档，未跳过schema。
真实SITL14使用显式降频诊断副本，单独核对完整下降链和退出；只读review并行进行。
只读review已完成该增量，未发现阻塞问题；包括完整原始图像等值、原TTL/generation、
失效清资格、新鲜disarmed验收与诊断哈希不参与准入，审查不替代实际联调。

**SITL14降负载完整链通过**：0.4m静止板、handoff/floor=.6/.5m、未使用相机1Hz，
实际稳定悬停约.949m后，真实反馈align 150、descend 94、lost_hold 17、reacquire_hold 32、
land_handoff 97；进入handoff时实测相对板高约.59827m、水平误差约.05608m。
PrecisionLand真实SUCCEEDED，message=land complete (fresh disarm confirmed)，独立末端
connected+disarmed源年龄0秒、steady receipt约.02776秒；水平相对起始观测误差
约.05401m（不是ground-truth精度统计或板接触证明）。三组launch退出0，全部子节点/
Gazebo GDB正常，无异常子日志、强制终止或残留端口。
时序中589组源时间重复、697条重复消息，诊断哈希没有发现同源异像素；生产仍以完整
图像字段/字节判等。该结果说明受限重复例外下失标/重获/下降/真实Land闭环可工作，
不认证全负载；SITL15恢复原有两个相机30Hz单独验证，未改生产机型或安全门槛。

**SITL15原相机30Hz配置（未通过）**：同0.4m静止板/.6/.5m高度区间，未使用相机
恢复30Hz，下视相机仍30Hz、激光与物理不变，只加载D5及基础飞控节点，非完整平台算法
负载。Takeoff真实成功；精准反馈align 591、descend 75、lost_hold 153、reacquire_hold 313，
最终真实ABORTED（landing_target_lost），无land_handoff。三组launch退出0，全部子节点/
Gazebo GDB正常，无异常子日志或强制终止。
精准动作期间图像726条，接收间隔最大约.77983秒、95分位约.30266秒，已越过现有
.3秒新鲜度门槛；detected 725条，另有geometry_or_plane_invalid 24条及17条tag_pose_invalid。
该轮精准阶段未观测重复源输入，不能将其失败归为重复例外修复回归；原时间戳仍保留，
迟到/过期/不可信几何仍阻止下降。没有放宽TTL、五帧重获、板倾角/重投影或准入。
安全失败不是常规场景完成；受限重复修复与指定降频闭环签收，D5整体仍执行中。
后续需要独立排查原相机配置的帧调度/负载及间歇位姿质量，不把诊断降频设为生产默认。
SITL14/15原始结果、相机图像、源时序/哈希、日志均已归档artifacts/d5-20261005，
原失败证据保留，未提交git/未开始D6/未恢复G9-G11。

**用户要求先收口仿真，真实内容暂缓**：保留真实云台/实机/动态外参边界，继续完成
常规相机配置、有效仿真配置及正式任务端到端验证；不进入G9-G11，不自动提交git。
OGRE原日志确认使用NVIDIA RTX 5060 Ti硬件渲染，非已证实的软件渲染回退，不升级系统。
既有62幅实际相机图像以近似内参作NONE/SUBPIX离线诊断，估计倾角超过10度分别4/1幅；
未纳入实际车辆姿态、非ground-truth精度证据。生产检测启用SUBPIX窗口3并限制独立
OpenCV进程线程预算默认2（readonly，1..8），不放宽倾角/重投影/歧义/时间门槛。
新增物理像素边界/插值的已知倾角字典测试，细化误差严格低于原角点；原3gtest保留，
4gtest通过。全AprilTag12/12CTest及精准13/13CTest通过（两包42.9秒），source-only
SMOKE flake8/pep257通过，git diff --check通过。

正式SMOKE --mission实际启动mission_fsm，正式schema_version1 YAML经SDK调用
Takeoff→显式15秒hover等待→PrecisionLand，不追加Land；定时hover不是稳定证据，
首次精准反馈前必须已有实际1m±.08m/低垂速/至少五个新源状态及一秒稳定证据。
记录任务/精降UUID、任务真实terminal、三步骤complete及独立fresh disarmed。
只读review发现ownership响应未核对goal_id和跨UUID聚合的验收漏洞，已修为精确UUID
RELEASED及同一合法精降UUID上的descend/handoff，补反例测试；复审未发现新阻塞问题。
组件验证不冒充正式任务实际SITL；先SITL16正常30Hz对照此前15失败，再验证小标签与任务。

**SITL16正常30Hz指定大板完整链通过**：0.4m静止板/.6/.5m区间，前视/深度/下视
相机均保留30Hz，激光/物理未改；实际稳定hover约.95068m。真实反馈含align、lost_hold、
reacquire_hold、descend、land_handoff，全部属于同一精降UUID；PrecisionLand真实SUCCEEDED
并确认fresh disarm。独立终态源年龄.1秒、steady receipt约.03370秒，水平相对起始观测
误差约.10642m，仅单轮观测参考、不认证物理精度。三组launch退出0，全部子节点/Gazebo
GDB正常，无强制终止或异常子日志。全轮几何/板失效与tag_pose_invalid各1条，较此前15
明显减少，但两轮时长/状态不同，不宣称线程预算或角点细化是唯一因果。
常规30Hz指定场景已获得真实闭环证据，不消除原失败或认证全算法/长期鲁棒性。
证据16已归档；SITL17继续验证默认0.2m/.3/.2m配置，不放宽安全门槛。

SITL17默认小板仍真实ABORTED（landing_target_lost），只有align/lost_hold/reacquire_hold，
无descend/handoff；动作阶段仅收到6张图像，接收间隔最长约.921秒，对应源间隔.904秒。
全部launch/子节点/Gazebo正常退出，原配置未签收；不以一次大板通过推定小板可用。
SITL18首次正式任务经SDK实际完成起飞/15秒hover等待，并在精降前实测稳定约.94785m；
同一精降UUID进入descend，随后reacquisition_timeout真实失败，任务真实ABORTED，
精确任务UUID ownership RELEASED，未重复或补偿Land。
三组launch正常退出，但任务ros2 run包装根进程SIGINT未转发至实际节点，20秒后
测试夹具记录强制TERM，mission退出-15，故该轮退出也未通过。改为直接启动已安装
mission_fsm_node（原ROS环境/参数不变），根进程即实际节点；不改生产FSM生命周期。
SMOKE新增小体积CameraInfo并行源时序用于区分渲染发布间隔和大图传输丢失。
SITL19单独使用该诊断及修正后的任务启动，不作无改动反复挑选成功；证据17/18已归档。

**SITL19诊断与DDS传输边界**：任务启动后Action discovery先于内部SDK首个state callback，
唯一Goal被明确REJECTED，未发送飞行动作、未重试；直接任务节点SIGINT退出0，其他三组
launch/子节点/Gazebo也正常，包装信号问题的修正已有实际退出证据。
fixture新增首次Goal前SDK实际/uav_state订阅匹配＋新鲜地面状态/电量＋连续1秒稳定检查；
不改生产任务准入。并行记录96个不同CameraInfo源时间、26张图像，70个源只有小体积
CameraInfo，图像均能找到同源CameraInfo，信息接收95分位约.038秒，优先怀疑大载荷传输。
本机FastDDS2.6.11；官方[2.6.x共享内存说明](https://fast-dds.docs.eprosima.com/en/2.6.x/fastdds/transport/shared_memory/shared_memory.html)
记录默认segment为512KiB，并警告小于/接近数据尺寸有丢失风险；640×480RGB为921600字节。
这是诊断依据，不证明所有丢帧只由一个原因造成。
新增显式仿真d5_fastdds.xml：SHM 64MiB、最大消息4MiB、端口队列512，保留UDPv4；
仅通过SMOKE --dds-profile作用于当前隔离进程树，非系统/生产默认，不修改sysctl或安全门槛。
原schema/时间/QoS/观测源header不改。XML实际FastDDS节点解析无error，配置39项通过；
SITL20以默认小板/原30Hz及显式profile验证，与此前17失败分列。19/构建/解析日志已归档。

**SITL20默认小板＋原30Hz＋显式DDS完整链通过**：0.2m标签、.3/.2m交接区间，
三台相机30Hz、激光/物理不改，实际稳定hover约.94861m；align87、descend155、
lost_hold11、reacquire_hold18、land_handoff97，同一精降UUID。
handoff时实际相对板高约.29332m、水平误差约.05846m；真实PrecisionLand SUCCEEDED，
独立新鲜disarmed源年龄0秒、steady receipt约.02725秒，水平相对起始观测误差约.07338m
（仅单轮观测参考）。三组launch/全部子节点/Gazebo GDB正常退出，无异常或强制终止。
CameraInfo/图像全轮均1027条；精准阶段539个不同源时间一一对应，无信息-only图像
缺失，图像间隔最大约.04824秒、95分位.04115秒，未放宽.3秒新鲜度。
该实测支持大图传输预算调整有效，但不推定所有环境或无profile默认都通过。
profile SHA256=944c2d6c2a52969bef4f8b51b3d3b2b81116d9b634cd55dcdf4817a72839bce0。
只读review未发现增量阻塞，指出SDK订阅匹配只属startup辅助，仍以实际准入/终态/精确
ownership作为验收；失败18/19保留。SMOKE显式profile复制到本轮证据目录后全进程树
使用同一冻结副本，记录来源和hash，不改变系统配置；SITL21以同小板配置验证正式任务。

**SITL21正式任务首次DDS联调（失败保留）**：起飞/15秒等待后已有实测稳定hover
约.94913m，正式任务接受，精降同一UUID开始后reacquisition_timeout，任务真实ABORTED，
精确任务UUID RELEASED；任务＋三组launch/全部子节点/Gazebo正常退出0，无强制终止。
CameraInfo/图像全轮均875条，传输不再出现大图缺失；精准阶段60条selected_tag全有效，
但guidance仅24有效＋25条零源expired，个别28.684源转换在ROS 28.9/上游28.984时才输出，
约.3秒时序滞后。无几何/标签姿态invalid，不继续把该失败归为图像传输或角点质量。
coder限定增加默认关闭、readonly、1Hz转换节点内部时序诊断，不改QoS/配对/TTL/准入；
区分callback排队、配对等待与发布阻塞，先取得定位证据再修改。21原始证据归档。

**SITL22定向诊断**：新增默认关闭readonly诊断（最多steady 1Hz），实际节点两信号
回归与lint通过，未改QoS/配对/TTL。正式任务起飞/悬停及精降连续159次descend，
此前21的早期滞后未在该轮重现。最大target/state/watchdog callback约.759/.689/.437ms，
最大发布.166ms，入口源年龄state≤.1秒，稳定下降期间target通常领先当前clock约.02–.08秒。
该证据排除本轮CPU回调/发布阻塞，不凭此宣称21原因已闭环，也不改QoS。
最终相对板高约.33m时图像底部裁切标签，no_tags持续，任务真实landing_target_lost，
精确排空＋全部任务/launch/子节点/Gazebo正常退出0。末帧图像是直接裁切证据。
原FOV测试只检查handoff高度下居中的黑边，未覆盖align容差/白边/倾角及下降floor。
新增包含白边对角线、.08m对准容差、最大标签倾角和.01m边缘余量的floor视野反例，
原.3/.2m仿真配置实际失败（可用半视野约.0626m，所需约.27385m）。
在用户已批准的显式高度区间策略内，将仿真例子改为.6/.5m，提前在仍有视野余量时
交给原普通Land；不改变无配置默认关闭、实机未开放、失标停下降及源时间/几何门槛。
旧.3/.2配置与SITL20单轮通过保留，不能据一次通过证明所有对准偏差都可见。
SITL22/诊断日志/末帧与反例证据已归档；继续新配置正式任务验证。

**SITL23正式任务完整链通过（2026-10-06）**：固定下视相机、静止36h11 ID7，
0.2m黑边；三台相机均30Hz，激光/物理保持原样，独立模拟云台不参与外参。
采用显式冻结d5_fastdds.xml（hash同SITL20）与新的.6/.5m交接/下降目标下限；
转换诊断关闭。正式schema_version1任务经mission_fsm/SDK执行Takeoff→15秒hover→
PrecisionLand，实际稳定hover约.95129m，首次精降反馈前已有独立稳定证据。
任务UUID `47ea45090ce44d359db60944d8a794a6`，真实SUCCEEDED/status4、success=true、
完成3/3步；精确同UUID ownership RELEASED。唯一精降UUID
`36b48af3659a2a9ef1e2b8ba4c15f158`反馈align50、descend102、land_handoff430；
首次交接实测相对板高约.59920m、水平对准误差约.04965m。
从精降开始到首次handoff，上游标签/选择/转换各222条全部有效，无失标或几何失效；
全轮CameraInfo/图像各1657条。全轮仍有启动失效、收尾期间标签不可见及217条
geometry_or_plane_invalid，不能写成所有时段零失效，也不依赖handoff后的标签继续控制。
独立终态确认fresh connected disarmed：源57秒，ROS年龄0、steady receipt约.02175秒。
最终相对最初观测中心水平误差约.15870m，仅观测参考，非ground-truth精度认证。
任务及三组launch退出均0；全部子节点/Gazebo GDB exited normally，无强制终止、
异常子日志、仿真残留或相关端口占用。原始result/config/profile/YAML/图像/日志与
console23已归档 `artifacts/d5-20261005/evidence23/`（目录沿用首次日期）。

**最终回归与评审（2026-10-06）**：SITL结束后顺序运行AprilTag 12/12、模拟云台
7/7、精准降落13/13、任务FSM 6/6 CTest，四包共38项全部通过（约70秒）；
另行飞控7/7 CTest、44行为用例通过（约61秒）。合计45项CTest全部通过。
精准配置39用例含精确UUID验收、正式任务、DDS与floor视野反例；实际执行的包内
lint通过（下列cppcheck跳过不算检查通过），source-only SMOKE另行flake8/pep257通过，
git diff --check通过。
四包test-result分别51/36/98/33 tests、零errors/failures；其中AprilTag 5、精准2个
skip为ament_cppcheck因cppcheck 2.7性能问题跳过的C++文件检查（含tag_node/policy），
不是完整静态分析签收；行为回归无跳过，不把混合统计当纯行为用例数。
xmllint使用已缓存原官方schema的本地catalog，未禁用验证。最终测试/脚本lint日志
归档artifacts/d5-20261005/easyfly-d5-final-{tests,flight-tests,smoke-lint}.log。
readonly reviewer独立核对脚本、配置及SITL23原始证据，未发现阻塞漏洞或越界签收；
SDK签名文档已修正（Python参数形式、C++ Goal形式）。审查未替代实际测试。
SMOKE仅缩减stdout摘要中的mission_feedback数组，完整原始反馈仍保留在result.json。

**本批完成边界**：D5仿真第一版实现、定向组件验证及上述短时正式任务链签收。
显式DDS为同机仿真进程树选项，不是系统默认；默认未配置仍不启用精降。
仅加载D5与基础飞控，不认证完整平台算法负载、无profile环境、遮挡/光照/移动板、
物理精度、长期稳定性或真实设备。SITL21时序滞后未完成唯一根因闭环，SITL23
功能通过不能删除它，也不能消除历史EGO/Gazebo偶发退出失败。真实内容按用户要求暂缓；
未开始D6、未恢复G9–G11、未提交git，用户既有修改保留。

**证据**：build各包test_results；本轮原始SITL/失败图像/日志已复制至本地忽略目录
`artifacts/d5-20261005/`，避免仅依赖/tmp。先前临时证据已随环境清理，不冒充仍可读。
独立review覆盖父子生命周期、时间窗口、配置默认与补丁；只读审查不是测试替代。
当前完整图像正式任务结果见SITL23；接口/例子见[开发说明](docs/development/d5-landing.md)。

## 12. D5 后续优化：时序定位与统一仿真入口（2026-10-06）

**用户范围**：UI暂缓，仅处理此前建议的1（SITL21观测时序失败）和2（统一可复现
仿真启动）。不开展SDK全仓清理、EGO/Gazebo未定位崩溃修补、实机或G9–G11。
主agent负责取证、统一入口/信号生命周期及集成；coder限定实现隔离staging/DDS准备
与纯测试；reviewer只读核对。既有D4/D5、安全修复及用户.codex修改保留；未提交git。

| 目标 | 验收标准 | 实际进度 |
|---|---|---|
| 时序失败定位 | 区分传输、取出/回调调度、状态配对、输出队列；修复必须有反例/回归，不放宽时间保护 | 新增默认关闭完整诊断与真实任务证据；S21未重现，根因与修复仍未闭环 |
| 统一入口 | 已安装单一引擎，默认不飞；隔离rootfs、冻结DDS、一致参数、独占预留后再启控制栈、明确就绪/失败及正常清理 | 已实现；实际准备、启动、防重拒绝、正式任务、两信号退出及任务中止均有证据 |

### 12.1 时序证据，不冒充已修复

重读S21：精降阶段60条selected_tag全部有效、collector源年龄最大约.016秒；
guidance只有24有效与25零源expired，按约.34秒周期成批到达，旧源年龄最大.284秒。
这种模式不能由单条collector日志断言是CPU、DDS还是配对；原S21没有相应原生时序。
本机Humble默认Executor只返回native take tuple[0]，丢弃tuple[1]的RMW信息。
新增显式diagnostics executor仍只take一次、返回同一原消息，额外记录系统wall的
发布/接收/取出时间、callback耗时、真实原receipt配对等待及observer输出队列信息。
默认关闭；不改QoS、ROS源header、TTL、配对窗口、控制门槛或无效传播。
wall回退/缺失时间显示未知；RMW时间语义不是硬件采集时间，不参与任何安全判断。
4项纯诊断测试含单次take/空队列/分离延迟/回退，真实ROS两信号回归验证日志与保护。

S24先使用原入口及旧隔离staging定位：正式任务真实成功、3步、精确RELEASED、
freshdisarmed及全部4组退出0。target/state最长receive→take约.468/.979ms，
配对最长31.705ms，callback均不到1ms；未重现旧延迟。
S30使用新安装入口与新rootfs，完整输入/输出诊断：同一精降UUID含align53、
descend105、handoff96；精降到首次交接各229条选择/转换均有效，相机/信息也各229。
转换target/state最长receive→take约.625/.775ms，最长RMW传输.159/.154ms，
配对最长11.143ms，target callback最大.741ms。collector valid landing/guidance
发布→取出最长约13.428/12.946ms（含collector自身调度，不等同生产callback耗时）。
S30真实任务UUID `36649a1cd39948f184551609a38533f2` 成功/3步/同UUID RELEASED，
唯一精降UUID `cae0c7a1876710aab5d3610598fc62aa`；首次交接板高.59027m、误差.04585m。
独立disarmed源年龄0、receipt .02441秒；4组/子节点/GDB正常退出。旧S21未重现，
没有根因证据就不实施猜测性的QoS/超时修改，也不标为修复。后续需在同入口捕获
发生滞后时的这组诊断，才可关闭目标1；本轮不是长期稳定性或高负载认证。

### 12.2 单一安装入口与安全启动顺序

`ros2 run easyfly_sim_launcher d5_simulation`；源码sitl_smoke.py仅作转发，同一
easyfly_precision_landing.simulation引擎。默认start-only，不发飞行Goal；
--mission/--direct-action显式且互斥；--prepare-only不启动Gazebo/PX4/ROS节点。
要求现存空证据目录，以及真实ELF PX4目录或带生成manifest的staging。
真实源生成新的独立rootfs和-w/-s wrapper；原参数不复制/改写，共享Tools/etc/plugins
是输入约定而非OS只读挂载。manifest/绑定/ELF/rcS/插件重新验证，不是认证凭证。
--use-bundled-dds-profile或--dds-profile必须明确选择；校验namespace/default
participant/transport引用、UDP+SHM、图像预算含序列化余量，冻结同一副本和hash。
所有子进程继承同一profile/时钟/参数；不改系统环境或sysctl。捆绑预算仍64MiB/4MiB。
生成跨节点配置先验证；先simulation独占marker及新clock，再检查旧ROS图，之后才
bridge/precision。marker只来自本轮新日志；父进程检查simulation存活，拒绝失败不再
立即启动可能连接旧会话的桥接/飞控。D5_READY为地面启动证据，不是飞行或感知准入。

**实际集成**：

- S25：已安装ros2run入口默认仅启动，20秒观测后exit0；actions空、无uav_command，
  地面未解锁，3组/子节点正常退出。新rootfs可直接使用，不依赖旧参数复制。
- S26：S25存活时第二入口真实拒绝，exit1，只失败的simulation组，无bridge/precision
  子组/Goal；原会话继续正常，拒绝证据保留。
- S27：同一已安装入口、新rootfs、诊断默认关闭，显式mission真实成功3步、
  精确RELEASED、freshdisarmed，4组/子节点/GDB退出0。UUID
  `6e9de4fe0df943fc9e2c6bb9059a054f`；receipt .03291秒，源年龄0。
- S28/S29：原生安装入口在READY后SIGTERM/SIGINT，前者exit1/中止、后者exit0/正常停；
  两轮均actions空、3组/子节点退出0，无残留。SIGTERM不再默认跳过finally留下子会话。
- S31：真实任务hover步骤收到SIGTERM，精确所属Goal真实CANCELED/status5，
  UUID `1a1ea72d36734eb1b20a9ad4097848e9` 的ownership确认RELEASED，入口exit1；
  未追加Land/precision，4组/子节点退出0。任务取消不记为成功或freshdisarmed。
- S32：安装入口prepare-only实际生成config/world/model/manifest/profile，未启动ROS
  或仿真节点。正常/错误模式验证另有纯测试。

入口自己处理SIGINT/SIGTERM，保留ROS context用于精确取消/排空，有界关闭自己的
子进程后检查exit/异常日志，cleanup期间抑制重复中断。服务管理器应运行原生安装
可执行文件或信号整个进程组，不假设ros2run包装PID会转发SIGTERM。永久无响应、
准入未知、handoff阶段信号中断未以S31签收；旧组件生命周期反例继续保留。

**开发过程与验证边界**：第一次新增runtime依赖放在precision包造成mission/flight
循环，构建明确失败，改将高层依赖/安装入口放sim_launcher后构建通过。首次包级lint
扫描到coder未完成新文件的中间态失败，完成后重跑。启动测试原4个失败是既有guard
包装遮住只读遍历，改只检查受管closure的声明actions，不执行guard或任何进程。
不删除测试，不将初次失败改写为通过。最终构建、相关包回归和评审结果另列于下。

**最终验证**：三包构建通过；精准包15/15、SITL包3/3、sim_launcher包1/1，共
19项CTest全部通过（最后重跑约11秒）。含46配置、24隔离准备、4诊断、9几何、
12策略及两类真实ROS各2用例；sim_launcher 9只读profile用例通过，防重实际测试保留。
精准test-result为141 tests/0 errors/0 failures/2 skipped，后两项仍是cppcheck2.7
工具跳过的C++文件检查，不宣称完整静态分析通过；其它两包为3/9 tests零失败。
注册实际执行lint及安装入口flake8/pep257、两包XML原schema/catalog通过，diff-check通过。
安装入口无.py后缀，独立copyright CLI未扫描它（0 files），不把此结果当版权检查通过；
文件内完整Apache-2.0声明已核对。默认长驻启动的flight/command/observation采样上限
各10000，编号图像最多100份、latest持续覆盖，避免启动模式无界增长；图像只解码一次。
最后仅日志准入UUID与捕获边界变化，不改变飞行逻辑，不据此关闭S21。
退出后定向确认无所属Gazebo/PX4/飞控/任务节点或端口残留。最终只读review核对
S30/S31证据及源码/文档，无新增阻塞；实际测试与审查分开记录。

**证据**：本地忽略目录 `artifacts/d5-optimization-20261006/` 收纳S24–32各轮
原始result/冻结配置/profile/图像/日志及构建、测试日志。无UI开发、实机、系统升级
或git提交；目标1仍未闭环，目标2仅限定本机短时仿真，历史问题保留。

### 10.10 D4 独立验收（2026-10-06，ZCode 受权执行）

验收基线：工作树 D4+D5 改动（HEAD=87ac9e5/D3，共 207 项变更）。

**新鲜度异常与处置**：验收时 10 个 D4 包源码晚于最后构建约 3 小时（用户 10:38 的后续修改）。重编全部 11 包（rc0 15.3s）后复测——当前源码状态确认。

**行为复跑（重编产物，独立 domain 63）**：

| 包 | 结果 |
|---|---|
| easyfly_time_sync | ✅ 2/2 |
| easyfly_camera_calib | ✅ 2/2 |
| easyfly_target_prediction | ✅ 2/2 |
| easyfly_single_object_tracking | ✅ 3/3 |
| easyfly_apriltag_detection | ✅ 3/3 |
| easyfly_landing_detection | ✅ 3/3 |
| easyfly_lidar_camera_fusion | ✅ 4/4 |
| easyfly_semantic_map | ✅ 6/6 |
| easyfly_perception_srvs / easyfly_params / pixel_to_3d frame 契约 | ✅ 1/1、1/1、1/1 |

合计 25 项行为 CTest 全过（与 §10.7 声明一致）。

**发现并定位一处测试失配（非 D4 回归）**：配置 pytest 38 项中 4 项 FAIL（`test_nested_launch_effective_parameters`×4 profile）。根因：D5 引入的 `session_guard.guarded_launch`（perception_sitl 会话守护）把动作包进 `OpaqueFunction`，仅真正执行时展开；测试的只读 `nested_entities(expand_include(...))` 遍历不执行 OpaqueFunction，故找不到嵌套 `local_planner.launch.py`（D0-D3 期 perception_sitl 为裸 LaunchDescription，遍历可达）。属 **D5 演进与 D0 期契约测试的结构性失配**，非 D4 功能回归——D4 八包行为测试与该失配无关。该失配需后续单独收口（更新测试以展开 OpaqueFunction 或按 guarded_launch 结构适配）。

**结论：D4-01~D4-07 验收通过**（软件边界同 §10.8：不含 SITL 负载全链、真实视觉/外参精度、lint 全量）。

### 11.x D5 独立验收（2026-10-06，ZCode 受权执行）

**组件复跑（重编产物，独立 domain 64）**：

| 套件 | 结果 |
|---|---|
| easyfly_landing_detection（策略/e2e/clock_ros/landing_ros） | ✅ 3/3（3.19s/3.35s/2.81s） |
| easyfly_apriltag_detection | ✅ 4/4 |
| easyfly_gimbal_control | ✅ 2/2 |
| easyfly_flight_control（全 7 CTest，含精准 ROS 案例） | ✅ 7/7 |
| easyfly_mission_fsm（全 6，含 15 执行器场景） | ✅ 6/6 |

**SITL23 归档证据核对（artifacts/d5-20261005/evidence23/，67 文件）**：result.json 逐字段与 §11 记录吻合——`/execute_mission` status=4、success=true、UUID `47ea45…`、completed_steps=3/3；precision UUID `36b48a…`；ownership **RELEASED**；反馈分布 align 50 / descend 102 / land_handoff 430；hover 0.951m、precision_started_after_stable_hover=true；final_disarmed=true、ros_age=0、receipt_age=0.022s；final_horizontal_error 0.159m（仅观测参考）；child_exit_failures 四类全空。相机序列图像 270+ 张在档。

**结论：D5-01~D5-06 按记录验收通过**（边界同 §11："D5 仿真第一版"+SITL23 签收；SITL21 时序滞后根因未闭环、历史 Gazebo 偶发退出等保留项如实维持；真实云台/实机/动态外参/G9-G11 按用户决定暂缓）。

**D4/D5 共同遗留**：配置契约 4 failed（guard_launch 结构性失配，见 §10.10）待收口；D3 四项 lint 欠账延续；全部改动（D4+D5，207 项）未提交。

## 13. 不飞行时序定向复现：取出前排队口径缺口

**范围**：用户授权继续定位消息突发、回调延迟及车辆状态迟到。只启动真实观测节点
和合成ROS输入，不启动Action/飞控/PX4/Gazebo/图像或全系统压力，不进行G9循环。
主agent负责回调阻塞/突发及证据判断；coder只新增迟到配对测试，reviewer只读审查。
本节保留其他代理追加的历史验收，不改写其原结论。尚未提交git或开展UI。

**用例与结果**：

- 三个实际安装LandingTransform迟到状态用例PASS（约3.01秒，domain198）：在原TTL内
  匹配可以输出原stamp；原steady receipt超过.3秒而ROS-age仍有效时不能由迟到state
  复活；连续新target仅保留最新pending，跨.1秒配对窗口的旧state不能倒序输出或续期。
  三个子节点单次SIGINT正常exit0，保留原始输出与日志。
- 系统时钟＋test-only aux callback阻塞.45秒，DDS接收线程继续运行：目标RMW
  receive→take约450.84ms，取出时ROS source-age约.451秒，输出invalid，随后新目标恢复。
  证明诊断能够辨别本地读者排队；不把人为阻塞当原S21同因。
- 8条突发＋.18秒阻塞：实际depth1 reader仅取到最后一条，receive→take约179.72ms，
  输出仍用原stamp，后续新观测正常；无积压倒序输出。保持现有QoS不变。
- **0.1x合成ROS时钟＋.45秒阻塞：反例FAIL，缺口已复现**。目标源
  10018642535ns，实际RMW receive→take约450.785ms，callback ROS-age仅.045053秒，
  随后实际发布该原stamp的valid guidance。当前steady receipt在callback入口重新开始，
  没有包含取出前等待；慢ROS时钟使ROS-age不能替代这段steady排队年龄。
  三案例合跑为2 PASS/1 FAIL（约5.26秒）；不将失败改为跳过或通过。节点仍正常exit0。

已核对本机FastDDS实测：一条消息发布后不take .4秒，received timestamp仍在发布附近，
不是取出时刻；[rmw_fastrtps 6.2.10官方源码](https://github.com/ros2/rmw_fastrtps/blob/6.2.10/rmw_fastrtps_shared_cpp/src/rmw_take.cpp)
将SampleInfo的source/reception timestamp转为RMW信息。诊断时间依旧仅作软件取证，
不因这个反例把系统wall时间改成飞行准入依据，也不宣称硬件采集时间有保证。

**结论及待确认策略**：已找到“callback接收TTL不包含本地读者队列等待”的可复现
边界；尚不能证明S21的原始周期性延迟由同一机制导致。reviewer确认这是一处TTL口径
缺口，稳态source/receipt检查本身未被本轮修改。候选修复是在本地steady处理连续性
超限时清空证据并保守隔离，不能仅靠watchdog检查，因为state/target可能先被调度。
只建立ROS source屏障也不足以证明future/旧队列样本新鲜。已询问用户：超限后是否
重建volatile观测订阅、清旧队列并重新获取，或保留观测故障锁直到人工重启。
在恢复策略确认前未修改生产行为；新反例暂未注册进默认CTest，保留独立命令的FAIL
作为修复前证据，不将当前默认检查通过冒充这个新保护已实现。

**产物**：新增test_timing_pair_ros.py、test_timing_queue_ros.py及不安装的
timing_queue_fixture.py；三文件flake8/pep257通过。所有节点/输入均只在隔离domain，
未运行任何飞行动作。原始queue与pairing evidence.json/node.log、独立pytest日志归档
`artifacts/d5-timing-reproduction/`，不得仅依赖/tmp；下一步按用户选择实现并要求同一
反例由FAIL变PASS，再回归原保护。

### 13.1 用户确认后的修复与验收

**目标与决策**：用户回复“按你的建议来”，采用自动恢复：本地steady处理超限时
清证据、重建volatile观测订阅以隔离旧队列，再获取新观测。不采用人工重启观测锁，
不引入RMW wall准入、不扩大TTL、不重打时间戳。本节前述“待确认/未修改生产”是
修复前的历史记录，当前以本小节为准；S21唯一根因仍未闭环。

**实现进度**：主agent实现LandingTransform处理连续性门与reader generation，
coder新增7项真实Node受控时钟测试；主agent集成并补4项负向/查询边界，reviewer
只读复核。state/target/watchdog首先检查steady间隔，超过原source_age（默认.3秒）
或出现负间隔时，拒绝触发样本并清states/pending/last_good/receipt，发布
`receiver_processing_gap`，重建原depth10/1、原可靠性、显式VOLATILE的订阅。
旧generation回调没有副作用；已处理source水位不倒退，正常查询不续处理期限。
不用排队ROS now作为采集屏障，新reader重新配对仍须通过原source/receipt/几何准入。
控制层失标停下降、首次失标悬停位置、5帧重获、超时及取消规则未修改。
重建异常传播并停止观测节点，不静默保留有效旧目标。

**验收标准**：

- 原慢时钟＋.45秒处理阻塞的旧目标不得输出valid；新generation的新观测可恢复。
- 诊断关闭使用普通SingleThreadedExecutor、开启使用诊断executor，两种均成立。
- 原.18秒/8条burst保留最新原stamp；迟到state不能复活过期/倒序证据。
- 三入口都可触发隔离；退休回调不清/续新证据；查询不续期；重建失败不发布valid；
  future触发不污染水位、负steady间隔隔离；原TTL内不重建。
- 新测试注册默认CTest，原观测与飞控组件回归及实际执行的lint不新增失败。

**已执行结果**：重新构建观测包成功。真实ROS队列6项通过（约4.37秒，domain199），
包括普通/慢时钟阻塞及burst × 诊断开关；真实安装节点迟到配对3项通过（约2.95秒，
domain198）。真实Node、不spin、可控steady/ROS时钟的恢复11项通过（约.21秒，
domain202），不是飞控或SITL测试。观测包全18项CTest通过（10行为套件＋8 lint），
其中cppcheck原有2项工具跳过仍保留，不宣称完整静态分析通过。
飞控组件全7项CTest通过（约60.67秒），覆盖既有安全、取消/停流与精准动作组件案例，
无PX4/Gazebo后端。两包colcon test-result分别187项/51项、0 errors/0 failures，
观测包保留上述2 skipped，飞控无skip；这是结果文件统计，不与CTest套件数混用。

**测试失败也保留**：首轮修复后2项因旧oracle只接受source_invalid理由失败，实际
已输出receiver_processing_gap并丢弃旧reader，调整为检查明确重建理由与旧源不valid。
注册CTest后首轮慢时钟2项在一次性baseline前没有消费第一条/clock而超时；单次查询
尝试又实测返回header=0。最终先用真实服务响应确认child clock>=10秒再发baseline，
未改生产门槛、未重发旧stamp、未跳过失败用例。原2 PASS/1 FAIL的缺口复现、
中间测试失配/启动竞争及最终通过日志均保留，不用最终通过覆盖历史失败。

**边界与证据**：独立只读审查未发现阻塞性安全回归；审查不是实际执行结果。
按reviewer建议，额外收紧burst断言为旧输入仅末帧被实际取出/输出，保护depth1语义。
收紧后观测包再次全18项CTest通过（约18.65秒），结果仍为187项零失败、2工具skip。
修复只隔离本节点处理中断后的旧reader队列，不证明上游队列/硬件采集时间可信，
也不覆盖全部传输延迟。持续处理超限仍可能导致保守失标或失败。不把该局部缺口
修复写成S21唯一根因已修复。本轮未启动PX4/Gazebo，组件Action使用合成反馈，
未执行SITL或实机飞行，无UI、实机、G9循环
或git提交。修复前后日志、最终队列/配对evidence.json与node.log归档在
`artifacts/d5-timing-reproduction/`；中间/tmp目录部分已被pytest正常轮换，其完整
pytest日志仍在归档，独立node.log以最终归档为准。

## 14. 下游guidance时序保护与观测重建控制链

**目标/范围**：用户授权执行第1、2项定向验证，并按先前说明在组件通过后做一次
短时正式任务SITL开发检查。第1项确认飞控reader等待是否使旧guidance续期并修复
反例；第2项签收观测重建后的停止下降、首次hold、5帧重获后重新对准及持续失标
终态/精确释放。UI、真实设备与G9–G11继续暂停，不进行飞行自动重试或冷启动循环。

**分工与进度**：主agent负责实际DDS C++队列测试、生产保护、负向边界、集成和记录；
coder仅新增test_precision_receiver_chain.py，实际transform/飞控配显式合成反馈；
reviewer完成一次只读生产增量审查，要求补goal_id匹配与负向边界，随后额度中断，
不将其写为最终独立审查全部完成。主agent落实建议并复核。未提交git。

**确认的反例与实现**：新test_precision_queue.cpp实际使用FlightController、DDS及
4线程MultiThreadedExecutor，不发送飞行Goal。test-only同state_cb_group阻塞.45秒，
慢ROS时间仅推进.045秒时，源10001000000ns被旧回调设置新receipt并判ready=true。
修复前3案例2PASS/1FAIL（约1.21秒）：正常速度时钟可拒绝，慢时钟失败，.18秒8条
burst消费末帧正常。最初fixture缺显式speed/align参数的构造失败单独留档，不算反例。

飞控在同接收callback group增加50ms进度watchdog，guidance callback与watchdog均
取得flight_mtx后检查steady间隔，其他组的控制timer不能掩盖接收组阻塞。超过原
target_max_age（默认.3秒）清valid/receipt，重建原depth1可靠、显式VOLATILE reader，
generation隔离已取出/等待锁的旧回调。保留source水位、Policy和首次失标deadline；
不扩大TTL、配对或下降边界，不重打源stamp，不以RMW wall时间准入，不重建UAVState
reader或改变普通Land/取消/反馈失效策略。创建reader失败在清证据后传播并停止节点，
不是吞掉异常继续使用旧目标，也不是自动进入正常恢复。

**验收标准与结果**：

- 系统/慢时钟两类.45秒队列超限旧目标均不ready，退休队列后新源可恢复；.18秒
  burst只接收末帧且不重建。相同反例修复后3PASS。
- 最终7项C++测试通过（约1.78秒）：以上3案例，退休callback不清/续新证据，
  callback等待flight mutex超限不续期，far-future触发不污染水位，以及实际无效ROS
  context令reader创建失败时清valid/receipt后抛出。原QoS也核对；异常用例不冒充
  所有内存/RMW资源故障覆盖。
- 实际transform＋飞控合成反馈链通过（最终CTest约6.69秒，domain204）：观测端
  .6秒test-only阻塞并发生真实generation重建，控制输出lost_hold的首次z=1.0；
  反馈扰动为.97时hold仍1.0。1–4独立有效源仅reacquire_hold，第5帧转align仍不下降；
  再5个新独立对准帧才descend。持续失标真实ABORTED/status6，landing_target_lost，
  ownership响应goal_id与所属goal_uuid一致且RELEASED；mode仅[3]/arm仅[true]，
  不追加Land/上锁。两个native进程单次SIGINT正常退出。合成反馈不是飞机动力学。
- 链路首轮误把重获阶段期待为align，第5帧立即descend，测试FAIL保留；改成实际
  Policy明确区分5帧重获与再次对准，未修改生产Policy或降低门槛。
- 默认注册新2套件：飞控全9项CTest通过（约70.11秒），观测包全18项通过（约18.94秒）。
  test-result飞控61项零错误/失败/跳过；观测187项零错误/失败、原cppcheck工具2skip。
  新C++测试cpplint/uncrustify、新链路flake8/pep257、两新文件Apache版权检查及
  diff-check通过。飞控原CMake没有注册完整lint，不能把新增文件lint记为全包lint签收。

**一次SITL结果：FAIL，集成签收未完成**。安装统一入口、新空证据目录、独立PX4
rootfs、冻结同机DDS、0.2m静止板、三相机30Hz、.6/.5m高度区间、诊断默认关闭。
起飞/稳定悬停后进入精准降落；正式任务137ec90d684245179bc31e47348a8a4b真实
ABORTED/status6，`step_failed:landing_target_reacquisition_timeout`。未进入descend或
land_handoff；mission ownership与该UUID匹配且RELEASED。四类父进程exit0，
child_exit_failures全空；定向检查无所属Gazebo/PX4/控制节点残留，未自动重试。
失败末段约35.539–37.689 steady elapsed：tag/landing_target各63条有效独立观测，
guidance为26条valid与26条expired_or_clock_invalid；反馈align2、lost_hold27、
reacquire_hold14、failed1。该窗口observer记录的guidance ROS源年龄约.124–.292秒，
不是RMW取出年龄或飞控callback年龄。全轮新旧reader重建warning均0，故不能将
失败直接归因于新增重建保护，也不能用这一轮宣称保护无性能影响或S21同因。

**当前状态/未完成**：第1项确认局部缺口修复及第2项合成链路签收完成；本次短时
SITL正式任务未通过。剩余优先定位观测转换的源时间、车辆配对等待及过期输出交替，
不是直接放宽重获期限/有效期，更不能把标签全程缺失当成已证根因。组持续运行但
单topic饥饿、上游排队/采集时钟、全遥测链、长期反复重建仍未签收；S21唯一根因
保持未闭环。所有失败、冻结配置、日志/图像及最终组件证据在
`artifacts/d5-guidance-timing-20261006/`，SITL目录为`sitl-mission.BcRz4F/`；观察窗口
汇总另存sitl-window-summary.json，不能替代原始result.json。不得将27项CTest通过
写成这次SITL或整个D5鲁棒性通过。

## 15. 持续流配对优化：定位与待确认策略

**目标**：用户授权解决第14节的guidance过期交替/重获超时：定位、建立不飞行复现、
保持原安全门槛修复，再组件与短时SITL验收。不恢复UI、实机或G9。
主agent分析冻结证据/诊断与生产策略；coder只新增test_stream_pair_ros.py；reviewer
只读审查候选策略。当前尚未实施新的生产配对策略或提交git。

**定位进度**：同原0.2m/三相机30Hz/.6/.5m配置的一轮诊断SITL（仅配置增加
diagnostics=true，源生产代码未改）正式任务dbfcc9e10da748dc82c512dd8cb39535通过，
完成3步；precision UUID 8e9c24a876ca0ac7bc1d8e6240076814，align/descend/land_handoff
齐全；同mission UUID RELEASED、fresh disarmed，ROS-age0/receipt约.023秒。
父进程exit0、child_exit_failures全空。该轮native landing_target receive→take最大
约11.62ms、transport最大.60ms、配对等待最大30.65ms、reader reset0，说明这轮未
重现上轮.124–.292秒observer guidance源年龄。不能据此把诊断开关当修复、把旧FAIL
覆盖或把两轮差异归为唯一根因。配置diff只有diagnostics，不代表全部调度条件受控。

**持续流实测**：新增真实安装LandingTransform＋合成30Hz光学target、20Hz state、
10Hz离散Clock，domain205，原source_age .3/pair_gap .1保持。串行6case（约20.79秒）：
普通/诊断executor匹配流各90/90 valid；state-source-lag .16秒、target-lag .02秒及
两个clock相位四case均90target/60state、0valid，仅pending无输出。无源倒序/重复、
无强制kill，所有节点单次SIGINT exit0。已确认这个受控持续迟到流的latest-only
配对饥饿；不是原SITL expired交替的同因证明。测试目前测量迟到覆盖，不要求放宽
安全规则，6PASS不是“迟到配对已修好”。其中初始clock就绪header0的fixture失败
保留；最终先真实查询到正header，再启动记录，不修改生产时间规则或重试动作。
新增文件flake8/pep257/版权检查通过；尚未注册CTest，待新语义明确后设验收断言。

**用户待确认**：已异步询问是否允许将“仅最新单槽”改为最多32帧有界短历史，
选择仍在原source/首次steady TTL内且满足原.1秒可信状态配对的最新可配帧；保留源
stamp、输出严格递增，无姿态外推，失效/重建清空。此策略替换原latest_only内部
契约，必须同步审查旧测试；不默默删掉旧安全断言，也不把扩大缓存当扩大有效期。
在用户确认前不改生产。原单槽无法配对即失效/失败仍是现行行为。

**验收标准（确认策略后）**：持续迟到流在不扩大TTL/pair_gap情况下能输出安全配对；
过期/非法/frame-ID不符、clock退回、reader重建不复活旧证据；输出单调、内存有界、
独立帧计数不被重放续期；组件与失标恢复链通过，再以诊断默认关闭的新短时正式
任务签收真实成功/3步/UUID释放/fresh disarm。S21原始唯一根因仍需独立证据。

**证据**：固定目录artifacts/d5-pairing-20261006/保存连续流输入source/steady到达、
输出observer ROS-age/reason及所有失败日志；诊断SITL为diagnostic-mission.ihqGAm/。
source-before.tgz与原第14节失败证据并存，不进行盲目飞行重试。

### 15.1 用户确认后的有界安全配对与实际验收

**决策/目标**：用户回复“按你的建议进行”，批准最多32帧有界短历史。第15节
“待确认/未改生产”是修复前历史，当前以本小节为准。目标是修复已复现持续迟到
配对饥饿，保持原安全门槛，并完成组件及诊断默认关闭的短时正式任务签收。

**实现完成**：pending_sources硬上限32，每帧保留原message及首次steady receipt；
watermark为输入防重，published_watermark为输出防倒序。每次挑原TTL内且能与可信
状态按原.1秒窗口配对的最新源，不外推；成功删除所有已发布/更旧源，保留更新
待配源。过期只删除该条，不连带清其他有效候选；无match不盲输出。新增观测入历史
前验证尺寸/有限值/深度/质量/单位光学姿态，非法新target/state或世界几何失败清
历史及有效证据，不向旧几何回退。clock失效/回退、receiver generation重建清历史；
回退重置两个源水位，重建保留水位，退休回调仍不能影响新证据。原source/首次receipt
.3秒、state年龄及.1秒配对窗、飞机5帧重获后再对准、取消/停流/控制权策略均不放宽。
只新增内部缓存/诊断字段，不改公开消息/Action布局，无RMW wall飞行准入。

**修复前后证据**：在改生产前，已按用户批准后的新覆盖语义把4个持续迟到case
增加>=50/90有效覆盖与逐条安全断言，旧实现真实4FAIL/2deselected（约13.96秒），
均因0<50，不是fixture失败。改后6个实际ROS连续流（普通/诊断executor各3case）
通过，匹配流各90/90，四迟到/clock相位各59/90；每valid源唯一递增、保留原stamp，
observer源年龄在原边界内、原target发布到输出<=.3秒、实际已发布state源差<=.1秒。
这是受控持续流证据，不将59/90写成所有动态场景覆盖保证。

**安全回归**：真实Node受控时钟history初10项通过，随后补坏质量、错误frame/ID和
冻结clock，共14项通过（约.24秒）：容量溢出只保留最新32且receipt不变、混合过期
不丢更新候选、重试不续TTL、输出递增/最新安全选择、无match拒绝、几何/非法新
证据/clock退回及冻结/reader重建清缓存。原test_timing_pair_ros的latest_only迁移为
history_newest_safe，明确允许先输出仍fresh且真实可配original、再newest，输出
[original,newest]严格递增；后续旧state不得复活或续期。旧单槽源码/用例与原始失败
归档保留，不通过删去过期/乱序断言冒充回归通过。

**包级结果**：重新构建成功；观测全20项CTest通过（约40.59秒），飞控全9项通过
（约69.85秒），包括真实观测重建→停止下降/5帧重获→重新对准→持续失标失败及
匹配UUID释放的既有链路。追加14项负向case后对应套件与copyright/flake8/pep257
定向4项CTest再通过（约1.46秒）。原cppcheck2工具skip保持，不宣称完整静态分析。
注册新history/stream两套件，不把观测性0覆盖PASS当新语义签收。独立只读生产审查
未发现阻塞，并与实际测试分开记录。diff-check通过，尚未提交git。

**改后默认诊断关闭SITL：PASS，限定本轮短时签收**。
安装统一入口、新空目录/隔离rootfs/冻结DDS、0.2m静止板、三相机30Hz、.6/.5m区间，
diagnostics=false，非降低负载或扩大参数。mission b5db5da6407544519f2c903ada9e3135
真实status4/success=true/completed_steps3；precision UUID
384350b8985ee6e205e32fe444d00340，反馈align55/descend102/land_handoff96，无lost_hold。
精确mission ownership UUID匹配且RELEASED，final_disarmed=true，末态ROS-age0秒/
receipt-age约.000347秒；所有四类父进程exit0，child_exit_failures全空。定向确认无
所属Gazebo/PX4/桥接/飞控/任务节点残留。本轮控制窗口约36.657–44.507 steady elapsed，
tag/landing_target/guidance各228条且228valid，无过期交替；全轮reader reset warning0。
进入普通Land后的观测失效仍按原语义，不将接地后tag缺失算飞行跟踪失败。

**结果与边界**：批准的持续配对缺陷修复、组件和这一次默认配置短时正式任务
已完成。此前诊断开启的通过不是修复依据，本轮成功也不证明第14节失败的唯一根因，
或所有时钟/传输/上游采集与S21都已解决。S21仍保留未闭环；全算法负载、长期鲁棒性、
实机/真实云台、UI与G9–G11仍未签收。没有盲降、自动飞行重试或恢复G9循环。

**产物**：artifacts/d5-pairing-20261006/保存history-stream-before.log（4FAIL）、
history-and-stream-after.log、history-ctest-first.log、history-negative-final.log及
6流实际输入/输出/全部失败证据；默认SITL目录history-mission.0cvawM/保存原result、
冻结配置、图像/日志。history-sitl-summary.json仅是原result派生摘要；原诊断
diagnostic-mission.ihqGAm/和第14节FAIL目录保持不变，源码最终快照/测试结果另归档。

## 16. 原始帧时序分段取证（2026-10-07）

**目标/边界**：用户批准按既定思路继续，先用非飞行受控实验区分上游源延迟、
DDS接收/take、回调、状态配对、publish调用及下游消费，再针对已证实缺陷修复。
S21和第14节FAIL缺少当帧native/publish信息，不能从旧采集源年龄追认唯一根因。
不放宽TTL/配对窗、改QoS、补源stamp或开飞行自动重试；真实设备/UI/G9–G11不恢复。
沿用主agent实现及总验收、原coder负责新增实验、原reviewer只读审查分工；未提交git。

**实现/进度**：默认关闭的diagnostics扩展为逐帧有界证据，转换端记录原stamp/
generation/first receipt/native take/target与state入口/pending及selected配对/状态源/
invalid上下文/publish起止和succeeded。实际publish抛错仍传播，finally记录false，
不冒充输出成功。飞控新增只读启动precision_timing_diagnostics=false，原消息回调
接收MessageInfo，记录回调前与取得flight mutex后的steady时刻、native接收系统时间、
source/准入结果/ready_at_exit/session active和UUID；callback入口不是native take，
ready_at_exit不是实际控制循环消费证据。统一仿真选项仅改生成配置同时启用两端；
采集端新增observer receipt steady。两端环硬上限256并公开累计丢失计数。

**确认并修复的新问题**：旧1秒诊断timer与至少1秒日志间隔同时使用，定时器微小
提前会跳过整轮，受控采集实验实际出现144条事件淘汰，曾导致逐帧链缺失的真实FAIL。
保留该失败目录collector_delay-d3gpqcgr，不删失败或选择有利窗口。诊断timer改1.05秒，
仍保留严格至少1秒检查、容量256和累计drop；退出强制排空转换尾段。恢复原1.0–1.25秒
采集暂停窗口后完整链75/drop0。此修复仅改善诊断完整性，不称作历史飞行过期修复。

**非飞行证据**：最终2项PASS约9.13秒。上游人为延迟批次upstream_batches-_srwrs7b
18完整链、6段valid/7段invalid交替、0reset/drop；native
transport/take队列/take到entry最大约.146/.292/.039毫秒，配对.200毫秒、publish
.055毫秒。这是人为延迟源在入口已旧，不是S21或网络延迟证明。原窗口慢采集
collector_delay-doc_1y5x的75链、0reset/drop，publish最大.064毫秒，采集迟读217.849
毫秒，区分“采集见到旧”与“转换输出旧”。按唯一source各阶段/first receipt及
valid且succeeded的publish关联，重复阶段拒绝歧义；各段来自同一源而非聚合拼接。

**发布背压假设对照**：另5项PASS约22.77秒，冻结bundled FastDDS副本/hash/env，
目标30Hz/状态20Hz/Clock10Hz，生产publisher不变，仅测试collector reliable/volatile
reader depth1/10/100、暂停.25秒及depth10暂停.34秒，另default-off depth10/.25基线。
四诊断case publish最大约.056/.058/.075/.071毫秒，采集段最大19.353/212.207/
217.662/297.113毫秒；全0reset/drop/正常退出。depth1仅69完整输出链，体现有界队列
覆盖，不能冒充75帧全收。默认关闭75valid，input delivery到collector最大216.978
毫秒，内部耗时/reset/drop保持未知而非填0。仅在此本机配置/应用消费暂停下未观察
publish阻塞；不是DDS ACK或网络故障注入，不能据此排除其他负载/环境的背压。

**验收标准**：默认关闭路径不新增飞行判断；原源/首次receipt/state配对/重建隔离/
失标5帧恢复/取消和控制权规则保持。真实native单次take原对象不替换、缺失或回退
系统时间为null；环有界/丢失可见/无成功发布伪证据；各有效链保留原source并唯一关联。
两新实验注册CTest串行domain207，分别30/45秒上限。包级回归及独立审查进行中；
真实模拟负载的带诊断采样与最终结果将在本节续记。不存在用受控延迟反向认证S21。

**产物**：artifacts/d5-frame-timing-20261006/保留全部first/final/失败与最终7项证据，
frame-flush105-verified.log、publication-backpressure-verified.log及逐帧evidence.json，
trace-unit-final.log（12项PASS）、flight-trace-unit.log（真实DDS callback及bounded测试
所属套件PASS）、build/lint日志。测试目录沿用本轮开始日期，不覆盖旧历史目录。

### 16.1 包级回归、实际模拟采样及最终边界

**组件验收**：重新构建两包成功。precision全22项CTest PASS约73.30秒（含新增7组
实际ROS实验及已注册lint），flight全9项PASS约69.87秒。Python诊断12项独立PASS，
涵盖原生单次take/原对象/metadata不改写、wall回退null、default-off inert、容量256/
drop累计、提前tick不排空/正常tick及强制尾段、publish异常false。CPP套件覆盖真实DDS
回调source/outcome、readonly/default-off、null native与环256/drop44/flush。
独立审查无阻塞，建议同时保留退休回调原代；已采纳callback_generation为闭包捕获代、
generation仍为当前代，实际旧reader回调断言old0/current1/retired。该小增量重新构建
并定向test_precision_queue PASS约1.96秒（10个gtest case）；不把此前全9项写成
小增量后的第二轮全包复跑。新增CPP两文件定向uncrustify PASS，原cppcheck工具skip
边界保留，不宣称flight全静态分析。最终配置/诊断/准备与flake8/pep257定向复验日志
另存trace-config-lint-final.log。
该定向5项实际PASS约1.61秒。额外header uncrustify检查发现原有排列/声明等格式差异；
本轮新增诊断声明已对齐，既有差异未批量重排，flight-header-style-final.log保留FAIL，
故仅声明新增CPP两文件定向style通过，不称作飞控全包lint通过。

**唯一带逐帧诊断正式任务SITL：FAIL，未自动重试**。新空目录frame-mission.Drz8q5，
原0.2m板/三相机30Hz/.6/.5m收尾区间、静止倾斜板、冻结相同DDS及隔离rootfs，
diagnostics=true/precision_timing_diagnostics=true。mission UUID
5bb4e0b3844148608cd994d32c50870c真实status6/success=false，
message=step_failed:landing_target_lost，精准动作UUID
2ad7f31ebf0425e1579c5583c26c2b5b经历align46/descend36/lost_hold35/reacquire_hold10/
failed1。同一mission UUID ownership=RELEASED；所有四类父exit0且child_exit_failures
均空，定向检查所属仿真/平台进程无残留。没有成功三步或新鲜disarmed证据，故不能
签收该轮，也不把仿真退出当远端实机安全终态。无阈值放宽、盲降或追加Land。

**该轮新取证**：精降窗口elapsed43.6995–50.0518秒。tag array184/184为detected，
但array valid不代表每个tag pose valid；原landing_target184条中169valid、15
tag_pose_invalid。guidance221条中132valid、37geometry_or_plane_invalid、33
expired_or_clock_invalid、15source_invalid_or_replayed、4vehicle_source_pair_pending。
本轮因此不是“只因看不到标签”或“valid入口迟到”的同一现象：存在上游pose拒绝和
转换几何拒绝，后续空源watchdog过期不能单独归为DDS延迟。

132条有效指导均获得唯一source/同generation/首次receipt一致且valid+succeeded的
完整native→entry→pair→publish链，及同一active precision UUID的真实飞控stored
接收链。原源在entry/publish/flight入口年龄均-.088至.016秒；native receive→take
最大约.413毫秒、take→entry .046毫秒、配对等待21.505毫秒且gap≤.088秒、publish
.118毫秒，飞控after-publish-end .197毫秒、native receive→callback .173毫秒、
mutex等待.0335毫秒。采集after-publish-end最大7.663毫秒。均为同机时间原点假设下
该132个具体有效源的分段值，不把不同帧聚合最大值相加成单帧延迟，不代表被拒帧。

整轮转换drop1416、飞控drop0、观测reset0，drop主要发生地面/无效高频阶段，不能
宣称整轮完整trace或给缺失invalid帧补0；本控制窗口132valid关联未缺失。此次1.05秒
修复消除了受控窗口因提前timer跳轮丢帧，但高事件负载仍会有正常有界淘汰，并非
承诺所有模拟场景零丢失。飞控ready_at_exit仍不冒充policy实际使用证据。

**结论/未完成**：本轮逐帧取证、受控区分、诊断定时器缺陷修复及组件验收完成；
实际正式任务该轮失败，未以再次通过覆盖。132条完整有效流未见显著传输/配对/飞控
延迟，但无效窗口有过期事件且未完整取证，不能断言全部失效与时序无关。
37条geometry_or_plane_invalid尚未区分高度误差/
法向倾角等具体几何门槛，15条tag_pose_invalid的底层位姿拒绝原因未保留。下一步应
离线检查原帧/相机标定/姿态候选，并补充具体几何拒绝字段；不能凭通用reason放宽
质量/倾角/高度门槛。S21的旧unique root仍未闭环，本轮不是对其追认或全负载鲁棒性
签收，真实设备/UI/G9–G11继续暂缓。

**最终产物**：frame-mission.Drz8q5/完整FAIL原result/冻结配置/图像/日志，
frame-mission.log；analyze_frame_mission.py从原证据保守派生frame-mission-summary.json，
stage重复/缺失拒关联、publish抛错不当success、同一active精降UUID才匹配飞控，保留
所有原FAIL及ring淘汰证据。该脚本是本单机本轮派生工具，不作通用时序/硬件时间认证。
独立reviewer从原日志重新计算并确认保存摘要完全一致，审查无阻塞；进一步要求仅
关联callback/current generation一致的stored、反馈UUID及observer有效source唯一，
已加显式断言/筛选，当前132项统计不变。审查不替代本轮失败或缺失阶段取证。

## 17. 本轮高度基准缺陷追查与修复（2026-10-07）

**目标/验收标准**：用户要求继续排查直至解决第16节正式任务失标。保留所有FAIL，
先离线定位、独立取证高度基准，再修复并以原0.2m板/三相机30Hz/.6–.5m区间和原
source/receipt/配对/质量/倾角/平面容差验证。组件/负向准入、真实地面接口、实际
正式任务及默认诊断关闭需分开记录；不将一次PASS或稀疏回放等同S21唯一根因/
实机/长稳签收。不以标签自身输出拟合校验平面，不在飞行中移动基准。

**离线证据**：原coder新增源树离线CLI replay_tag_frames.py/.cpp和7项测试，真实
调用现有ef_tag::estimate及production SUBPIX参数；40张保留PNG全部以捕获序号+
原RGB/BGR SHA对应原source。各K假设/另轮K下21张ID7检测均pose valid；production
回放10几何通过/7height拒绝/0tilt拒绝/4无法认证state pair。none模式另1倾角拒绝，
精炼后消失，不能用调宽倾角解释7个高度缺口。camera_1200重放center z≈.09565，
原平面-.0619075的误差≈.15756>.15，而倾角≈.1055<.175。保留同stamp状态完整包络，
不猜实际first receipt；旧实际37geometry及15pose拒绝不能由稀疏图像全部追认。
真实K由startup-only calibration-startup.mDeFDu采集，182条同K：fx/fy337.3570508553，
cx320.5/cy240.5、D五零；这是另轮同SDF实测，不冒充旧轮精确标定。无飞行，三组
exit0/子失败空。独立只读审查核对原图SHA/回放输出/源码SHA，无阻塞。

**新增精确诊断**：原pair_selected保留真正选中车辆position/rpy与原optical pose；
geometry_rejected按原判断分开记录center/normal/height_exceeded/tilt_exceeded及原
容差。observer opt-in记录真实CameraInfo、selected_tag内部valid/reason/error/pose、
LandingTarget pose；array detected不再误当selected pose valid。默认off，不改准入。
两几何负向纯Node case仍要求invalid；配置纯测试覆盖array有效而选定位姿拒绝。

**已查明的实现缺陷/方案**：旧统一仿真入口直接设置plane=board_world_z-.10，
混淆Gazebo世界与PX4 odom高度且假定固定接地位置。旧PASS preflight odom z约-.01，
第16轮FAIL约.142；原平面已贴近高度拒绝门槛。新方案从生成模型完整collision和
显式URI资产推算base_link接地高度，再用Gazebo GetEntityState(独立world真值)
与新鲜disarmed stationary UAVState配对，十个严格推进样本/至少1.8 steady秒/
offset span≤.03m/真值ground span≤.005m，冻结median(odom_z-world_z)后才启动精降。
world平面用cell顶部而非model原点（约+1mm）；不使用检测结果校准自己，不放宽.15m
plane tolerance、.175rad tilt或原TTL，不运行时修改只读参数。服务只调用get-state，
generated-only插件低频发布；生产/实机没有自动基准拟合。

**保留的接线FAIL**：首轮reference-startup.Am3FqM（仍用旧.10接地假设）在实际地面
拒绝fixture not stationary on expected ground，precision/飞行动作均未启动；仅
simulation/bridge退出0、子失败空。这不是飞行FAIL，也不能隐藏为startup通过。
实际base collision box高度.11给底面-.055；include mid360/gps必须显式解析资产，
无映射/未知relative frame/不支持碰撞mesh等拒绝，不能默默忽略include后声称完整。
后续接线改为从模型推算，并保留每次ground reference响应/时间/实际world pose。

**组件进度**：height reference初29项纯测试通过，后追加cell面定义/world倾斜负向；
入口真实nested sampler提取负向测试覆盖最新armed/disconnected/moving不退旧、
query timeout移除pending/清client、clock回退，另AST核对成功校准先于precision
start。初5项入口负向通过；地面完整collision/include及其负向测试由原coder独立
承担。完整包回归及正式飞行验证尚未完成，本节最终以接续验收结果为准。

**产物**：artifacts/d5-geometry-20261007/保存本轮构建/单元/lint和两个startup原证据；
离线原失败帧回放保存于artifacts/d5-frame-timing-20261006/replay-Drz8q5-*，不改原FAIL。
继续沿用主agent/原coder/原reviewer分工，UI、真实设备及G9–G11未恢复，尚未提交git。

### 17.1 独立地面基准核实与组件验收

实际reference-ground.Spt33x地面接口PASS，无飞行动作。完整模型碰撞推算upright
base_link接地高度.055m；原模型include mid360/gps由与launch相同的显式只读路径
映射并记SHA，真实资产手工核实结果.055。23项便携collision测试不依赖ignored
artifact/外部PX4绝对路径，保留未知include、cycle、非零included-model pose/scale/
relative frame/mesh/非法尺寸等拒绝；不宣称通用SDF parser或接触动力学解算器。

GetEntityState请求easyfly_iris::base_link/world的实际真值z≈.05399999999（碰撞静置
允许的约1mm穿透）；十条odom源4.9–6.7秒/世界源5.0–6.792秒严格推进，source gap
≤.1秒，steady跨度1.83447秒，offset span.0146484m，冻结offset=-.05517492675m。
fiducial cell顶部中心world z=.03908277119，最终odom plane=-.01609215556。原raw
响应pose/header/frame/source/请求及receipt与十组配对均保留；三组父exit0、child
失败空，未发送任何Action并无残留。这证实旧-.10偏移与实际坐标系不一致，startup
通过不承诺飞行中datum无漂移。冻结后不会用标签/拒绝值重新调整。

观测包全26项CTest PASS约74.59秒，包括新增reference/collision/replay/入口负向及
全部已注册lint；cppcheck2.7工具skip现3项（新增离线CPP helper），不是全静态分析
通过。增补4项fixed odom-origin shift的门槛不变性测试，ground_reference定向套件
再PASS约.37秒。31项ground pure case加4个frame-shift，共35；入口6项（5个实际
sampler异常路径+1个顺序AST检查）、collision23、offline replay7。几何纯Node原14
负向加2细分拒绝case仍通过。精确snapshot本轮默认关闭，record-only新增字段不改
质量/时间门槛。原reviewer独立核对ground十条原证据和源码，无阻塞，未运行SITL。

飞控第一轮全包回归8项通过/1项timeout：test_precision_queue在新的diagnostics
unit取消executor并join时，native discovery可能早于worker spin开始，过早cancel
被后续spin启动覆盖。原30秒timeout全日志保留。测试夹具新增is_spinning同步，
10次整套重复PASS约19.81秒；随后增加worker启动延迟120ms的确定性立即取消case，
验证同步后可有界退出。仅改测试夹具，不修改飞控逻辑/控制时间。含该增量的全9项
飞控回归仍在进行，正式任务尚未验收；后续结果在本节追加，不能以repeat覆盖原FAIL。

Gazebo接口时戳/参考系实现可参阅
[官方只读状态查询源码](https://github.com/ros-simulation/gazebo_ros_pkgs/blob/ros2/gazebo_ros/src/gazebo_ros_state.cpp)。
本平台只调用get_entity_state；生成插件另提供的set-state服务不被调用，且仅存在于
隔离仿真，不把此仿真真值校准开放为实机默认功能。

### 17.2 最终限定仿真签收：PASS

**组件结果**：含确定性120ms延迟worker启动case的飞控全9项CTest PASS约69.78秒，
queue套件11个gtest case通过；这是修复后全包复跑，不抹掉初次30秒timeout。
只读review另提醒startup等待自身失败后的迟启动边界，已在fixture TearDown于cancel
后、join前关闭专用context，防止迟到spin重启；该测试收尾小增量三次重复PASS约
6.33秒，随后源码格式收尾重编译，定向验收PASS约2.12秒（queue-final.log），
生产逻辑不变。原source/generation/控制权/失标/停流和未知命令锁均保留。

**修复后诊断开启正式任务reference-mission.OXqqor：PASS**。mission UUID
b54cf615ea1d40909c6a5c396c281c8a、precision UUID
6e8af199b89b2c8179b361321849f856；真实status4/success=true/completed_steps3，反馈
align57/descend101/land_handoff93，无lost/reacquire。精确同mission UUID RELEASED；
final_disarmed=true，末态ROS-age0、receipt-age约.0002244秒；四组父exit0且所有子
失败空，无所属仿真/平台进程残留。ground offset=-.06207189941，plane=-.02298912821。
进入handoff前控制窗口tag/raw各230条全valid；guidance231中229valid、1geometry
reject和1expired。拒绝源35.9秒的精确geometry事件height_exceeded=false /
tilt_exceeded=true，原倾角门槛仍正确拒绝，不把该无效帧抹成全valid。整轮转换事件
drop148、飞控drop0，无observer reset，不能宣称整轮trace完整；无持续失标失败。

**修复后默认诊断关闭正式任务reference-default.YT7636：PASS**。mission UUID
0d856ede734e491f959a958ac4328b83、precision UUID
add3d964978dba223b16bf89fb912b06；status4/success=true/completed_steps3，反馈align61/
descend104/land_handoff108，无lost/reacquire。精确mission UUID RELEASED；新鲜
disarmed，末态ROS-age0、receipt-age约.038224秒，四组exit0、子失败空，无残留。
ground offset=-.06260595702，plane=-.02352318583；控制窗口tag/raw/guidance各240条
且240valid。两端诊断日志均未产生，内部耗时/drop为未知None，不填零或伪称无排队。

两轮保留原.2m静止倾斜板、固定相机、三相机30Hz、.6/.5m区间、冻结相同显式DDS
和新隔离rootfs，不是缩板、降相机速率、扩大TTL/几何门槛或blind retry。第二轮是
独立default-off验收，不把开启日志的成功当普通executor路径签收。新ground校准
只在运动前冻结，独立于tag测量，飞行中不重估/调容差。

**结果**：本轮查明的仿真world/odom高度基准实现缺陷已修复并完成组件、地面和
开启/关闭诊断各一次短时正式任务验证；可结束该具体缺陷修复，不代表所有采集/
姿态/遮挡/光照或长期datum漂移均已覆盖，也不能唯一反推旧37geometry/15pose
invalid或S21。S21历史缺证据的unique root状态保持，所有旧FAIL/skip/timeout保留；
实机、真实云台、UI与G9–G11不恢复，未提交git。

独立reviewer从原result/日志重新计算reference-missions-summary.json，确认两次真
完成、精确UUID释放、新鲜disarmed、原负载、默认off的None边界及诊断唯一倾角
拒绝一致，审查无阻塞；其复核不代替根实际测试。结果和代码快照归档于
artifacts/d5-geometry-20261007/，summarize_reference.py只派生该单机原证据，不作
硬件/长期鲁棒性认证。最终运行日志为precision-ctest-final.log、
flight-ctest-after-fixture.log、queue-cleanup-repeat.log及两轮reference原result/配置/
图像/所有进程日志；source-final.tgz及sha清单保留最终实现。

## 18. 优先处理历史退出故障（2026-10-07，部分完成）

**执行目标**：用户授权先处理退出故障，不开发新功能。分开核对EGO stop SIGSEGV、
Gazebo stop boost self-join及相机重名加载空指针；优先真实栈/最小反例，只修有证据
的缺陷。验收须真实inferior/子节点正常退出，launch0不足以代表整体成功。
沿用主agent负责Gazebo/相机/接线/记录、原coder负责EGO、原reviewer只读复核；
项目主＋子并发上限2，未连接实机或恢复G9长循环，未提交git。

| 子项 | 本轮结果 | 验收边界 |
|---|---|---|
| 相机重名加载空指针 | 已真实复现并修复项目相机路径 | 原系统QoS/Load SIGSEGV红栈；新插件明确拒重名、原流存续、真实SIGINT退出0 |
| EGO深度投影内存 | 两个真实ASan越界修复＋review收尾 | 直接instrument实际grid_map.cpp的5case通过；不在默认云链，不追认旧退出根因 |
| EGO历史stop SIGSEGV | 新无Goal点云/odom两信号及完整组合均未重现 | 仍缺旧故障真实栈，保持未闭环 |
| Gazebo历史stop self-join | 传感器隔离/完整组合未重现 | 不用相机空指针解释self-join，保持未闭环 |
| 旧相机重复加载来源 | 尚未定位 | 最小同名fixture是明确人为反例，不是旧模型重复加载来源证明 |

### 18.1 相机真实反例与项目局部修复

旧`/tmp`退出实验当前已不存在；原608MiB相机apport报告仍在/var/crash、未改。
新证据基目录`artifacts/shutdown-20261007/`。`camera-original.vf86DS`给两个相机
同plugin name＋namespace，真实GDB SIGSEGV落系统QoS::get_publisher_qos及
GazeboRosCamera::Load，复现已定位的NodeGet返回null路径。原探针passed=true
仅是预期反例符合，不表示运行PASS。

从官方ros-simulation/gazebo_ros_pkgs **3.9.0**导入camera源/头，保留OSRF版权及
Apache-2.0，新`safe_camera`独立类/头/库名；除此仅NodeGet后null guard。源归一化
SHA `0385ceec25a7b55f57aea38c060267bc593c4959a0f097ae4cb89561cf34a416`、头
`9d2f1b9808a21648bc852e5358e99ff3d96c9d47fe9544b117f1b675190486ec`，逐字契约
测试固定此边界，不把tag等同已安装Debian二进制逐字源码。原来源见
[官方camera源码](https://github.com/ros-simulation/gazebo_ros_pkgs/blob/3.9.0/gazebo_plugins/src/gazebo_ros_camera.cpp)。

项目模型两相机显式选`libeasyfly_gazebo_ros_camera.so`，下视克隆继承；两个SITL
入口搜索位置从不存在的share/package/lib改为prefix/lib。新库不依赖原camera库，
仍链接安装的base/multi_camera/node库。系统/opt文件不覆盖、不升级，不自动改
节点名、重stamp/QoS、换原流或用禁用相机授权飞行。包元数据仅追加该明确派生
部分Apache许可，混合Livox原MIT元数据/未知来源保持，不宣称整包第三方许可解决。

**实际验证**：camera-safe-pidfix2.GIZ61B有明确重名及Camera plugin rejected日志，
首图/Info持续输出，真实gzserver SIGINT退出0约.21372s，无强杀。最后加严探针的
重复名＋拒绝日志判据重新核对此原证据仍PASS，未重新飞行。sensors-safe.kcnAB6
保留原两相机30Hz/MID-36010Hz，RGB/Info/depth/cloud/livox分别26/42/22/9/29条，
真实SIGINT退出0约.31385s。最初safe夹具把版本化gzserver-11.10.2路径按basename
误判，强制清理FAIL保留；随后原端口TIME_WAIT预检拒绝也保留，不删锁或连旧master。

safe_camera两个CTest PASS约.77s：真实NodeGet重复拒绝/registry释放重获的gtest，
另9纯契约case（2来源hash、fixture冲突保留、6加严verdict）。实际注册测试不自动
跑Gazebo；显式scripts/gazebo_shutdown_probe.py是单次、预留锁、无PX4/飞行探针。
PX4入口/模型/会话全3CTest PASS约.35s；下视原配置/准备/collision三定向CTest
PASS约1.13s。新增Python及相机C++夹具lint修正后PASS，初格式失败/命令选项错误
日志均保留；没有签全仓lint。

### 18.2 EGO独立内存缺陷及实际退出检查

coder在actual GridMap::projectDepthImage取得原两份ASan红栈：640x480/skip3
unfiltered实际34240写入>固定floor34133的容量越界；filter margin0末像素读取
下一像素越界。最小修复按当前rows/cols ceiling容量resize，使用当前pixel判0；
review再指出最后指针+=skip可能越过one-past，已改行首＋row_ptr[u]、不递增指针。
实际方法5个ASan case覆盖上述两反例、非标准尺寸、stride大于尺寸、后继0不影响
当前深度，plan_env全5CTest PASS约.43s。ASan只新测试目标且detect_leaks=0，
不是全栈ASan/泄漏签收；plan_env当前Debug cache明确保存，未更改生产安全门槛。

local_planner仅订阅可信cloud/odom，未接depth/pose生产者，所以深度两缺陷不能
解释历史默认云链SIGSEGV。正常main单线程spin停止后再销毁FSM/manager/map，
只读检查亦未证实默认析构缺陷，没有猜测性线程/析构补丁。
ego-cloud-shutdown-aom09nkh确认真实EGO接受trusted cloud/odom且无Goal，GDB
inferior SIGINT/SIGTERM正常退出各约.21438/.21410s，debugger0，无所属残留。
原短命GDB helper PID识别夹具FAIL保留，未计为平台失败根因。

### 18.3 完整组合与整体剩余边界

第一次full-stack.sUIm2s向整个进程组SIGINT，launch又传播一次，多个真实child
exit-2，整轮FAIL保留；不能删除正常SIGINT INFO后抹掉child异常。修夹具为只给
launch SIGINT，独立新rootfs的full-stack-owner-signal.ldy8cl实际PASS：原相机/
MID360、CPU检测/跟踪/SLAM/地图/桥接/飞控/任务/导航/EGO组合运行，无Action Goal，
观察uav_command计数0。RGB484/depth482/livox168/可信云话题58/odom893/UAV464，
这些是收到消息计数，不是所有观测有效或规划性能；地面无Goal不代表飞行任务。

输入≥3条/EGO存在、connected/pose/velocity有效且steady receipt新鲜disarmed后
请求退出，24个进程正常退出，launch0约1.61695s；两个GDB真实Gazebo/EGO均
exited normally，没有子失败/强制清理/所属残留。该探针未保存完整UAV源时序，
末态新鲜只按steady receipt解释，不伪称完整ROS-source准入。诊断SIGINT发给owner
修正不改生产控制语义、停流或故障锁。

**独立审查**：原reviewer核对来源hash/limited diff/null Load析构、ELF依赖、ASan
实际方法和原反例、加严探针及完整24退出原日志；review指针收尾已落实，最终无
阻塞发现。其只读核对不代替主/coder实际测试。

**当前状态**：本轮可复现缺陷修复与有限退出验证已完成，第一项总体仍部分完成。
历史EGO stop SIGSEGV、Gazebo boost self-join和旧重复加载来源保持未知；不得
以未重现关闭。后续需保留自然故障栈/精确输入再最小复现，不臆测修改系统依赖。
UI、真实设备/云台、G9–G11及新功能均未恢复，未提交git。完整EGO重编/整包回归
与最终归档结果在此节接续记录。

### 18.4 最终构建与回归收尾

EGO依赖头重编时原BFD链接持续工作超过8分钟，link命令重复导出rclcpp约66次/
多个ROS类型库约63次；这是构建耗时现象，不是退出崩溃根因。原colcon未完成签收
前仅对自有PID有界终止，外层退出143日志保留；发停止请求时ld已经结束，不能把
此状态追记为BFD崩溃或整轮构建通过。没有修改依赖导出/源CMake或安装系统工具。
随后局部EGO cache指定已安装GNU gold（CMAKE_EXE_LINKER_FLAGS=-fuse-ld=gold），
重建PASS约31.2s，输入源码/编译安全策略不变；cache和原失败/新构建日志归档。
plan_env明确Debug，初始原cache未预先保存，无法认证原值，不伪称恢复原默认。

完整EGO **16CTest实际10PASS/6FAIL约18.94s**：前8行为全部PASS（含traj两信号/
导航会话/managed故障等），cppcheck与xmllint通过；copyright/cpplint/flake8/
lint_cmake/pep257/uncrustify仍失败。plan_manage生产源码本轮无新增改动，仅新增
显式无Goal诊断probe；不能把8行为PASS写成整包/全仓lint通过，也不在退出任务里
批量改第三方许可/格式。cppcheck原xunit有18个skip，不代表完整静态分析通过。

相机打包收尾完整2CTest再PASS约.79s，单独9纯契约PASS；新增Python及相机CPP
夹具lint最终PASS。源码来源原文、actual ASan两红栈、最终回归与完整平台原result/
日志全部保留，原reviewer已核对收尾无阻塞。EGO probe原文在plan_manage/test/
probe_ego_shutdown.py及artifact同SHA副本，后者仅归档，运行使用源码路径。

最终gold二进制另执行无Goal点云/odom两信号有界probe，
ego-cloud-shutdown-68hx_c51两次真实inferior正常退出、debugger0，原日志及bin SHA
保存；这是最终构建运行核对，不是冷启动长循环或历史故障根因证明。所有自有
仿真/节点/构建/调试进程已退出，无残留；系统camera原SHA保持未变。最终源码/
文档快照、三包test_results＋SITL包CTest原日志、缓存和SHA清单归档至本节artifact
基目录。SITL包使用原生CTest而无该test_results目录，不伪造xunit。

## 19. Gazebo transport self-join 局部修复（2026-10-07）

**执行目标**：继续第18节退出故障排查，确认真实Gazebo self-join可达路径，落实
用户批准的项目局部兼容补丁；线程必须真实结束后才释放资源，不改系统库，不
跳过join后直接free、不忽略异常。用户随后关闭子agent，本轮实现、测试及代码
核对由主agent单独完成，没有独立reviewer签收。UI、实机、云台、G9–G11不恢复。

**当前进度/结果**：确定性的last-connection生命周期缺陷已修复并接入两个SITL
入口，组件＋一次完整无Goal组合验证通过。第一项整体仍部分完成：历史自然
Gazebo事故没有旧真栈，不能从最小反例追认唯一归因；EGO历史SIGSEGV及旧相机
重复加载来源仍未知。第18节中的“未复现”是当时批次结论，最新证据以本节为准。

### 19.1 根因证据与修复进度

证据目录`artifacts/shutdown-root-20261007/`。`connection_last_owner.cpp`通过
真实安装的transport::Connection和本机loopback peer触发空头读取，回调使用
barrier确定性控制最后引用释放：主线程先放弃owner，实际WeakBinder在IO回调
返回时释放最后strong ref。原GDB栈`connection-before-gdb.log`真实SIGABRT，
boost报告trying joining itself；路径是Connection析构→计数归零→IOManager析构
→Stop→join自身。没有手工抛同名异常，不启动Gazebo master、PX4、ROS或飞行。
这是安装库真实API生命周期反例，不等于自然历史stop事故已经唯一定位。

最初仅在独立server定义IOManager同名符号的方案被实际连接测试否定：系统库
内部是直接调用，没有IOManager的PLT重定位，仍进入旧self-join。原失败CTest/
无效方案传感器PASS日志保留；传感器exit0不能代替补丁真实生效。这一方案没有
作为正式入口交付，不使用跳过测试、静默fallback、二进制改写或系统升级补救。

最终`safe_transport`按官方`gazebo11_11.10.2`构建完整私有transport：11个其它
实现文件逐字导入，cmp和SHA256SUMS核对，原OSRF/Apache-2.0保留；只派生
IOManager/server main。独立`easyfly_gzserver`的私有RPATH选该同SONAME库，
目录不加入通用LD_LIBRARY_PATH/plugin路径，不影响系统gz/gzclient、PX4和其它
ROS进程。两个SITL入口只替换server显式路径，参数、插件/相机率、模型、session
guard、退出由launch owner单次传播、安全门槛不改。

清理语义：外线程析构停止IO、同步join后释放；自身IO线程析构则把整个private
state交给一个独立清理线程，该线程join原IO线程后才释放thread/work/service/
state。Stop在自身线程只请求停止，不free，不detach；不在run活跃时调用reset。
main先释放Server所有者，再drain，要求live/pending=0，join清理线程后才成功退出。
仍有live manager、晚于关闭创建manager或join异常明确失败，不标PASS；回调卡住
会等待，不以超时直接释放资源伪造成功。生命周期控制入口限定非IO主线程。

构建要求精确11.10.2、IOManager头SHA及原系统transport SHA；运行要求Connection
与兼容代码同私有库，并校验实际加载的原core SHA。固定值/来源归档hash见
`safe_transport/README.md`和third-party-provenance。未知版本拒绝，不降级到旧库。
系统transport/core/camera SHA复核保持不变；回滚为两个入口恢复`gzserver`并
重建SITL包，不需要恢复任何系统文件。本轮没有commit或push。

### 19.2 验收标准与实际结果

| 验收项 | 标准 | 实际结果 |
|---|---|---|
| 实际连接last-owner反例 | 新库必须确实接管；回调释放后无self-join，全部资源释放 | gtest lifecycle计数验证通过；单独GDB `transport-connection-after-gdb.log`通过，真实inferior正常退出 |
| 资源释放顺序 | IO回调未返回时不能free；外线程析构必须等待；Stop可重复 | 7个真实IO/Connection生命周期case全通过，包括barrier保持活跃、Drain等待、外线程join、worker Stop、保留live时拒绝Finish、指纹拒绝 |
| 内存检查 | 实际私有transport及测试启用ASan，不能仅测重写公式 | 独立Debug/ASan完整transport构建，7case全通过；detect_leaks=0，其他Gazebo系统库未instrument，不声称全栈/泄漏验收 |
| 原相机/启动契约不退化 | 现有camera与SITL组件同时通过 | 插件全部4CTest PASS约1.77s（新7生命周期＋2来源/接线case、旧camera测试）；SITL全3CTest PASS约.34s |
| 隔离原传感器组合 | 原两相机30Hz/MID36010Hz都有数据、用新库、正常退出无强杀 | `sensors-full-transport.CoKzNx`通过：RGB/Info/depth/cloud/livox均≥3；live=0 pending=0 deferred=1 completed=1；SIGINT真实exit0约.314s |
| 完整平台组合 | 新入口、原传感器＋CPU感知/SLAM/地图/桥接/飞控/任务/导航/EGO，真实正常退出 | `full-stack-transport.ShMtWH`通过：24进程正常退出，Gazebo/EGO两GDB inferior正常，launch0约1.6666s，live=0 pending=0，无强杀/所属残留 |
| 定向lint与来源 | 新自有/派生修改格式、许可、Python及CMake检查通过；上游原文件不批量重排 | cpplint/uncrustify/copyright/lint_cmake/flake8/pep257最终全通过，原错误记录保留；不签全仓lint/EGO已有6项lint失败 |

完整组合未发送Action Goal或解锁命令，/uav_command=0；消息数为RGB466、depth466、
Livox164、可信云话题57、odom917、UAV481。连续3s就绪且receipt新鲜disarmed后
只向launch发SIGINT。计数不保证每条消息有效或规划性能，末态新鲜只按steady
receipt解释；不签完整源时间准入、起降/精准降落任务、长循环或实机验证。

最终构建日志`transport-release-build.log`；正式CTest为`transport-release-ctest.log`
及`sitl-release-ctest.log`；ASan为`transport-asan-final-test.log`及真实gtest XML；
最终定向lint为`transport-lint-final.log`，原始反例/失败/完整组合日志均保留。
原native build cache未全局添加ASan或变更优化档位；独立ASan不安装进正常overlay。

### 19.3 剩余边界与下一项

EGO被中断的`ego-cloud-o7zb0_iq`只有待解析断点/收到云的日志，result是空数组，
没有活跃断点信号、真实终态或完成报告，**不记PASS**。本轮未重建被屏蔽的回复，
亦未以换模型/子agent重试规避检查。后续EGO工作仅按授权的正常可靠性诊断推进：
有效默认cloud/odom链的活跃回调退出取证，先确认实际Debug/ASan库加载，再用
真实栈判断需要何种源码修复；不能把假设的坏点云当默认生产者已证实的根因。

整体不能写成“退出问题全部解决”。本轮关闭的是已真实复现的Gazebo manager
自线程析构缺陷及局部接线验证；历史EGO故障、相机重复加载来源和自然历史
Gazebo唯一归因继续保留。新功能、UI、真实设备和G9–G11仍暂停。

### 19.4 用户要求的偶发性有界复测（2026-10-07）

用户要求“现在试一下是否还有这个崩溃，可能是偶然事件”。本轮只验证，不修改
生产源码、规划/飞控边界或模型负载。证据目录为
`artifacts/shutdown-repeat-20261007.SepTUU/`，汇总为`summary.json`；主agent单独
执行，保持已安装的局部修复，未提交git，未恢复G9、飞行任务或真实设备。

完整组合连续5次，前3次不挂调试器，后2次Gazebo/EGO均由GDB捕获异常栈；每次
独立PX4 rootfs、ROS domain215–219、Gazebo端口11381–11385，原RGB/depth30Hz、
MID36010Hz和CPU感知/SLAM/地图/桥接/飞控/任务/导航/EGO配置不变。退出前连续
就绪等待3/6/10/3/8秒，connected/pose/velocity有效、receipt新鲜且disarmed；
只通知launch owner SIGINT，不向组重复发正常退出信号。预检未连接其它进程，
五次共享PX4/MAVROS端口均已释放，无需等待或删锁/杀旧进程。

验收加严为每次**24个已启动进程全部exit0**、启动PID集合与正常退出集合完全
一致、launch0、无强制收尾或异常行；同时从所属Gazebo实际/proc/maps确认私有
transport库、末尾live0/pending0，按PID＋start_ticks核对所属子进程无残留。带
GDB轮另要求两个真实inferior均exited normally。所有轮均满足，结果如下：

| 轮次 | 调试器 | 连续就绪等待 | 正常退出进程 | 退出耗时 | 结果 |
|---|---|---|---|---|---|
| 1 | 无 | 3s | 24/24 | 0.8658s | PASS |
| 2 | 无 | 6s | 24/24 | 1.4165s | PASS |
| 3 | 无 | 10s | 24/24 | 1.4164s | PASS |
| 4 | Gazebo＋EGO GDB | 3s | 24/24；两个inferior正常 | 0.9653s | PASS |
| 5 | Gazebo＋EGO GDB | 8s | 24/24；两个inferior正常 | 0.8150s | PASS |

五轮/uav_command均0，没有解锁或Action Goal。每轮输入均收到≥3条，原始计数
见各trial/result.json，不把接收计数当作观测全部有效或规划性能。server SHA
`50ec5e23a7666a96143e902647fc5e605cad766c6bcc693fd4185cbc12b955d0`
与第19节最终构建一致；私有transport/EGO及原系统core/transport校验和另归档。
本轮没有SIGSEGV/SIGABRT/self-join，没有删除旧FAIL或用成功覆盖失败。

**额外组件验证**：7个transport生命周期case使用gtest_shuffle随机顺序重复20轮，
实际140次case全部通过，其中真实Connection last-owner路径20次、保持活跃回调
等待清理20次。`lifecycle-repeat.log`含20个迭代和20次7case PASS，进程exit0。
这是确定性边界回归，不是140次完整平台或自然故障概率统计。

**EGO覆盖限制及补充**：地面未起飞odom z约0，低于规划floor0.5m，真实EGO日志
报告odom outside map并清空可信云；这是既定边界，不是本轮放宽/修复项。因此
全平台5轮不能声称验证了正常飞行规划或有效云inflation中的退出。另复用已验证
的合法cloud/odom隔离探针（独立domain209，无Goal），合成odom z1.5m及两个合法
XYZ点，SIGINT/SIGTERM均明确trusted cloud accepted后请求退出：真实GDB inferior
都exit0，约0.21427/0.21429s，原日志/result在`ego-valid-cloud/`。该补充未证明信号
恰处于活跃inflation回调，也不能补足历史崩溃真栈；不冒充该部分已验收。

**结论**：本轮5次完整组合＋有界组件/有效云退出未复现崩溃，可继续正常开发；
有限样本不证明低频故障消失或历史事故“纯属偶然”。已确定的self-join是条件
满足时可真实触发的生命周期缺陷，应保留局部修复；历史EGO SIGSEGV、旧相机
重复加载来源及自然Gazebo历史事故唯一归因保持未闭环。结束时已核对无本轮
仿真、节点、调试器或测试进程残留，详细日志/脚本及SHA清单全部保留。

## 20. 统一导航与任务的真实SITL闭环（2026-10-07，基础范围验收通过）

用户决定搁置低频历史退出故障的进一步取证，保留现有修复及未闭环状态；批准
继续第1项导航/任务真实仿真。仅主agent执行，high项目配置、子agent关闭，不
恢复UI、实机、云台或G9–G11，不自动提交git。旧退出、S21及旧相机加载来源
不作为本轮阻塞，也不倒推认定为误操作/已解决。

### 20.1 目标与验收标准

1. 用当前生产接口和真实PX4/Gazebo/感知地图建立起飞→公开/navigate→普通Land
   正向链，依次核实astar/ego/combined三策略，不用软件plant替代真实动力学。
2. 终态必须匹配真实Goal UUID，status=SUCCEEDED且success=true，检查真实位置
   到位；公开/navigation/ownership必须返回同UUID RELEASED，不能只以取消ACK、
   Action终态或进程退出认定内部排空。
3. 独立取消场景：确认动作已执行后精确取消，真CANCELED＋同UUID释放；有效
   状态/稳定悬停后新导航可执行，证明未留下旧执行锁或旧会话污染。
4. 地图失效场景：只停止本轮所属真实地图生产者，不伪造正常地图/定位或放宽
   TTL；动作必须失败而不误报到达，确认所属子动作/会话排空或如实保锁。
5. 任务引擎使用正式YAML通过/execute_mission完成起飞→navigate→land，同任务
   UUID RELEASED、真实步骤完成、末态新鲜connected/disarmed，保留内外层证据。
6. 原模型/感知负载与飞控/导航约束不变，独立rootfs及冻结DDS，全部所属进程
   正常退出；非预期失败仅精确取消所属动作并等待，不自动追加Land/RTL或解锁。
   预期取消/失效场景中的普通Land是显式独立测试步骤，只有确认终态/释放且
   状态可信、仍在OFFBOARD时才发出，不修改生产任务引擎失败即终止语义。

### 20.2 当前进度

已核对生产导航三策略/地图时限/FollowTrajectory及会话STOP、UUID所有权、普通
起降动作与版本化任务接口。规划首个短直线目标约2m、1.5m航高、0.6m/s，使用
现有perception_demo真实地图/点云；地面高度在EGO图外不作为有效云签收，起飞
后另确认有效云与hover准入。正在新增显式安装式仿真验收入口及证据校验测试。
目前尚未发送本轮飞行动作，不记完成或PASS。实际失败、修复和逐场景结果接续
追加，若需要改变安全边界或控制语义，先向用户确认。

### 20.3 首轮正向结果与验收入口（2026-10-07）

新增 `ros2 run easyfly_sim_launcher navigation_sitl` 显式入口，不被 CTest 自动
发送飞行动作；pure predicate CTest 只检验独立时间/健康、UUID 和真实终态。
复用 D5 独立 rootfs 与冻结 DDS，不改飞控、规划 TTL 或模型负载。使用说明为
`docs/development/navigation-sitl.md`，证据统一在
`artifacts/navigation-sitl-20261007.RHS0ye/`，各轮原日志/result 全部保留。

起飞接口生产到位半径为0.5m，首轮A*成功返回后飞机仍在上升，原测试已要求
低速但未要求达到预设航高；因此首轮导航保持实际约1.208m，而非1.5m。该轮
真实导航误差0.07489m、SUCCEEDED/true、同UUID RELEASED、普通Land新鲜disarm，
24进程正常退出，通过该轮实际目标验收，但不记作1.5m稳定起飞验收。随后
**只加严测试**：独立起飞后等待实际z=1.5±0.1m、fresh OFFBOARD/低速连续1s
才导航，不修改生产起飞半径或强行改状态。

EGO/combined后续两轮均满足加严条件，起飞后真实trusted cloud accepted，实际
FollowTrajectory/会话开始、跟踪、STOP、同公开UUID RELEASED；无需伪造云或定位。
EGO到位误差0.04405m，combined误差0.05979m，均真SUCCEEDED/true和普通Land
新鲜disarm，各24/24进程exit0、transport live0/pending0、无强制收尾/所属残留。
这证明已知短直线自由空间闭环，不冒充复杂障碍绕行或实机安全验证。

新增纯谓词18case＋原profile launch9case通过，两项CTest通过；新脚本/测试
flake8、pep257、copyright通过。正在验证组合导航取消/地图生产者丢失、正式
任务三步闭环，并补区域搜索的两条几何扫描带及四个内层导航UUID排空证据。
本节此时仍进行中，不把未跑场景预先记PASS。

### 20.4 取消、生产者失效及任务结果（2026-10-07）

`combined-cancel`：导航4m，反馈出现且真实位移≥0.15m后只精确取消其Goal；
ACK0，真实status5/success=false，导航UUID `6f67843ec76142e7b8736d848b52e981`
返回RELEASED。同一平台稳定悬停后新导航UUID
`d8f32c5bab0a4e17a9969cf2555b6d4d`真实成功并释放，再显式Land新鲜disarm。
两条导航的匹配START/STOP完整留存，24进程正常退出/无残留。本轮发生在后续
增强取消ACK UUID记录之前，不补写它未记录的数据；真实结果/释放已按各句柄
精确UUID证明。最终脚本追加ACK goals_canceling UUID、触发时真实状态和恢复
到位误差，并对每个Goal的全部session要求START及最后STOP。

`combined-map-loss`：先真实运动，然后核对PID/start_ticks仍为本轮所属
semantic_map_node，只向它SIGINT。约1.055s后公开导航真ABORTED/false，原消息
`planner_emergency_stop`；UUID `7d0b424727b54274aa6057c25b5227c4` RELEASED，
同session START/STOP。可信状态/原OFFBOARD及悬停确认后独立Land成功；被停止
地图节点自身exit0，加最终其余退出仍24/24，transport排空、无残留。此处实际
停止占据图＋EGO云共同生产者，证明其丢失安全失败，不声称分别验证了两个
输入TTL；没有启动自动补偿，也未改生产任务失败即终止。

`combined-mission`：通过正式版本1 YAML的3步takeoff/navigate/land，公开任务
UUID `b6939d53ec5e4efa83f68fde15246ccd`真实SUCCEEDED/true，三步完成反馈，
导航完成观测误差0.05040m；任务UUID与内层导航UUID
`91e3fbbf3779a6f2a8a26851367aa30f`均RELEASED，内层匹配START/STOP。末态新鲜
connected/disarmed，24进程exit0、transport排空、无强制退出或残留。原始反馈
及源/接收时间在该轮result/states.jsonl；不是软件plant、仅解析YAML或SDK伪后端。

最终脚本新增会话闭合8case，纯谓词共26case＋profile9case通过；两项CTest
通过（colcon含套件节点计数37，0失败），flake8/pep257/copyright及package.xml
xmllint通过。当时脚本和安装副本SHA一致
`67c13df3ac0bbb83b39a20793bf8a2310511f2e5b34a167fc693a26fae2a622d`。
正在执行搜索场景；最后补加严1.5m航高的A*及最终取消证据后再签收本轮范围。

### 20.5 补跑发现A*精确目标缺陷及修复（2026-10-07）

`combined-search`已真成功：两条带/四个导航，反馈几何面积依次0/1.65/3.3m²，
单调且进度与面积一致；搜索UUID `3b7088e7c9144e009bdb04076bbd08f9`及四个内层
导航UUID全部RELEASED，每条匹配START/STOP，普通Land新鲜disarm，24进程exit0、
transport排空、无残留。完整UUID/端点/反馈保存在该轮result，不虚报传感器覆盖。

加严1.5m起飞后的`astar-happy-settled`实际**FAIL**，必须保留：公开导航虽然
SUCCEEDED/true、UUID RELEASED，验收观测距原始目标0.18035m，大于0.11m观测
上限；没有追加Land/RTL，只按所属句柄排空并关闭本轮，24进程仍正常退出。
原目标(1.9570558518,0.0060870671)，生产末航点却为(1.9,0.1)，日志明确“段1/1
到达(1.9,0.1)”。不是放宽误差后通过，也不把正常退出当飞行PASS。

原因已确定：公共A* helper把终点保留为栅格中心，GlobalPlanner直接发送该值；
实际0.2m格中心偏移叠加0.1m子航点半径，能使真实到位偏离原始Goal。另同格
起终点只回传一个起点，后端0段执行即可成功，漏掉水平/高度动作。两项新增
纯C++回归在修复前均真实FAIL，原日志`astar-endpoint-before.log`完整保留。

修复：在free目标格中心之后追加**精确原目标，再进行既有LOS剪枝**，避免将
已经检查的最终连线在剪枝后强改目标；同格情况也保留起终点并执行真实动作。
目标占据/越界拒绝与原地图/到位半径保持不变。combined原有剪枝后强换终点
改为使用公共helper的已规划精确终点，不能旁路检查。没有更改TTL、飞行状态、
安全边界、EGO避障或取消补偿语义。

同次审查发现A*子航点只判断SUCCEEDED枚举、没检查result存在及success=true，
现补齐真实结果条件，避免“终态成功但payload=false”被父导航误当成功。新增
ROS节点契约回归以显式mock flight检验精确xy/z、同格也发送航点、假成功必须
ABORTED；此测试不是飞行动力学签收。正在运行11项规划功能CTest及修复后的
真实SITL A*，后续补combined相关路径回归和最终取消证据；本轮仍未签收。

### 20.6 修复复验及新发现的准入观测缺口（2026-10-07，进行中）

`astar-happy-fixed`真实PASS，原接口/0.1m半径不变；到位误差0.09577m，同UUID
RELEASED、普通Land新鲜disarm、24进程exit0/transport排空/无残留。公共A*两项
回归已PASS。首次11项功能CTest中10PASS、新增endpoint契约断言均通过，但其
mock cleanup只给ros2 run父进程SIGINT未转发到node，退出等待超时，整套记录
仍FAIL；已核对并只清理所属domain89的PID84366/84367独立组，再修正mock组
SIGINT（不是SITL launch owner策略），单项及整套11/11随后PASS，原FAIL日志
保留。cppcheck/lint_cmake/xmllint三项PASS，新Python测试窄lint通过。

继续真实`combined-cancel-fixed`时，旧导航真CANCELED/false，ACK中的精确UUID
及RELEASED均正确；稳定悬停后新导航却真ABORTED/false，消息
`planner rejected session: invalid_target_speed_or_stale_sensors`。新旧UUID都
RELEASED，没有错报成功或故障锁泄漏；本轮整体**FAIL**，没有追加Land/RTL。
其后串行批次立即停止，未凭失败后自动重试Goal或执行后续场景。正常退出24
不能把该轮算PASS。仅凭当前泛化拒绝消息不能确定是odom、trusted cloud或
目标/速度哪项失效，不能认定为A*修复造成、误操作或“偶然无害”。

下一步增加**观测而非放宽准入**：EGO START拒绝日志记录分别的odom/cloud
新鲜度、目标/速度及源/接收/时钟；GridMap记录失效odom年龄与拒绝cloud源年龄。
原判断、调用短路顺序、TTL、未来容差、取消/STOP和急停恢复规则保持不变。
仿真入口新增inputs.jsonl，仅记录本轮真实地图/云header、尺寸、独立时间，
不伪造/回放数据。当前在独立新rootfs执行带诊断的正常取消/再导航场景；未将
准入拒绝从验收中排除，结果接续追加，需要改变控制语义时先问用户。

### 20.7 取消后EGO输入积压与旧轨迹会话混淆（2026-10-07，修复复验中）

带诊断`combined-cancel-diagnostic`再次FAIL：拒绝时odom=false，now33.5s、
odom源32.2s、接收33.1s，源年龄1.3s超出原1s阈值；不是速度/目标越界或
不允许重用已释放Goal。进一步`combined-cancel-odom-trace`记录实际/odom与云，
32–34.2s窗内148条odom源年龄0–0.1s、23条cloud源年龄0s，只有一个合法odom
发布者；说明消费者所用状态有滞后，不能靠缓存receipt或扩大TTL让它“新鲜”。
该轮新START受理但随后ABORTED/planner_emergency_stop，旧新Goal都释放、24
进程正常退出，整体依然FAIL；未追加Land，原日志和inputs完整保留。

后一轮另有明确生命周期问题：取消STOP后local_data仍保留旧traj2；新会话尚
在GEN_NEW_TRAJ时runtime checker把旧traj2/t2.5当成正在执行的轨迹，报0余量
碰撞并急停。STOP已停旧会话下游流，新会话没有发布首条曲线；不得因旧曲线
仍存在就将其归给新Goal。此处不判定近场占据点是否“误障碍”，不移除点云或
忽略真实当前曲线的碰撞，避免凭猜测扩大自由空间。

实现两项限定修复：

- FSM odom、GridMap独立odom/cloud使用SensorDataQoS KEEP_LAST(1)，只保留实时
  最新一帧，避免可靠历史队列回放旧控制观测；可靠上游可匹配这些订阅。原源
  时间/接收/clock检查、1s TTL、0.2s未来容差全部保留，丢流仍失败关闭；维持
  原单线程执行，不引入并行数据竞态，模型/感知频率与地图持久化不变。
- 记录成功本地发布曲线的会话，STOP/新START清空此归属；runtime只扫描当前
  会话已发布的曲线。fresh cloud和odom/depth失效急停检查仍在会话过滤之前，
  新曲线仍过完整规划碰撞/速度验证，发布后恢复全部runtime检查；急停曲线的
  会话、ACK恢复门及轨迹ID单调水位不重置。非受管旧模式不改变。

新增纯契约回归证明old/empty session不能归属new，匹配new才允许runtime，
非受管旧语义保留。正在统一重建plan_env/ego_planner后做真实复验；前一轮
诊断只重编ego时GridMap新增日志尚未编入，不能以没有该日志认定没有失效。
本次会同时编译两个包，不将未执行/未构建的变更当作PASS。

### 20.8 最终版本阶段结果（2026-10-07，正在完成剩余复验）

plan_env/ego_planner及仿真入口统一构建成功，实际二进制/脚本指纹保存在
`navigation-final-binaries.sha256`。plan_env五项CTest（含实际depth路径ASan）和
EGO四项纯契约/几何CTest全部通过；新会话归属断言通过。没有恢复搁置的历史
退出长循环、GDB故障取证、旧malformed探针或改动系统库。

`combined-cancel-latest-session`与独立新rootfs的`combined-cancel-confirm`连续
两轮均真实PASS：各旧Goal运动后精确cancel，ACK goals_canceling对应本Goal，
真CANCELED/false及UUID RELEASED；新Goal到位并释放，恢复误差分别0.05535m
和0.08993m，匹配START/STOP，显式Land新鲜disarm，24/24退出、无强制收尾/
transport遗留/所属残留。两个独立平台不是在失败的同Goal上自动重试。

`combined-map-loss-final`同最终版本亦PASS：真实运动后仅停止所属地图生产者，
约1.01471s后真ABORTED/false，消息`navigation input invalid or stale`，同UUID
RELEASED、匹配STOP，确认控制/悬停后独立Land成功；24/24正常退出。此前EGO
cloud路径先报告planner_emergency_stop、本轮协调器地图失效先报告失败，均
保留原消息，不要求固定竞态赢家，也不把地图失效改成成功或改变TTL。

正在重跑同最终版本的正式任务与搜索，完成后统一签收；旧FAIL原目录/日志
不删除、不覆盖，最后验收需区分修复前、诊断中与最终版本。

### 20.9 搜索复验出现本地trusted-cloud失效（2026-10-07，尚未签收）

`combined-mission-final`已PASS，到位误差0.04317m、任务与内层UUID RELEASED、
匹配会话及新鲜disarm，24进程正常退出。但`combined-search-final`在第二个
导航端点执行中因NO_TRUSTED_CLOUD真失败，搜索ABORTED/false、UUID RELEASED，
没有虚报覆盖或追加Land/RTL；整体仍FAIL，24进程正常退出只说明清理正确。
因此不能用旧搜索成功覆盖这个新失败，也不能签收整个第20节。

该轮32–44.7s记录实际318条cloud，无零源时间或空帧；42–44.7s窗有182条
odom源年龄0–0.1s、28条cloud及28条grid源年龄0s。上游持续正常不等于EGO内部
已处理到最新数据，当前新日志没有odom丢失/source-age拒绝记录。接续补充
真实cloudCallback的steady处理耗时、处理后的源/ready年龄，以及ready过期
具体年龄。当前plan_env缓存为Debug（-g，未优化），这一点仅作为候选解释，
在实际耗时证据之前不擅自认定原因、移除障碍、降低模型负载或放宽1s阈值。

测试入口还修正了失败摘要：不把所有逐帧feedback重复塞入异常字符串，完整
反馈仍在result.json，不删旧原始日志。这只是证据输出整理，不影响动作结果。
当前独立场景`combined-search-timing`只新增计时观测，保持现有控制/感知配置。

### 20.10 处理预算证据及地图库优化（2026-10-07，复验中）

保持未优化Debug的`combined-search-timing`再次出现同类NO_TRUSTED_CLOUD失败，
搜索真ABORTED/false、所属锁释放，没有追加Land，原FAIL保留。真实计时记录
471–1000点的cloudCallback单帧约390–723ms（另501点563ms），源/ready年龄在
处理结束已达0.3–0.6s，上游原本10Hz（100ms帧预算）。这直接证明该构建下
地图处理跟不上输入，不能仅凭上游/clock在更新就认定内部参考仍新鲜。

进一步记录fresh odom替换时，上一内部参考失效导致清空trusted层的具体源/
接收时间，以区别真实源丢流与本地处理延迟；不改清空策略。原Debug编译flags
`-g ...`不含优化，保持该Debug ABI/符号及断言，不改OpenCV/TBB或NDEBUG选择。
仅对plan_env库在GNU/Clang Debug或未指定配置时加入-O2（Release已有优化不
覆盖），独立ASan depth目标的-O1不受影响。地图尺寸、kernel/占据持久化、
点云/感知Hz、丢流TTL、完整碰撞与源年龄判断全部不变。

这是处理热路径/构建预算修复，不是降低模型负载或把处理完成时间冒充新观测
源/接收时间；对超预算或真正失效仍失败关闭。现在用同一原场景/输入配置
执行`combined-search-optimized`，逐帧接受日志新增wall_ms/source_age以便与
未优化原失败比较，随后重复搜索及取消/地图失效/任务回归再签收。

### 20.11 优化构建的首轮真实搜索结果（2026-10-07）

`combined-search-optimized`真实PASS：搜索UUID
`0764570cba8a461d957e8686b034cfb4`与四条内层导航UUID全部RELEASED、每条匹配
START/STOP，最终几何面积3.3m²/进度1，普通Land新鲜disarm，24进程正常退出、
transport排空、无强制收尾/所属残留。原模型/CPU感知/云与地图配置不变；不是
减少占据点、改帧率或放宽阈值后达成。反馈不承诺传感器真实覆盖。

原接受日志52个采样的实际cloud处理wall_ms为102.110–207.162ms，明显小于
未优化390–723ms；本轮没有再出现内部trusted cloud失效而中止。虽然已大幅
减少开销，这不是宣称每帧<100ms或每帧都处理：latest-only会丢掉积压的旧帧，
实际受理帧仍要通过源/接收新鲜度与完整占据检查，输入断流仍须真实失败。
本机有限有界结果不能代表任意硬件/点数/并发负载，200000点输入上限也不是
本轮全部经过性能签收。

实际优化版二进制/脚本指纹另存`navigation-optimized-binaries.sha256`，不会用
旧版本指纹标记新版本。现在独立重复搜索，并对同优化版重跑真实map-loss和
正式mission，再完成原有ROS会话/失效回归及窄lint。之前所有FAIL保持可追溯。

### 20.12 正式任务近场急停与仿真雷达距离缺陷（2026-10-07，复验中）

优化版`combined-search-optimized-confirm`再次完成四端点/3.3m²，
`combined-map-loss-optimized`预期失败后精确释放并独立Land，均PASS/24正常退出。
但`combined-mission-optimized`真ABORTED，消息`step_failed:planner_emergency_stop`，
任务/内层导航精确释放、匹配STOP、24正常退出，无追加Land。当前轨迹traj4
在EXEC中样本(0.51,-0.05,1.41)命中grid_occ=1，odom约(0.49,-0.08,1.38)，
trusted_cloud=1。这是当前会话真实占据检查，不是此前旧轨迹残留问题；不能
跳过当前轨迹检查或因为原点附近预期空旷就忽略占据急停。

独立`mission-lidar-trace`在旧距离实现上PASS，且有限的候选自身碰撞观测未
捕获符合条件的命中。因此尚不能唯一归因为自身回波，亦不能用这一PASS覆盖
上一FAIL。全部原始失败/观测目录保留。

核对[Gazebo 11.10.2官方实现](https://raw.githubusercontent.com/gazebosim/gazebo-classic/gazebo11_11.10.2/gazebo/physics/MultiRayShape.cc)：
原生射线起点是origin+min*axis，GetRange返回min+实际射线长度。项目Livox插件
在Load和逐帧InitializeRays中却用origin+min*axis-min*axis，把起点退回origin；
本模型min=0.2m，所以有效回波平白多出0.2m。这是可确定的独立几何缺陷，
会影响近场/地面回波和所有外部物体测距，不能仅修搜索路径或修改安全阈值。

已把两个起点统一为明确的rayStart辅助函数，保留原最小/最大量程、外参、
近障处理/占据膨胀/碰撞急停，不新增自身模型过滤、扩大blind zone或调低
传感器负载；临时有限命中日志撤回。新增原生ODE碰撞几何回归，覆盖2m外部
表面、0.25m盲区内回波、最小量程内几何、最大量程外几何、旋转/平移外参与
零最小量程。正在进行该修复的实际正式任务复验；在充分证据前不把距离修复
宣称为上一轮偶发急停的唯一原因，也不签收本节。

### 20.13 距离修复后的真实任务及负向闭环（2026-10-07）

`mission-range-fixed`和独立`combined-mission-range-final`均PASS，正式v1任务
3/3步、进度1，导航观测误差分别0.08299m/0.06831m，同任务及内层导航UUID
精确RELEASED、每条会话匹配START/STOP、普通Land确认新鲜disarm。没有加入
额外hover步骤/降低climb_speed以隐藏原三步流程问题。

`combined-cancel-range-final`PASS：实际运动后对UUID
`e08f55f636ba4f33816d53f128adb6ad`发精确取消，ACK=0且列表包含该UUID，最终
status=CANCELED、success=false、同UUID RELEASED。稳定悬停后新UUID
`6f43b7d04de74765a1efb7996fb971b6`导航真成功，误差0.08007m、精确释放；两条
会话均START/STOP，最后普通Land新鲜disarm。不是只看到cancel ACK就准入新任务。

`combined-map-loss-range-final`PASS：实际运动后仅停止本轮地图生产者PID12085，
约0.99207s后导航真ABORTED/false，保留消息`navigation input invalid or stale`；
同UUID RELEASED、匹配STOP，确认新鲜OFFBOARD/稳定悬停后，显式独立Land成功。
以上4个完整仿真均24/24正常退出、transport live/pending排空、无强制收尾和
所属残留。搜索及三策略最终正向场景仍在串行执行，暂不把未跑结果写成PASS。

组件补充：EGO原生ROS会话和managed地图失效测试2/2 PASS（8.76s）；EGO四个
gtest及initial_sampling合计5/5 CTest PASS；plan_env 5/5（含原ASan depth）PASS；
Gazebo插件5/5（其中新射线几何6case）PASS；sim_launcher 2/2 CTest PASS。
新增文件窄flake8/pep257、C++ cpplint/uncrustify、CMake lint和完整Apache版权头
通过；本机cppcheck 2.7默认会跳过，显式允许该版本并加载googletest库后实际
分析新几何头/测试通过，不把默认跳过当作已分析。功能测试与窄lint不冒充整个
工作区零lint债务或全部功能验收。

实际安装二进制指纹为`navigation-range-binaries.sha256`，私有server/transport
另存`navigation-range-server.sha256`，其SHA与此前版本相同；未动系统库。
导航到位是新鲜UAVState观测值，不声称Gazebo ground-truth定位精度；正式任务
近场单次急停仍未取得唯一归因，距离缺陷和最终复验结果分别记录。

### 20.14 最终有界验收与交付（2026-10-07）

以下8轮使用相同最终导航/EGO/地图库/雷达实现、原模型与CPU感知配置；每轮
独立rootfs及证据目录，串行执行。原FAIL不删除、不覆盖，不算入以下PASS。

| 最终独立场景目录 | 真实结果及关键证据 | 验收 |
|---|---|---|
| `mission-range-fixed` | 正式v1三步完成，导航观测误差0.08299m，任务/内层导航释放 | PASS |
| `combined-mission-range-final` | 独立重复同三步，误差0.06831m，任务/内层导航释放 | PASS |
| `combined-cancel-range-final` | 实际运动→精确CANCELED/释放→新导航，恢复误差0.08007m | PASS |
| `combined-map-loss-range-final` | 只停所属地图节点，0.99207s后真ABORTED/释放，随后独立Land | PASS |
| `combined-search-range-final` | 两条带/四端点，几何面积3.3m²、进度1，外层和四内层全部释放 | PASS |
| `astar-happy-range-final` | 统一入口A*短程到位，误差0.09651m，同UUID释放 | PASS |
| `ego-happy-range-final` | 统一入口EGO短程到位，误差0.07725m，UUID释放及匹配START/STOP | PASS |
| `combined-happy-range-final` | 统一入口组合策略短程到位，误差0.08419m，UUID释放及匹配START/STOP | PASS |

每轮均新鲜connected/disarmed、24个启动进程与24个正常退出PID集合完全匹配，
launch exit0、transport live/pending排空、无强制收尾/异常退出/所属残留。
`final-case-audit.json`另逐项复核同UUID RELEASED、真实status/载荷、取消ACK所属
UUID、任务3/3反馈、搜索四UUID、末态源/独立接收新鲜度、脚本与server指纹。
结束后再次按各轮所属PID/start_ticks读取/proc确认无同身份残留，证据为
`final-owned-process-audit.json`。这些是8轮完整SITL，不是8个mock或组件case。

最终规划器功能CTest 11/11 PASS（95.72s），包括精确终点/同格/假成功拒绝、
协调器及真实EGO链组件测试；它们与实际飞行结果分开记录，不冒充额外真实
SITL。EGO 2原生ROS＋4 gtest＋initial_sampling、plan_env 5、launcher 2仍通过；
插件再次构建后5/5 CTest PASS，新增ODE几何6case仍通过。最后新增测试仅改用
所需collision.h而非ODE总头，消除未使用系统misc.h的char*警告；最终插件构建
exit0且无stderr，窄cppcheck/googletest、cpplint、uncrustify再通过。
完整Apache声明/新增Python窄flake8、pep257及CMake/XML lint均有独立日志；未
执行/宣称全工作区历史lint全部清零。任务相关diff --check通过。

补充版权头/测试include后重新构建，`navigation-range-binaries-rebuilt-check.log`
与server对应check证实实际运行二进制SHA不变，因此没有拿旧二进制结果签收
新逻辑。公共规划实现共享库、飞控/任务/搜索及traj_server另存
`navigation-range-runtime-libraries.sha256`；初始六项及server/transport清单仍
保留。全部证据在`artifacts/navigation-sitl-20261007.RHS0ye/`。

**本批交付**：第20.1节基础短程三策略、真实取消恢复、地图丢失关闭、正式
三步任务以及本批追加弓字搜索已跑通，显式安装入口/纯验收谓词/文档可复用。
修复A*精确终点及子动作假成功、传感器旧帧积压、旧会话曲线误检查、未优化
Debug地图处理预算，以及仿真雷达系统量程偏差。未放宽TTL、占据/碰撞或飞控
准入，不静默降级，不新增生产失败补偿。

**保留边界**：§20.12当前轨迹近场单次占据急停仍未唯一归因；最终复验未再
出现，不等于已证明只由距离偏差导致或永不复发。O2优化后的处理也不是恒定
<100ms，最终两轮任务/取消部分采样仍达到约250–406ms；latest-only与源/接收
判断保留，任意负载不作性能保证。观测位置不是仿真ground-truth精度认证，
搜索不是传感器真实覆盖；复杂静态/动态障碍、多段任务中途取消/超时和外部
接管的进一步实际矩阵尚未由本批签收，不能据此记完整D1/D3或全平台完成。
UI/实机/真实云台/G9–G11及用户搁置的低频历史退出故障仍不启动；旧修复保留，
未擅自提交git。后续若复现近场急停，先记录实际障碍表面/时间/占据来源，再
判断原因，不追加自身过滤或跳过碰撞来追求PASS。

## 21. 任务级取消、超时与外部接管（2026-10-07，本批基础范围验收通过）

用户批准继续第1项风险边界，仍只由主agent执行；不启动静态绕障优化、UI、
实机、真实云台、G9–G11或已搁置的历史退出取证，不自动提交git。

### 21.1 目标与验收标准

1. 正式v1任务进入navigate或search步骤并确认内层真实运动后，精确取消外层
   ExecuteMission；任务真CANCELED/false，所属搜索/导航/FollowTrajectory真实
   终态、对应UUID RELEASED及每条规划会话STOP，不能只以cancel ACK判定完成。
2. 分别用任务文件显式步骤期限触发navigate/search超时，任务真ABORTED/false
   并保留step_timeout，不继续后续Land或虚报覆盖；同样逐层核实排空。
3. 仿真外部接管第一批选AUTO.LAND：仅一次向本轮私有domain内MAVROS请求该
   模式，确认新鲜飞控实际模式7，而非只认mode_sent；任务/所属子动作失败
   关闭，不抢回OFFBOARD，平台UAVCommand及实际MAVROS setpoint流停止。等待
   PX4自己完成已请求的降落，不追加本平台Land/RTL/上锁或模式补偿。
4. 取消/超时已确认排空后，观察任务未继续后续步骤；仍在新鲜OFFBOARD且
   稳定悬停时，独立执行预先声明的恢复任务，验证任务与导航槽可复用。它是
   测试步骤，不是生产任务的失败补偿。非预期失败只精确排空所属动作并收尾
   仿真，不追加飞行动作；未确认释放不得发恢复任务。
5. 结果不明/迟到终态/拒绝取消的保锁由现有真实MissionFSM/SearchNode＋SDK
   的mock后端组件测试另行复核，与真实PX4/Gazebo六类场景分开记录，不冒充
   已在实际飞行中制造全部未知结果组合。额外保留本平台普通Land的正向任务
   作为“自身降落不误判外部接管”回归。
6. 原模型/CPU感知/飞控准入/TTL/占据与碰撞约束保持，不伪造正常状态或地图；
   全部所属进程正常退出、transport排空、无强制收尾/残留，原FAIL保留。

### 21.2 当前进度

已阅读任务/搜索执行器、安全检查、SDK所有权及普通飞控接管停流契约；现有
组件包含延迟取消终态、未决所有权、拒绝取消和超时保锁测试，正在复核。
拟扩展现有显式navigation_sitl入口，保存search/navigation/FollowTrajectory/
Land/Takeoff的真实UUID状态、MissionStatus及平台/实际setpoint观察。新增场景
只允许combined以验证完整轨迹链，不改变原有基本导航入口的策略支持。
证据根目录`artifacts/mission-lifecycle-sitl-20261007.YznI0t/`，目前未发送本批
真实飞行动作，不记PASS；实际问题及修复继续追加。

### 21.3 首轮取消及恢复观测时序（2026-10-07）

组件6/6 CTest PASS（20.92s），包含迟到准入/终态、拒绝取消、递归未决所有权
保锁；不将mock后端结果当作实际飞行。入口新增场景后纯谓词先39、再加入
真实轨迹意图/实际下游流触发条件成为40case，均通过。首轮
`mission-nav-cancel`和更严格触发的`mission-nav-cancel-final`真实PASS：任务
真CANCELED/user_cancel，navigation和FollowTrajectory精确GetResult得到真
CANCELED/false，任务与导航UUID RELEASED、匹配会话STOP，没有进入第四步
Land；独立恢复任务真成功并确认disarm，24正常退出。

`mission-search-cancel-final`原轮保留FAIL：搜索第三个子导航实际运动后取消，
任务/搜索/当前导航/FollowTrajectory均真CANCELED/false，前两段真实SUCCEEDED，
第一条带几何面积1.65m²/进度0.5保留，层层释放、匹配STOP，没有启动第四个
端点或任务Land。随后独立恢复任务真成功/普通Land完成，但验收用更晚的
Mission完成反馈pose测得0.11249982m，超过既定0.11m观测阈值，因而整体FAIL，
24正常退出不消除此失败；串行批次立即停止，未继续后续场景。

取证：恢复FollowTrajectory首次SUCCEEDED状态事件在steady3313.880496s，
最近接收的UAVState在3313.839665s、源44.9s，实际观测误差0.06569696m；
控制器原日志到达dist约0.07m。任务完成navigate反馈在3314.099765s（晚约
0.21927s）使用源45.1s，观测已成0.11250m。控制器原契约是独立轨迹序列帧
连续5次进入半径，不包含稳定低速到位条件；本轮不悄悄加入新的控制策略，
也不把后来的漂移或上层收到消息时间当作下层成功时刻。

验收记录改为保存每个子UUID第一次真实终态事件时的独立位置/源和接收时间，
GetResult仍另证实真实成功载荷；恢复到位按最后成功FollowTrajectory事件的
新鲜观测检查，阈值仍0.11m，不从任意窗口挑选最小误差。更晚任务反馈误差
独立保留，不删除原FAIL。观测过期/非OFFBOARD/非有限等仍拒绝；后续“稳定
到位/低速成功”若开发需单独明确语义，不在本批擅自改变。

另核对桥接原契约：控制器接管后停发新UAVCommand，桥接仍按原1s源处理/
steady缓存期限自然停流，服务切模式不续命。原拟一刀切0.5s下游零发布会
误把既有缓存尾流判为故障，实际运行前已修正观测阶段：控制器确认模式后
0.5s起静默、下游1.5s起至少连续1s静默，延迟只是验收接收/调度余量，不改
生产1s参数。补看position/velocity/attitude/raw四类MAVROS出口，避免只看raw
漏掉其他类型；不关闭桥接、不改TTL或清空队列来得到PASS。新纯回归覆盖两
类时序，正在用同一新入口独立重跑七场景，旧目录/脚本指纹不覆盖。

### 21.4 独立复跑在注入前被电池保护终止（2026-10-07，排查中）

`mission-search-cancel-verified`在搜索第一条导航期间、尚未满足计划的第三段
取消条件时，现有任务安全检查报告`battery_invalid_timeout`，桥接真实请求
AUTO.RTL，PX4日志确认进入RTL；导航/搜索/轨迹最后被精确取消，任务与导航/
搜索排空，24正常退出。但这不是预定取消场景，不记PASS，串行批次已停止，
未执行之后的步骤超时或计划AUTO.LAND场景。原低电量/电池失效RTL保护由既有
代码触发，不是验收脚本追加的失败补偿；本轮不会关闭它或延长宽限期。

目前原观测只保存了pose/velocity，不足以断定是原始电池数值、消息丢失、
接收时限还是发布来源问题；不凭一次失败猜测原因。已补保存每条原始
`/mavros/battery`源/接收时间、voltage/percentage/present/location/serial及
每条UAVState battery_valid/voltage/remaining；非有限值如实记为字符串，未
忽略非法电池帧或伪造有效标记。注入前若任务已终态，另保存真实status/载荷
而非只写泛化异常。`mission-search-cancel-battery-trace`只新增观测后独立运行，
维持原所有安全/感知参数；在实际电池证据出来前本批未签收。

### 21.5 搜索取消通过、超时验收的段时间边界（2026-10-07）

`mission-search-cancel-battery-trace`实际PASS：第一条带1.65m²/进度0.5保留，
第三段真实运动后外层任务及搜索/导航/FollowTrajectory真CANCELED，前两段
真成功，逐层释放/匹配STOP；独立恢复任务成功，轨迹终态观测误差0.05193m，
后来的任务反馈误差0.12840m独立记录，普通Land确认disarm，24正常退出。
本轮34条原始电池消息，主battery id0持续有效，最大接收间隔2.86865s，飞行
中没有battery_valid=false。启动阶段另有匿名SYS_STATUS样式消息voltage约
65.535/percentage约-0.01，随后id0正常；该启动消息不能唯一解释上一轮飞行
时电池失效，原FAIL/未归因保留，不写成已修复或通过放宽电池策略解决。

`mission-nav-timeout-battery-observed`实际PASS：主任务ABORTED/step_timeout，
所属导航/轨迹真CANCELED/false，精确释放与STOP，无后续哨兵Land；独立恢复
任务真成功、终态观测误差0.08813m，普通Land新鲜disarm、24正常退出。

`mission-search-timeout-battery-observed`整体仍FAIL，原证据保留：外层已经真
ABORTED/step_timeout，但入口错误地把“首次证明运动”时的第一进场导航永久
视为超时应取消的活动段。原记录该段4265.72284s已真成功，父搜索4273.78217s
才CANCELING（两者相隔8.05933s），第二个导航及轨迹在4274.02278/4273.85212s
真CANCELED，搜索真CANCELED/false，最后面积0m²。这是预算内先完成进场后开始
扫描、随后父步骤超时的正常顺序，不是超时后把活动子动作误报成功。

修正验收时域：timeout采用该步骤父Search/Nav实际CANCELING或非成功终态的
首个观测边界，允许在此边界之前已真完成的段；边界之后的成功仍拒绝，且
必须观察未完成导航和FollowTrajectory的真实非成功终态。取消/接管仍核实
发请求时实际活动的精确UUID，不改变生产步骤期限/停止传播，也不把面积
0当成完成。补充纯回归后同最终入口重新串行执行七场景，未签收全部结果。

### 21.6 初始第一轨迹碰撞拒绝与验收隔离选择（2026-10-07）

`mission-search-timeout-signed`在被测运动/超时触发之前真ABORTED，消息
`step_failed:navigation_failed:planner_emergency_stop`；EGO记录
`FIRST_TRAJ_COLLISION: SEQUENTIAL_START→EMERGENCY_STOP`，实际UAVState高度约
1.35486m、速度低、battery_valid=true。任务/搜索/导航排空，24正常退出，无
额外Land或测试模式补偿；整个预定timeout场景仍FAIL，不用安全拒绝冒充超时
注入PASS。当前仅是第一轨迹碰撞判定，不与§20的运行期碰撞自动合并归因，
也不跳过首次轨迹碰撞或清空占据来得到PASS。

现准备任务起飞后固定hover2s，并不保证实际高度达到1.5m或地图爬升过渡结束。
已向用户询问：是否用另一个正式takeoff＋hover准备任务，确认新鲜OFFBOARD、
实际高度1.5±0.1m及稳定后，再提交被测导航/搜索任务；保持全部生产策略，
原初始爬升/电池失效FAIL另保留。未获选择前不修改准备流程。正在独立验证
原流程下导航AUTO.LAND接管，能继续检查的子范围不假定已经全部签收。

### 21.7 两类原流程外部AUTO.LAND接管通过（2026-10-07）

在等待准备流程选择时保持原四步任务，不更改hover/起飞/安全参数，独立
`mission-nav-land-direct`与`mission-search-land-direct`实际PASS。均在被测
真实运动后仅发一次MAVROS外部AUTO.LAND，确认新鲜armed/实际模式7；任务真
ABORTED/`external_land_takeover`，所属导航/轨迹（搜索场景还含搜索）真实
非成功终态、精确UUID释放、匹配会话STOP，未执行任务哨兵Land，也未切回
OFFBOARD或追加本平台Land/RTL/上锁。随后等待PX4自身降落并新鲜disarm，
24/24正常退出、transport排空、无强制/残留。

导航接管：最后UAVCommand比确认模式时刻早0.04298s，最后raw setpoint在确认
后0.95018s，符合原bridge 1s缓存尾流；position出口早已静默，之后各出口
均保持静默，armed期间没有模式回抢。读取真实GetResult：导航CANCELED/false，
FollowTrajectory ABORTED/false且保留`external mode takeover; setpoint stream stopped`。
上层任务与子动作的取消/失败枚举不要求全层相同，但不得成功或虚报释放。

该结果只覆盖仿真AUTO.LAND，未验证真实RC、AUTO.RTL/POSCTL或解锁/切模式
未知结果的实际飞行矩阵；未决保锁仍以组件证据单列。现有导航取消、搜索
取消、导航超时以及两类LAND各已有通过结果，搜索超时的修正后独立全场景
仍待通过；正在原流程下做一次有界确认，若再遇初始碰撞则保留FAIL，不
以无限复跑或关碰撞得到签收。准备流程选择未获答复，仍未修改。

### 21.8 用户确认独立准备，原流程搜索超时通过（2026-10-07）

用户选择“独立准备任务后验证”。已将六类入口改为正式准备任务
takeoff(1.5m/0.3m/s)＋hover10s（原任务电池/遥测保护全部启用），真成功并
精确释放后，再观测实际1.5±0.1m、新鲜OFFBOARD及持续1s速度≤0.3m/s；条件
不满足则失败，不追加被测任务。被测任务为hover0.3s→navigate/search→Land，
哨兵为第三步，仍通过正式v1接口，后续取消/超时/接管及独立恢复规则不变。
这是用户确认的验收准备隔离，不修改任何生产动作成功、地图清空、TTL或
飞行策略；旧起飞后hover2s并不能保证稳定准备的FAIL继续保留。

在选择到达前已运行的`mission-search-timeout-edge-confirm`原流程实际PASS：
任务真ABORTED/step_timeout，预算内完成的进场正常成功，未完成搜索/导航/
轨迹真非成功终态，逐层释放/STOP、无后续哨兵Land；独立恢复任务成功及
新鲜disarm，24正常退出。当前原流程六类各已有至少一轮通过，这不消除其
初始碰撞与电池失效的真实FAIL。尚在完成原三步普通Land正向回归，之后
用新准备协议独立复验六类；不拿旧脚本指纹标记新入口结果。

### 21.9 独立准备后的最终六场景验收（2026-10-07）

按用户确认边界串行执行最终入口，每轮独立PX4 rootfs、DDS配置及输出目录，
ROS domain 215、Gazebo port 11430；沿用完整combined规划/控制链、原CPU感知
及24进程模型。不修改生产C++控制代码、飞控准入、地图、碰撞判断或TTL。
六轮的正式准备任务均SUCCEEDED/true并精确RELEASED；准备后的实际高度
1.49573–1.50400m，速度0.02363–0.06965m/s，连续1s稳定检查通过，随后才提交
独立被测三步任务。准备失败/未稳定绝不提交的纯回归同时通过。

证据根目录仍为 `artifacts/mission-lifecycle-sitl-20261007.YznI0t/`；下表目录
均含原始result.json、states.jsonl、inputs.jsonl、console.log及正式任务文件。
外层枚举4=SUCCEEDED、5=CANCELED、6=ABORTED，成功载荷必须与枚举一致。

| 最终独立目录 | 被测外层真实结果 | 停止传播/覆盖 | 独立恢复到位误差 | 结果 |
|---|---|---|---|---|
| mission-nav-cancel-prepared | 5/false，user_cancel | Nav/Follow均5/false | 0.09070m | PASS |
| mission-nav-timeout-prepared | 6/false，step_timeout | Nav/Follow均5/false | 0.08394m | PASS |
| mission-search-cancel-prepared | 5/false，user_cancel | Search5；前两段真成功，第三Nav/Follow5；保留1.65m² | 0.04720m | PASS |
| mission-search-timeout-prepared | 6/false，step_timeout | Search/Nav/Follow均5/false；面积0m² | 0.08785m | PASS |
| mission-nav-land-prepared | 6/false，external_land_takeover | Nav5、Follow6；等待PX4自行落地 | 不发恢复任务 | PASS |
| mission-search-land-prepared | 6/false，external_land_takeover | Search/Nav5、Follow6；面积0m² | 不发恢复任务 | PASS |

均按精确UUID读取搜索/导航/轨迹真实GetResult，任务/搜索/导航所有权RELEASED，
所有导航会话匹配START及最终STOP。取消ACK不是验收终态；超时保留原生步骤
预算，不用主动取消冒充超时。观察停止后2s（接管3s）无迟到新增子动作、无
被测任务哨兵Land或假完成；只在排空且仍可信OFFBOARD/稳定后执行已声明的
独立恢复任务，其最终真成功、普通Land完成和新鲜disarm全部确认。

AUTO.LAND接管均只发一次外部请求，确认实际armed/模式7；最后UAVCommand
分别早于确认0.00854s/0.03400s，最后raw setpoint分别在确认后0.95034s/
0.95043s（原bridge 1s缓存尾流）。四类下游出口随后静默，直到PX4自己完成
降落无平台回抢OFFBOARD、追加本平台Land/RTL/上锁。搜索接管的Search真
CANCELED与任务真ABORTED是实际取消传播顺序，不强求每层失败枚举相同。

六轮均启动及正常退出24/24，launch returncode=0、transport live=0/pending=0，
无abnormal_lines、强制收尾、排空错误或所属进程残留；退出耗时约0.915–1.567s。
`prepared-evidence-audit.json`再次从真实结果核对终态/载荷、精确释放、会话、
最后1s准备观测、接管静默、恢复误差及当前/proc PID与start_ticks，无复用PID
误报；6/6 PASS。该汇总不替代各轮原始记录。

入口源文件与实际安装入口SHA256均为
`3ddf738ee723637fbf13976e387f5040f7872cdb345d43c12910deac4a13e5a3`，与六轮
result.json一致。最终指纹见 `prepared-runtime-binaries.sha256`，生产规划、
飞控、任务/搜索、Livox及私有Gazebo二进制与旧manifest逐项一致。保留原
`final-runtime-binaries.sha256`为准备修改前证据，不用旧入口指纹冒充新测试。

### 21.10 正向回归、检查与剩余边界（2026-10-07）

原三步普通Land正向回归 `mission-edge-confirm`亦PASS：任务UUID
8081ee47a0ae4fa8b925dc6c6a7638f0真4/true、mission complete，导航到位观测误差
0.09899m，精确任务/导航RELEASED，匹配STOP、新鲜disarm、24正常退出及排空。
自身普通Land没有被误判成外部接管；该轮采用修改准备前入口，独立标记。

| 检查 | 最终结果与证据 |
|---|---|
| launcher CTest | 2/2套件PASS，实际46项纯验收回归＋9项profile回归；launcher-prepared-final-ctest.log及xunit |
| MissionFSM/Search组件 | 6/6套件PASS；mission-component-before-ctest.log，含迟到准入/终态、拒绝取消、递归未决保锁及SDK |
| 本轮两个Python文件 | flake8、pep257、Apache-2.0版权检查PASS；*-prepared-final.log |
| launcher构建元数据 | lint_cmake、xmllint PASS；cmake-prepared-final.log、xml-prepared-final.log |
| 工作树空白检查 | git diff --check PASS；不等于全仓lint已清零 |

本批完成的是已有任务停止/排空契约的有界真实SITL验收及可复用入口完善。
修正测试观测时域（真实轨迹终态与迟到上层反馈分开、预算内已完成段与超时
停止边界分开），并按用户批准隔离准备，不改生产到位半径或成功速度语义。
恢复动作成功不保证稍后上层反馈时仍在半径内，较晚误差单独保存，不能从
任意历史窗口挑最小误差来通过；进一步稳定到位属于独立优化议题。

明确仍未解决/未签收：

1. §21.4原流程真实battery_invalid_timeout及其AUTO.RTL保护触发原因尚未唯一
   归因；后续记录原始battery，不屏蔽无效值、关闭保护或以复跑PASS销账。
2. §21.6初始爬升阶段FIRST_TRAJ_COLLISION仍待专门几何/占据证据排查；独立
   准备只隔离本批注入，不证明其误报，也不与旧运行期碰撞自动合并归因。
3. 未知命令结果、拒绝取消、迟到终态的故障锁有组件mock后端证据，不是实际
   飞行未知结果全矩阵；接管仅此次仿真AUTO.LAND，不覆盖RC/RTL/POSCTL。
4. 复杂静态障碍、任意负载/性能、跟随、UI、实机与已搁置历史崩溃不因本批
   PASS自动完成。保留全部原FAIL；不额外开启这些工作，不自动提交git。

## 22. 电池失效采样链路排查与修复（电池专项完成，退出异常单列）

用户授权优先处理电池失效、持续排查至解决；不启用子agent，不扩展初始碰撞
或搁置的历史退出取证。本批验收要求原因有原始证据、修复可回归且电池无效/
低电量保护继续有效；不延长5s电池新鲜度、5s任务宽限或用有效缓存伪装更新。

### 22.1 原失败飞行日志的新证据

找到§21.4失败当轮私有rootfs中的PX4 ULog：
`mission-search-cancel-verified/px4/build/px4_sitl_default/rootfs/log/2026-10-07/14_54_49.ulg`。
日志起止2.382–26.234s、无dropout；电池共有71条，connected=1、voltage=16.2V、
remaining约0.989–1、warning=0，但最后battery_status在16.674s，之后一直未更新。
同期system_power最后16.674s、cpuload最后16.206s；vehicle_status、baro/mag及
telemetry仍更新至25s以后。PX4在16.666s解锁、21.742s自身报Battery unhealthy，
与ROS任务报告电池失效及25.858s进入RTL相符。不能归因为电量真实耗尽，也不
支持单纯ROS/DDS丢包解释；重点转向PX4内部周期采样/调度停止。

PX4源码显示battery_simulator和system_power_simulator在hp_default周期工作队列，
load_mon在lp_default，均依赖POSIX HRT定时调度。MAVROS 2.14.0在收到id0的
BATTERY_STATUS后停止SYS_STATUS电池fallback；PX4 onboard默认BATTERY_STATUS
0.5Hz。后者是链路背景，尚不能认定提高流频率能修复内部采样停止；禁止把
陈旧SYS_STATUS重复发布当作新电池观测。

新增显式、最多三轮的battery_sitl诊断入口，仅正式takeoff→hover20s→Land，
沿用完整感知与所有安全配置；保存原始battery、独立sys_status、状态及发生
armed电池无效时所属PX4线程/proc只读快照。非预期失败只排空所属任务，不
追加补偿飞行动作；不导航，避免初始规划碰撞干扰电池问题归因。

### 22.2 确定性根因对照与局部修复（2026-10-07–08）

在本机PX4 1.16.2真实POSIX HRT实现中确认并复现并发重排缺陷：回调期间
释放队列锁，另一线程可重新调度同一周期项；原回调返回后再次入队，产生
自环并丢失后续定时项。原生fixture编译实际drv_hrt.cpp、queue及semaphore，
仅外层定时派发与日志出口使用桩；原版10/10队列损坏，补丁版10/10队列完整，
两版同线程回调重入均完成并保留嵌套定时项。最终对照写入兼容构建manifest。

修复采用递归互斥，串行化整个tick、回调和周期重入队；参照上游方法，不
整体升级PX4。原失败日志没有故障时刻队列/线程快照，不能唯一还原当轮
竞争参与者或全部历史电池故障同因；确定修复的是已原生复现的调度缺陷，
真实飞行采样恢复作为独立回归证据。原版三轮电池专项亦PASS，说明问题是
竞争条件，不以原版偶尔PASS否定原始FAIL或声称必现于每次飞行。

自有prepare_px4_hrt工具在新目录复制并补丁化HRT，复用原生产编译/链接
参数及其它对象，仅替换局部libpx4_layer.a中的HRT对象。lockstep、O2/g及
原模块保留，原生fixture的桩不进入生产二进制。工程外PX4源码、库、ELF
不改；原BSD-3-Clause版权头及PX4-LICENSE副本保留，自有工具/测试Apache-2.0。
构建失败的初期布局日志保留，不覆盖或当作飞行结果。

关键SHA256：

| 输入/输出 | SHA256 |
|---|---|
| 原HRT源码 | eb826fde8a1eaae3eef98c8f37c686bc21f62ad061d9cc86c8d2fa2a1ea1ede2 |
| 原PX4 ELF | 9484a69221d73465f621b80662b51d72cd4739b216c9a4526dbaef35ba67c9a4 |
| 项目局部patch | be22a4dfcf1fcb242906d893687052ccb19a0cdd48cf205e2f7e6bfa39bef8ab |
| 补丁后HRT源码 | 2e3a5a6faf2fec42d29cbc4a8be4eb3922ac1140b2ad72d8c5cb4bbb2c74614c |
| artifact兼容ELF | 3a954be562c3192f01eb06c502ee203cbd8a4e3f7a4ac77c893478d0a1a76519 |
| 默认兼容ELF | 5df380603e0c1b8c19e69b36bacc18a68218bb0c216e0c29976d2b6d7931e227 |

两个局部ELF全文件指纹不同（路径/调试信息），.text逐字节相同，其SHA256为
35efbd7d40bd3540e9d421d779e91b455f8197eae0432dad26ff8c2159bd1c30。

### 22.3 用户确认默认兼容版与启动拒绝验收

用户选择“仿真默认使用兼容版”。默认构建位于
`build/easyfly_px4_hrt_compat/px4-input`；基本/完整感知launch、navigation_sitl、
battery_sitl及D5仿真入口统一使用选择器。指定已审查原安装时映射到局部版，
指定兼容输入/私有staging时逐项验证并保留独立rootfs。校验原源码/ELF、
补丁源码、实际兼容ELF、alias脚本/模块别名、来源绑定、manifest及私有wrapper。
缺失或来源/指纹不符直接拒绝，不静默回退原版或其它版本；实机入口不启用。

`startup-refusal-live-launch-audit.json`记录两种launch各执行真实启动请求，
分别覆盖兼容目录缺失与惰性假ELF指纹不匹配，共4/4明确拒绝、returncode=1、
没有启动子进程。另保留show-args拒绝审计。没有修改实际兼容ELF制造故障。
默认飞行记录保存所属实际/proc ELF与SHA，证明不是仅manifest声明使用兼容版。

### 22.4 有界真实SITL结果与采样验收

证据根目录：`artifacts/battery-diagnosis-sitl-20261007.73ebGr/`（沿用开始日期，
跨日至10-08）。保留各轮原始result.json、battery/sys_status/UAVState输入、
ULog、console和真实任务/子动作终态；不是仅检查取消ACK或启动日志。

| 独立目录 | 真终态/验收重点 | 平台整轮结果 |
|---|---|---|
| patched-cycles | 三轮takeoff→hover20s→Land均4/true；2683条armed状态，无电池无效 | PASS，24正常退出 |
| patched-mission-nav-cancel | 任务5/false user_cancel，Nav/Follow5；独立恢复误差0.09091m | PASS，24正常退出 |
| patched-mission-nav-timeout | 任务6/false step_timeout，Nav/Follow5；恢复误差0.07696m | PASS，24正常退出 |
| patched-mission-search-cancel | 任务5/false，Search5，前两段4、第三Nav/Follow5；保留1.65m²，恢复误差0.03356m | PASS，24正常退出 |
| patched-mission-search-timeout | 任务6/false step_timeout，Search/Nav/Follow5；面积0，恢复误差0.04997m | PASS，24正常退出 |
| patched-mission-nav-land | 任务6/false external_land_takeover，Nav5/Follow6；等PX4自行降落，不抢回 | PASS，24正常退出 |
| patched-mission-search-land | 任务6/false external_land_takeover，Search/Nav5、Follow6；面积0，不抢回 | PASS，24正常退出 |
| default-cycles | 三轮任务均4/true、2821条armed状态无电池无效；关闭时semantic_map_node SIGSEGV | **FAIL，23/24正常退出** |
| default-mission | 正式起飞→导航→普通Land，4/true，导航到位观测误差0.08883m、新鲜disarm | PASS，24正常退出 |

六类取消/超时/接管沿用§21用户批准的独立正式准备协议及生产阈值，核实
精确UUID的真实GetResult/载荷、所有权释放、匹配START/STOP、无后续哨兵Land；
外部AUTO.LAND仅一次请求，等待PX4自身落地，不由平台补偿飞行。

`final-battery-evidence-audit.json`逐一审计9轮及各轮全部ULog，结论为电池
专项PASS、平台8PASS/1FAIL。兼容版所有轮次armed电池无效观测为0，电池
connected且remaining有限/合法；全部ULog无dropout，最大记录间隔0.200–0.212s，
末次电池距日志结束≤0.200s，未再出现原9.56s停止更新。记录速率不等于实际
采样频率，审计使用已有5s新鲜度契约，不另造0.21s阈值或改生产保护。

default-cycles三次飞行完成后，在SIGINT退出阶段semantic_map_node-18（当轮
PID51640）退出-11；launch本身returncode=0、transport已排空、无强制收尾/
所属进程残留，不能据此把子进程异常算PASS。原顺序批次遇此FAIL即停止，
原计划的普通任务另开独立目录执行并PASS，不重跑替换该FAIL。新异常没有
与旧Gazebo/EGO历史退出故障合并归因，未开展GDB/崩溃压力专项。

### 22.5 保护、测试与证据完整性

| 检查 | 结果与证据 |
|---|---|
| MissionFSM/Search组件 | 6/6 CTest；executor17项，新增无效电池/低电量两项；mission-protection-final-ctest.log |
| bridge保护/时钟/退出 | 3/3 CTest；bridge-protection-ctest.log |
| launcher入口 | 3/3 CTest，46导航＋9profile＋2电池纯回归；launcher-final-ctest.log |
| PX4构建/选择/旧契约 | 5/5 CTest，新增6构建及11选择测试；px4-launch-final-ctest.log |
| D5配置/隔离rootfs | 2/2 CTest；d5-configuration-ctest.log；不是精准降落全飞行矩阵复验 |
| 本批新增/相关工具lint | 7个Python文件flake8/pep257、8个文件版权、2个CMake及PX4 XML通过；*-final.log |

新增电池保护组件测试运行真实FSM＋SDK、mock飞控服务：位置为已在空中，
电池无效超过测试组件已有宽限或remaining=0.1时，任务真6/false并保留
battery_invalid_timeout/low_battery，恰好一次AUTO.RTL请求，无后续Land。
不冒充实际飞行电池注入；生产5s新鲜度/5s宽限/15%阈值保持不变，未用
陈旧SYS_STATUS、非法帧过滤或假有效标志绕过保护。legacy文件仍有既有格式
债务，本批lint通过不等于全仓lint已清零。

证据校正明确记录：早期battery-sampling-comparison.json只取每目录首个ULog，
保留为初稿；battery-sampling-all-logs.json及最终审计改查全部周期日志。
一次objcopy导出未显式指定输出，重新封装了未运行的artifact兼容ELF，使
SHA变为4efe221d621fd22854e808e5878b5c1fb520f504abe004765d29cfca9c6cf10e。
核实无所属运行实例后，用冻结的补丁archive和原manifest链接参数恢复到
原3a954...指纹，逐字节指纹与各轮preflight一致；默认运行ELF及工程外原版
没有变化。详见artifact-fingerprint-recovery.json。后续导出均显式输出独立
诊断副本，不覆盖输入；不以恢复后的文件伪造或覆盖旧运行结果。

### 22.6 签收边界与后续未完成项

本批验收目标已完成：可复现缺陷有原生反例及修复对照，局部兼容版在真实
起降/原任务停止矩阵保持采样，默认启动映射与拒绝回退已验证，电池保护
继续有效；构建/使用/来源见docs/development/battery-sitl.md及第三方登记。
但不签收整个平台全部场景。仍待用户另行安排：

1. 新记录的semantic_map_node退出SIGSEGV；飞行已经成功，不推测具体根因。
2. 初始爬升FIRST_TRAJ_COLLISION（§21.6）未修复，独立准备不替代其专门验收。
3. 未知命令/其它接管实际飞行矩阵、复杂障碍/负载、UI与实机等旧边界不变。

没有启用子agent、继续G9–G11、恢复搁置历史退出取证或提交git。原FAIL全部
保留；后续若再次电池失效，按新增原始采样及所属线程快照重新归因，不
先验认定为本次HRT缺陷复发。

## 23. 初始爬升第一轨迹失败专项（专项完成，2026-10-09）

用户“开始”授权处理前述第1项；不启用子agent，不处理semantic_map退出崩溃、
旧退出取证、UI或实机，不自动提交git。目标是确认§21.6原失败的真实原因，
针对性修复并完成组件及默认兼容PX4真实SITL回归；不关闭碰撞、不清地图或
放宽速度/新鲜度/飞行边界，也不以独立稳定准备替代原流程验证。

### 23.1 原日志纠正了碰撞归因假设

复查mission-search-timeout-signed原console：十次优化均plan_success=1及
refine_success=1，随后逐次managed trajectory exceeds requested speed;
reject publication，才进入通用FIRST_TRAJ_COLLISION。第一轨迹生成入口对
任何失败使用同一标记，原标记不能证明几何碰撞；此次明确记录的是细化
后的速度约束拒绝。原任务/搜索真失败、24正常退出及原FAIL继续保留。

修复前细化只在初始可行性检查失败时做一次时间重分配/重新优化；细化输出
并未再次做最终动力学检查。发布前严格导数控制点向量范数检查捕获了超速，
十次重复同一输入并不能纠正细化结果。下一步使用真实EGO ROS组件与原附近
起点/速度、合法远处障碍输入建立反例，再验证修复；组件输入不是实际
原始点云回放，不能冒充历史完整重现。

验收标准：反例在旧实现失败、新实现发布合法轨迹，最终完整导数控制点
限速及固定终点成立；真实障碍/无效输入仍拒绝；原起飞→短悬停→搜索流程
在默认兼容PX4中独立验证真实子动作/超时语义，保持原安全配置并保留失败。

### 23.2 反例、失败中间方案与最终实现

新增test_managed_refinement.py使用真实EGO ROS进程及原失败附近UAVState
起点(-0.03239,-0.02705,1.32565)、速度(-0.03314,0.08464,0.07424)，目标
(0.5,-0.55,1.5)、请求0.6m/s；合法障碍点在(5,5,1.5)，不在路径上。
旧实现确定复现十次细化成功→速度拒绝→急停；component-before.log保存
失败。这是同缺陷的组件反例，不是历史完整点云/精确odom帧重放。

第一中间方案仅增加五次细化后检查仍FAIL，component-after.log和
component-diagnostic.log保留：初始速度控制点上界0.649165779m/s，第一次
细化后0.607698765m/s超过请求。继续调用legacy lengthenTime只拉伸中间
少数knot spans，短轨迹实际整体时间增长远小于feasibility比例，五次仍不
满足更保守的原逐轴可行性检查（虽后几次向量范数已经小于请求）。不以
增加无限重试或取消发布防线签收该方案。

最终仅对managed导航使用全时间域重参数化：按原几何的均匀参数采样，
把整个duration按原可行性比例分配至新均匀interval，用原start/end导数
输入重新参数化，不把测得的初始速度直接除比例。固定终点再次锁定，
每轮原优化器做完整轨迹碰撞检查，输出再做动力学检查；最多五次，非有限
比例、无效interval、超出原300s时长界限或仍不可行均拒绝。发布前完整
导数控制点向量范数限速和占据/边界/输入新鲜度防线保留，无阈值放宽。
legacy非managed有效输入保持原单轮/中间knot拉伸策略；无效时不签成功。

同一正向组件反例最终PASS，只需两轮细化，完整导数控制点速度上界
0.4713822188248739m/s≤0.6，精确固定终点误差<1e-9m，时间有效且≤300s。
另外两项真实节点组件回归确认：障碍覆盖起点时真故障，不发布运动轨迹；
起始边界x速度0.8m/s时不通过缩放观测绕过限速，同样拒绝运动轨迹。
允许合法恒定急停曲线，不把它当导航成功。三项均PASS；不是实机速度认证。

FSM的通用FIRST_TRAJ_COLLISION改名FIRST_TRAJ_FAILED，具体动力学/碰撞/
输入拒绝仍另记；真实故障消息、急停动作与上层任务失败语义不变。速度
发布拒绝日志追加控制点编号、速度、请求及起点速度，便于区分原因。

### 23.3 有界真实SITL结果（3/3 PASS）

navigation_sitl新增显式--lifecycle-preparation direct，仅六类任务场景
可用，生成原四步takeoff(1.5m/0.3m/s)→hover2s→navigate/search→Land；
不另发准备任务或等高度稳定。默认isolated协议保持用户原选择，新纯回归
检查direct四步内容/原预算不被改成准备隔离，默认准备失败仍不发被测任务。
证据根目录`artifacts/initial-trajectory-20261009.kFdMbF/`。

direct-search-timeout整轮PASS：原search步12s预算不改，起始实际高度约
1.30884m；首个Nav/Follow真4/true到位，第二段在原预算边界真5/false取消。
外层任务3d38a17787fe4524a1435a4bbe618118真6/false、step_timeout，而非
planner_emergency_stop；Search真5/false、部分几何面积0，所有精确UUID
读取真实GetResult并RELEASED，匹配会话STOP，无后续哨兵Land。排空并确认
可信OFFBOARD/稳定后原独立恢复任务e1011e098a5d467cb840c3aa1835a441真4/true，
到位终态观测误差0.09153m（迟到任务反馈0.09305m另记），最终新鲜disarm。

direct-mission整轮PASS：不加准备悬停的正式三步takeoff→navigate→Land，
任务6054117cbc7844d68b97a8698a45730d真4/true、3步完成，导航到位任务反馈
观测误差0.07069m、任务/导航精确释放、匹配STOP、新鲜disarm。

direct-nav-cancel整轮PASS：原起飞/hover2s后导航实际移动，再精确取消
外层1811bea4634e4331ab35570d3b786ea1，真5/false user_cancel；Nav/Follow
真实非成功终态、精确排空/STOP、无后续哨兵Land。独立恢复任务
796e08169c7645c58bb29524d335acc8真4/true，再确认新鲜disarm；恢复到位
终态观测误差0.07523m，不从历史最小误差挑PASS。

三轮均24/24正常退出、launch=0、transport live/pending=0，无强制/异常/
所属残留。本批未出现semantic_map退出异常，但不销账§22的独立SIGSEGV。
到位观测不是Gazebo ground-truth精度认证。

实际默认兼容PX4 SHA仍5df380603e0c1b8c19e69b36bacc18a68218bb0c216e0c29976d2b6d7931e227；
新入口源/安装SHA同为8248f73c4ef4ce1d8897b3e62ef6690767609da3fe2c117e22327f950007ef7b，
EGO安装ELF为a5d8265f5971c7efa67847a7021b143f7d2086c60fc2d773873e49fc4eec7f08。
旧入口/二进制证据和原FAIL保留，不用新指纹改写旧签收。

### 23.4 测试、证据审计与验收边界

| 检查 | 结果与证据 |
|---|---|
| EGO相关组件 | 8/8选定CTest PASS，含新增真实节点3项正/负回归、会话、失云故障、初始采样、急停/边界/种子；planner-ctest.log及details |
| launcher | 3/3 CTest PASS，实际47导航谓词/准备回归＋9profile＋2电池纯回归；launcher-ctest.log及details |
| 本批3个Python文件 | flake8、pep257、Apache-2.0版权PASS；flake8.log、pep257.log、copyright.log |
| 修改的EGO CMake | 初次lint发现原61行末尾空白，最小删除后PASS；cmake.log保留、cmake-final.log |
| 三轮真实SITL | initial-trajectory-evidence-audit.json从原始结果再次确认3/3，不替代各轮原始日志 |

审计核对实际入口/PX4指纹、真实任务终态与载荷、未完成子动作取消、已
完成第一导航在超时边界之前成功、无哨兵Land、恢复到位误差、会话关闭、
24正常退出及当前/proc PID＋start_ticks。69个所属身份均无残留，不因PID
复用误报；三轮armed电池无效观测均0。runtime-sha256.txt记录最终源/安装
工具、EGO及PX4原/兼容输入。对原PX4源码/ELF无修改，系统库未升级。

本批反例与原明确速度拒绝日志形成闭环，已满足本专项验收；完整历史
点云未录制，不能把组件远处点云冒充原失败帧，也不宣称所有FIRST_TRAJ
或未来运行期碰撞同因。提高或放宽到位、速度、碰撞/地图TTL没有用于签收。
更保守的合法轨迹时间分配可能增加段耗时，任务原期限不变，不能用延长
任务预算来掩盖超时；高速初始状态或不可行路径仍允许真失败。

本次未恢复已搁置旧退出取证，未修复§22独立semantic_map_node退出SIGSEGV，
未重跑D5完整图像降落矩阵，也未开始复杂障碍/负载/实机/UI/G9–G11。
不因三轮正常退出清除旧退出FAIL；下一优先项仍为该独立退出异常。无
子agent或git提交。全仓lint和所有既有工作树变更不被本批局部通过签收。

## 24. semantic_map独立退出崩溃专项（按用户指令暂缓，未定位/未修复，2026-10-09）

用户“开始处理”授权解决§22默认三轮起降后的semantic_map_node SIGSEGV。
只处理该节点及相关退出验证，不恢复搁置的Gazebo/EGO退出专项，不启用
子agent，不改飞行/地面/占据/时间/新鲜度阈值，不自动提交git。

目标：区分节点关闭竞态与运行期内存问题，建立真实节点正/负生命周期
证据，针对确认原因修复并用默认兼容PX4复验原三轮飞行/关闭流程。
验收须先有有效地图/服务再退出，SIGINT/SIGTERM及系统/运行/冻结时钟
正常关闭，真实SITL24/24正常退出且无所属残留；不忽略-11或强制退出。

原记录确认为SIGINT后退出-11，之前仍正常处理点云，不能仅凭时间顺序
推测内存原因。当前源码TF Listener有独立执行线程，但成员声明已保证
Listener先于Buffer析构；直接调换两成员不是有证据的修复。正在使用
合法点云/TF/UAVState及查询流量的有界真实节点夹具，未注入畸形数据。

### 24.1 有界复验结果与不能签收的边界

证据根目录`artifacts/semantic-shutdown-20261009.TG2N4P/`。普通节点6项
系统/运行/冻结时钟×SIGINT/SIGTERM基础退出均PASS（before-python-pytest.log）；
补齐障碍/栅格/非地面/marker全部实际订阅及本项目DDS profile后仍6/6
PASS（before-full-pytest.log）。合法1806点XYZI包含地面和远处立方障碍，
至少3次有效输出和真实GetObstacles非空回复后才发送信号；不是空载发现
节点即退出。新pytest不自动启动飞行，第二次查询仅记录请求/完成状态，
不声称每次信号必定命中服务函数执行中。

original-cycles原普通构建、默认兼容PX4三轮正式起飞/hover20s/Land均
真4/true并新鲜disarm，24正常退出、无强制/异常、transport排空且无所属
残留。这只是一次有界对照，不表示原SIGSEGV已解决，更不判定误操作。

核对TF listener/buffer现有析构顺序已正确；已安装rclcpp16.0.19、tf2_ros
0.25.20及对应官方源码用于核对实现，未找到足以归因原FAIL的反例。原
没有堆栈/core，不宣称成员顺序或某系统库就是根因，不修改系统安装。

### 24.2 独立ASan诊断及ABI校正（非生产修复）

原生产源码与ELF保持不变，在证据目录另外构建asan-build/install及
asan-aligned-build/install。首次六项诊断全部在处理阶段FAIL（-6），
原栈显示system libpcl_filters分配的4000字节缓冲，节点Eigen
handmade_aligned_free读取缓冲前8字节。实际预处理对照：普通编译
EIGEN_MALLOC_ALREADY_ALIGNED=1，ASan默认变为0；是诊断和未插桩PCL的
分配/释放ABI不一致，不能等同原退出阶段-11。初始FAIL与构建完整保留。

新独立诊断构建显式匹配普通ABI值1，未修改生产定义、未抑制非法内存
访问。校正后6/6退出PASS，asan-aligned-pytest.log及各semantic.log无
AddressSanitizer错误。detect_leaks=0明确仅排查非法访问，不签泄漏；
系统ROS/PCL未全量插桩，阴性结果不证明没有并发问题。

asan-cycles在真实完整平台上仅该节点/main替换为独立ASan版，实际
/proc映射保留在asan-cycles-loaded-libraries.txt，确认系统PCL、libasan和
局部模块来源，不以路径声明替代实际加载证据。三轮正式任务均4/true，
24正常退出、无强制/异常/所属残留和ASan报错；不是普通生产签收。

### 24.3 显式、默认关闭的semantic专用取栈

新增semantic_shutdown_capture只启动本次指定的semantic_map_node，不
附加到既有进程或Gazebo/EGO；根据真实exe/PID/start_ticks识别inferior。
SIGINT/SIGTERM正常转发，异常停止后保留线程栈且返回失败；拒绝无gdb
静默回退，不忽略异常/使用快速_exit，不修改系统core_pattern/下载符号。
启动/信号后等待有界，强制清理明确FAIL。

节点launch的capture_shutdown、完整perception launch的
semantic_capture_shutdown，以及navigation_sitl/battery_sitl的
--semantic-capture-shutdown均显式启用、默认关闭；取栈输出单列
diagnostic_only=true，会改变时序，不能混作普通退出签收。

普通/取栈两入口×三种时钟×两种信号共12项真实节点测试PASS；其中
取栈必须观察inferior正常退出和信号转发，不仅wrapper returncode=0。
capture-pytest.log及capture-ctest.log保留。仅该节点取栈的原三轮完整
SITL已完成，对应capture-cycles目录：三轮任务均真4/true，真实inferior
20379有精确身份记录、SIGINT转发及exited normally，24个launch进程正常
退出、无强制/异常/所属残留。取栈增加wrapper/debugger实际所属身份，
不把24个launch退出行理解为只有24个操作系统进程，也不当普通时序签收。

本批未改semantic_map_node.cpp：源码SHA
e35d41319c49a5f4b60a131c28ddebd5a4cf58a2f047293229525652dc991162，普通
节点模块7c1cf7db65a224e8b6086507a35339d8a9be47f4a95e2449f69b2ea5e8cb37da，
main ea7f8b1f4535c390e09ed56420c4249a60ba0da14abacf3def85ef80b506d2e2。
before-sha256.txt与unchanged-semantic-sha256.txt逐项相同，不能把新增诊断
工具描述成已证实的生产根因修复。

### 24.4 最终检查与下一步边界

捕获SITL结束后，将信号转发升级为pidfd：先绑定真实进程，再核对exe及
start_ticks，避免核对后PID复用改变目标；另加2项纯路由拒绝回归（只mock
信号发送，不向其它进程发送信号）。最终12项真实生命周期＋2项纯路由
检查通过。该信号路由加强不是原semantic SIGSEGV修复。capture-cycles
当轮实际旧helper另存capture-cycles-helper.py及SHA；当前helper的pidfd
版本由最终组件测试验证，不用新helper冒充已跑过的SITL入口版本。

| 最终检查 | 结果及证据 |
|---|---|
| semantic相关组件 | 7/7选定CTest PASS，含14项新退出/路由回归及原分类、地面、地图有效性/膨胀、动态跟踪；final-semantic-ctest.log |
| PX4启动/隔离契约 | 5/5 CTest PASS；px4-ctest.log |
| launcher | 3/3 CTest PASS；launcher-ctest.log；诊断选项默认false，不改飞行步骤 |
| 本批5个Python文件 | flake8/pep257/Apache-2.0版权PASS；*-completed.log；初始格式FAIL保留并最小纠正 |
| semantic CMake/XML | PASS；cmake-completed.log、xml-completed.log |
| 默认节点launch | 实际启动/退出PASS，确认无debugger；default-launch-check.log |
| 实际三类完整流程审计 | evidence-audit.json：普通/ASan/取栈各三轮任务完成，71个所属PID身份无残留；原根因未确认、未实施生产修复、原FAIL保留 |

新增文档docs/development/semantic-shutdown.md说明默认关闭的节点/平台/
显式飞行捕获参数及ASan边界。没有修改semantic生产C++、系统库、core_pattern、
感知/飞行准入或安全阈值，没有把“不复现”解释为误操作，也未提交git。
原三次飞行及本批所有普通/诊断结果都保留；全仓lint仍不在局部签收范围。
final-runtime-sha256.txt保存最终源码、普通semantic模块/main、源/安装捕获
与飞行入口、PX4原/兼容输入；检查原节点字节不变及源/安装工具一致。

本批目标尚未达成的部分：原退出-11未复现且缺真实栈，不能给出可验证的
根因或声称修复完成。当前安全下一步是在后续相同仿真回归中显式启用
semantic专用捕获，若出现异常按真实栈定位并做反例/修复对照；不要无限
盲复跑、随意改析构顺序、忽略异常或用成功次数销账。旧Gazebo/EGO退出
专项继续搁置；UI、实机、G9–G11及其它功能不因本批正常退出自动完成。

### 24.5 接续：异常捕获反例、合法动态负载及同机器码符号版（2026-10-09）

用户“继续”后仍仅处理semantic退出。目标为补齐捕获器负向路径、覆盖
动态处理/读者连接变化/时钟重置后的关闭，获得可定位到源码行号的自然
异常证据。原根因确认和生产修复仍未完成，不将下述PASS消除§22的FAIL。
接续证据根目录`artifacts/semantic-shutdown-continue-20261009.SF4Jzh/`。

1. 捕获器清理分支加强：原流程若精确inferior清理抛异常，将跳过后续
   debugger回收；现在用finally保证执行所属group清理和wait，对已退出
   进程的ProcessLookupError作正常竞态处理，其余错误仍报失败。该工具
   默认关闭；不是semantic生产C++的SIGSEGV修复。
2. 独立capture_fixture.cpp不链接生产节点，真实GDB分别验证exit0/7、
   std::terminate产生SIGABRT并保留fixture源码栈，以及忽略信号的fixture
   在20s后清理且必须非零/FAIL；两项mock验证清理异常仍回收debugger。
   共6项，不把fixture异常说成原-11复现。最初残留审计扫到不可读/proc/1
   导致三项测试失败，改为核对GDB明确记录的自有inferior PID；首份日志
   保留。首轮CTest的超时fixture另暴露“固定等0.1s就绪”的夹具竞态，
   在程序尚未安装handler时发SIGINT；改为等待程序明确报告handler就绪，
   保留final-ctest.log及timeout-fixture-readiness-fail.log，不归因生产节点。
3. 八项真实动态负载关闭PASS：合法6686点XYZI以20Hz发送，4s实际处理
   约80帧，必须有动态目标确认；附加DDS reader每0.25s销毁/重建。时钟
   回跳2s的四项实际观察TF/semantic清除日志及随后有效地图恢复。普通/
   捕获×SIGINT/SIGTERM均正常退出；不注入畸形点云，不提高资源预算或
   修改地面/占据/新鲜度阈值。stress-pytest.log及逐节点日志保留。
4. 独立symbols-build/install增加-g而不改变优化/分配定义：模块.text
   与.rodata逐字节等于普通版，main新构建.text不同（不把-g天然等价作为
   前提）。保留新main原件generated-main-with-symbols，在此诊断install
   使用普通main精确副本；生产模块/main及源码SHA仍同24.3。调试模块SHA
   b70ae2d1506008214808860dd0c23f49ce685c0a21dfcfed485423d74ab97e07。
   symbol-line-check.log确认onCloud源码875行可解析，真实节点26743实际
   加载诊断模块的/proc映射和start_ticks已存，不以声明路径代替加载证据。
5. symbols-cycles默认兼容PX4、原三轮takeoff1.5m→hover20s→Land均真
   4/true，新鲜disarm/battery_valid；24/24 launch正常退出、无强制/异常，
   transport排空，25个实际所属PID身份无残留。当轮捕获helper源/两个
   安装一致SHA 6006874ea3d7f4e957f2252bd405725b040948532c7810a0e0864283df56a57c，
   inferior26743收到SIGINT且GDB确认exited normally。diagnostic_only=true，
   不算普通时序修复签收。第一次driver调用因新证据目录尚未创建，在
   启动前拒绝；symbols-cycles-driver.log保留，实际运行另存*-run.log。

最终验收：corrected-final-ctest.log的9/9选定CTest PASS，含原14项退出/
路由、8项新负载、6项捕获工具检查及既有分类/地面/地图/动态跟踪回归；
4个Python文件flake8/pep257、C++ fixture cpplint、5文件Apache-2.0版权、
CMake lint均PASS。ordinary-postbuild-sha256.txt确认普通semantic两个ELF
字节不变，evidence-audit.json独立核对身份残留与机器码/只读数据一致。
未做全仓lint签收、系统库升级、实机/UI/G9–G11或git提交。

收尾pep257发现新docstring首词Always不符合D401，初始日志保留，仅改为
Reap后pep257-corrected.log通过；没有运行逻辑变化。该注释修正后源/普通
安装helper最终SHA bd646635b7c0e255b91a18ce5ba56b7ddaef0a0abe06c5714596be57c6716250，
两个mock清理回归另复跑通过。SITL/九项CTest当轮旧字节helper单独存为
symbols-cycles-helper.py；上述6006874e…是该实际运行版，不把注释修正后
新SHA冒充已跑SITL的版本。捕获负向测试实际日志另存ctest-capture-fixtures/。

结论：本轮解决捕获工具异常清理缺口及夹具就绪竞态，扩大有证据的退出
覆盖并补源码符号；原自然SIGSEGV仍未复现、未获原栈，不能给出唯一根因
或宣布平台崩溃修复。后续在相关仿真回归沿用显式符号取栈；若出现自然
异常，保留完整栈/实际加载指纹后再做生产反例与修复对照，不无限盲复跑。

### 24.6 用户决定暂缓（2026-10-09，当前执行状态）

用户认为可能与特定条件或系统因素有关，指令为无法复现则先不动、做好
记录。现将本专项标记为暂缓，不再主动复跑、开启取栈或修改相关实现；
24.4/24.5所述后续取证计划不再作为当前执行任务。

原§22默认三轮飞行后的SIGINT退出-11及其FAIL、全部后续普通/诊断验证、
源码/ELF指纹和日志均保留。根因未知，特定场景/系统原因只是待验证假设；
不能写成偶然事件、误操作、系统已确认故障或已修复。

现有默认关闭的诊断入口、已验证回归及捕获工具清理修补保留，不回滚、
不删除证据；生产semantic代码及安全阈值不再变更。正常开发/仿真若自然
再次出现同类异常，应记录触发步骤、运行版本、退出码、日志和可用栈，
报告用户后再决定是否恢复专项。暂缓不意味着忽略异常退出或改变既有
故障处理，也不把失败运行判为通过。本次仅更新记录，未运行测试或提交git。

## 25. D5当前版本仿真矩阵（基础场景已覆盖，普通任务时序缺口未收口，2026-10-09）

用户批准下一项为兼容PX4与当前飞控/时序/高度基准下的D5仿真回归。单
agent执行，不恢复semantic/Gazebo/EGO崩溃专项，不启用UI/实机/G9–G11，
不自动提交git。证据根`artifacts/d5-current-matrix-20261009.rQN1mN/`。

目标：验证正常正式任务、短时观测丢失/重获、持续丢失、下降取消、普通
Land收尾取消和外部AUTO.LAND接管的真实飞行终态与控制权。固定下视相机、
静止0.2m ID7标签、三相机30Hz、原显式DDS、.6/.5m下降区间和全部安全
阈值保持；每项使用独立rootfs和新空证据目录，不用自动重试覆盖FAIL。

验收标准：正常/短失标恢复必须真SUCCEEDED、同UUID完整下降/交接和新鲜
disarm；取消必须精确Goal ACK、真CANCELED、父ownership RELEASED，收尾
还须唯一内部Land真CANCELED并恢复可信OFFBOARD；持续失标须停止下降、
保持固定位置命令并真ABORTED/释放；外部接管必须实际模式确认、真ABORTED、
父释放且平台停流（下游允许既有一秒缓存尾流），不能抢回OFFBOARD。
所有场景须launch和子进程正常退出、无强制清理和所属PID/start_ticks残留。
负向动作的真实失败是该场景预期，不写成降落成功；不追加生产自动返航/
降落/上锁。外部接管只覆盖仿真AUTO.LAND，未知命令/RC等不借此签收。

进度：nominal-mission正式任务真4/true、3步complete、精确mission释放、
新鲜disarmed；含align/descend/lost/reacquire/handoff，四组exit0且子失败空。
该轮运行旧成功路径入口，实际源码另存nominal-runtime-simulation.py；
自然失标不代替定时主动失标测试。cancel-descent已真5/false，精确cancel
ACK与同UUID RELEASED、可信OFFBOARD，三组exit0/子失败空/所属残留空。
cancel-handoff进行中，其余待执行；最终结论以后续矩阵结果为准。

新增显式--scenario仅允许--direct-action，与默认启动/正式任务分离。
loss两项用观察者转发真实原始图像到独立测试话题，暂停转发而不伪造
图像/目标/新时间戳；不等同真实遮挡/光照鲁棒性。取消只发精确handle；
接管通过MAVROS服务显式请求测试模式，不作为生产旁路控制。新夹具23项
纯验收反例＋原47项配置回归PASS；首次未安装新模块的17项导入FAIL和
初始两处flake8长行FAIL保留，安装/格式修正后70项与局部flake8通过。
生产precision_controller.cpp及飞控ELF未改，before-sha256.txt留指纹。

### 25.1 接续场景结果及失败边界

cancel-handoff真5/false，取消时已实际AUTO.LAND；唯一内部Land UUID
b3d21be9040b23d844a1973ef9b2af25真5，精降f8b0a66b43b84bcbb45e977c52d4b8a1
精确RELEASED，实际OFFBOARD保持，三组退出/残留正常。loss-recover真4/true，
在真实descend后暂停原图像转发，首次lost_hold后0.6s恢复；实际固定位置
命令、reacquire_hold→align→descend→handoff及新鲜disarm均通过。

原loss-persistent动作正确真6/landing_target_lost且释放，测试仍FAIL：
初版检查窗口延伸到ownership查询之后，把真实failed阶段重新捕获实测
悬停点也算进失标保持。代码precision_controller.cpp明确decision.failed
后enter_hover_at当前位姿；没有证据说明失标过程中锚点变化。新增确定性
夹具反例区分“活动失标保持”与“故障后悬停”，按实际最后lost/reacquire
反馈及failed阶段边界修正验收，不改生产策略、不挑最小漂移窗口。新
loss-persistent-confirm真6/landing_target_lost，37条活动保持位置命令
一致、未启动Land，父释放后新鲜armed/OFFBOARD保持，passed=true，原FAIL保留。
新夹具纯反例现24项，加原47配置共71项PASS。

precision组件首轮18/19 PASS，一项诊断开启的真实转换节点测试在关闭
时JSONDecodeError：长landing_diag JSON中间混入“Failed to publish log
message to rosout: publisher's context is invalid”。原stderr/stdout合流且
管道未持续消费；只修测试采集，将此子进程的RCUTILS日志显式送stdout，
stdout/stderr分别直接保存文件，不跳过坏JSON或屏蔽stderr，不改转换
节点。两信号真实节点复验2/2PASS，context关闭的rosout错误仍独立可见；
完整19/19行为CTest随后PASS约74.39s，飞控9/9行为CTest PASS约70.09s。
这不是生产退出崩溃修复，不恢复已暂停专项；原precision-components.log保留。

external-takeover首轮在接管注入之前因landing_target_reacquisition_timeout
真实ABORTED，scenario.injection=false，仍FAIL。目标检测存在但下游持续
expired/source_invalid_or_replayed，未达到真实descend，不发模式请求，
不能据此签接管成功。该轮与组件回归并行，不能认定负载为唯一根因。
组件结束后独立external-takeover-isolated已PASS：精降bd3992b998f3472791b92b4e7607b3a8
真6/flight evidence/control lost，实际AUTO.LAND确认及mode ACK，父RELEASED，
观察2.5s上下游停流且无OFFBOARD抢回，18个所属身份无残留。
原输入时序失败单列，后续成功不销账；不认证任意并发/算法负载。

早期四项负向运行使用lifecycle-runtime-simulation.py/scenarios.py归档版；
接续增加结果内入口/助手/飞控/PX4指纹、实际保持命令/下游流采样和精降
释放查询，current-runtime-*另存，后续运行记录actual runtime hash。
当前在用最终安装入口独立复验正常正式任务，补齐其所属进程身份和精降
精确释放证据；最终结论与矩阵表待该轮完成后写入。

### 25.2 当前普通任务时序失败（仍在排查，不能整体签收）

nominal-current-entry最终独立正式任务真6/step_failed:landing_target_lost，
未进入descend/handoff；四组进程exit0、子失败空、无所属残留，但passed=false。
该轮不与组件测试并行，说明前一失败不能简单归因并发组件负载。原正常
nominal-mission的PASS保留，不覆盖本FAIL；当前矩阵整体暂不能签收。

按精降动作窗口统计observer收到的源年龄（ROS clock减原header source）：
camera及tag各50条，tag中位0s/最大.048s；landing_target35条中24valid，
源年龄中位.36s/最大.628s；guidance73条中10valid，源年龄中位.36s/最大
.628s。说明此轮可观测滞后已在tag→landing_target环节出现，而非已证实
相机没有检测标签或只发生于飞控。observer收到年龄不是该节点native
take时间，不能据此唯一判定订阅队列、发布阻塞或系统调度。

启动新的nominal-timing-diagnostic，沿用原.2m/三相机30Hz/高度区间/DDS，
仅显式开启既有transform/flight只读诊断。observer native RMW采样新增
camera/CameraInfo/tag话题，与原landing/guidance/state配对；原消息不换
时间、不重复take，不改QoS或任何控制/新鲜度门槛。目标是区分tag输出、
landing_target发布/接收及下游配对的耗时；若无可信native字段，阶段保持
未知。没有恢复任何已暂停的退出崩溃专项，也不以诊断运行通过追认正常
任务时序问题已解决。

上述nominal-timing-diagnostic已真4/true、3步完整、精确任务及精降释放、
新鲜disarm、四组exit0/所属残留空；仍只是诊断运行PASS。其动作窗口内
camera/tag/landing/guidance源年龄最大.052s（camera最负-.056s）；625组
有效匹配tag→landing_target native发布差中位.127857ms、最大.309926ms，
无法解释先前默认入口的.36/.628s滞后。没有据此宣称来源已修复。

新增默认关闭--observer-rmw-diagnostics，将observer native采样与生产
transform/flight诊断解耦；仅改观察者数据采集，不启用生产日志、第二个
reader、换QoS/时间戳或改飞行控制。nominal-observer-only正在记录生产
诊断关闭路径，补充实际source pub/received/take阶段证据；仍按原门槛。

### 25.3 本轮交付与尚未解决的问题

| 场景 | 有界实际证据 | 当前结论 |
|---|---|---|
| 正常正式任务 | nominal-mission真4/true/3步完成；nominal-current-entry真6/landing_target_lost | 有成功证据，但普通复验失败，不能整体签收 |
| 短失标恢复 | loss-recover真4/true；固定命令保持、重获/重新对准/下降/交接、新鲜disarm | 此指定断流场景PASS |
| 持续失标 | loss-persistent-confirm真6/landing_target_lost；37条保持命令、无Land、精确释放/可信悬停 | 此指定场景PASS，旧验收窗口FAIL保留 |
| 下降中取消 | cancel-descent精确ACK＋真5/false＋同UUID RELEASED | 此指定场景PASS |
| Land收尾取消 | cancel-handoff父及唯一子Land真5、父释放、实际OFFBOARD | 此指定场景PASS |
| 外部AUTO.LAND接管 | external-takeover-isolated真6、实际模式/ACK、父释放、上下游停流 | 此指定接管PASS，首轮注入前时序FAIL保留 |

nominal-observer-only正式任务在准入即REJECTED，未起飞；退出/残留正常，
整轮FAIL。该次MissionFSM没有记录具体拒绝条件，不能从observer就绪
推断SDK也已就绪，不能认定是输入时序同一原因，不自动重发Goal。
另以direct-observer-only绕过任务层隔离检查实际精降：Takeoff4/true、
PrecisionLand dc0727b0f77c4aef9a2023975dae2a3a真4/true、新鲜disarm、同UUID
精确释放、三组exit0/无残留；生产transform/flight诊断保持关闭，仅observer
保留native字段，故仍是诊断证据，不能销掉普通任务失败或准入拒绝。

25.2源年龄表是所有正时间戳消息（含invalid）的observer统计。只看valid：
landing_target24条中位.312s/最大.412s，guidance10条中位.266s/最大.348s。
valid表示发布时校验结果，observer收到时的年龄不等同生产入口/发布时
年龄；不据此指控某节点绕过TTL。证据仅支持需继续追查tag→landing_target
及后续传输/配对时序，尚无失败轮native栈/时延足以给出唯一根因。
tag新鲜是数组header口径，并非每帧所选标签位姿可信的完整证明；默认
诊断关闭的失败轮缺同帧候选几何/native阶段数据，几何与时间的耦合仍待核实。

最终检查：飞控9/9行为CTest PASS；precision修正日志采集后19/19行为
CTest PASS，随后新observer开关的CLI/验收反例＋配置共72项PASS、最新
入口2/2CTest PASS。四个本批Python文件flake8/pep257/Apache-2.0版权、
CMake及官方缓存schema XML校验PASS；最初错误xmllint --xsd调用保留，
改用既有XML_CATALOG_FILES成功，未跳过schema或更改系统配置。

matrix-audit.json逐项保留全部运行（含失败）、actual runtime指纹及
已记录的PID/start_ticks独立残留核对，整体matrix_acceptance_complete=false。
旧nominal-mission入口没有所属身份记录，标为未知而不补造；新增入口
及两个诊断运行的身份核对均无残留。before/final-sha256确认生产精降
控制源码4f8b935a…、飞控ELF cf0eff4e…及兼容PX4 ELF5df38060…逐字节不变。
本次修的是测试/记录与默认关闭观察者入口，未修生产时序原因、未放宽
安全阈值，未做全仓lint/性能/实机/UI/G9–G11验收，未提交git。

后续优先项：捕获普通失败轮的tag与landing_target原生阶段时间，区分
订阅处理、发布/传输和下游队列；同时补任务准入拒绝的真实guard理由，
不把固定等一秒当SDK状态已可信的证明。取得确定原因/反例后再修生产
实现并重跑原普通任务；当前不能宣称D5当前版本完整回归或间歇失标问题
已经完成。semantic及旧退出崩溃专项仍按用户决定暂缓。

## 26. D5 输入时序与任务准入取证接续（进行中，2026-10-11）

目标：继续第25节尚未关闭的普通任务失标和一次任务准入拒绝，取得失败
现场而非仅增加成功次数。第25节所有FAIL保留；UI、实机、退出崩溃专项
仍暂停，单主agent执行，不提交git，不放宽TTL/状态配对/几何/失标门槛。

新增默认关闭的 landing_detection timing_trace_path。由原订阅的
rclcpp::MessageInfo记录同一次take的writer/receive wall时间、callback
entry wall/ROS时间及原publish调用前后时间；输入和watchdog分别标记。
仅8192条环形内存，独占创建证据文件，正常析构时写TSV，记录total/
retained/dropped。不添加reader、线程、话题或回调内磁盘/rosout输出；
强杀/崩溃时没有完整落盘不能算有效时序证据。wall与ROS时间不混减，
RMW字段缺失/系统wall回退不得视为真实正常延迟。

MissionFSM拒绝时记录真实guard类别；状态拒绝的日志使用该次决策的
同一个SDK StateSnapshot，不重新采样。原准入条件、文件校验、独占锁
和拒绝结果不变；不自动重发Goal。仿真入口新增独立显式开关
--ingress-timing-diagnostics，默认不启用、不授权飞行，也不启用
transform/flight诊断；运行证据新增landing/mission ELF指纹。

证据根：artifacts/d5-timing-followup-20261011.RDokX8/。
三个相关包构建成功。landing四项CTest（含真实ROS消息、安全失效、
独占文件/环形容量/退出落盘）通过；任务执行和入口回归仍在执行。

验收标准：明确捕获失败轮原生时序/真实拒绝理由，确定原因后只修对应
实现并验证反例；原三相机30Hz/.2m标签/.6m收尾/.5m下降下限和独立
高度基准不变，最终普通正式任务须真实三步成功、同UUID释放、新鲜
disarmed及所有所属进程正常退出。诊断PASS不覆盖默认入口FAIL；若
无法重现，应明确保留未知，不宣称修复。

### 26.1 真实输入延迟已捕获，队列候选未晋级

mission-ingress-1正式任务真6/step_failed:landing_target_lost，未下降/未
Land收尾，整轮FAIL保留。450条原生事件无截断；277条原生输入均匹配
observer所见同writer_wall与同header的tag发布，header错配0。
tag writer→LandingNode native receive中位290.237ms、最大365.222ms；
native receive→callback中位.047ms，但p95 383.925ms、最大396.942ms。
callback到publish中位.003ms，publish中位.018ms/最大.052ms；447个
同stamp且writer时间严格落在publish边界内的输出配对，其到observer
native receive中位.020ms、最大.801ms。该轮源ROS入口年龄中位.344s，
大于后续动作链.3s预算；guidance真实理由为过期/源无效，没有平面几何
拒绝。证据定位到tag→LandingNode接收/可读调度这段，不能反推是其
计算、下游传输或控制准入绕过TTL，仍未确认具体DDS/调度触发机制。

独立构建仅把tag可靠reader深度1改10，候选安装只通过本轮命令的
AMENT_PREFIX_PATH接入，正式安装/源码不改QoS。mission-depth10-candidate
真4/true、完整3步、精确任务/精降释放、新鲜disarm、四组exit0、子失败
空、leftovers空；native入口源龄最大.048s、receive→callback最大.172ms。
但回到正式depth1的mission-ingress-2也真4/true/完整链/正常退出，源龄
最大.060s、receive→callback最大.182ms。因此候选PASS不是队列根因
证明，也不晋级为生产修复。两轮均是producer/observer诊断运行。

无飞行真实LandingNode受控30Hz输入：正常depth1全450条及时take；
三次120ms自有进程暂停/恢复对照depth1 take441/450、depth10 450/450，
没有持续>200ms输入延迟。活动发布中加入空/单tag变长载荷的对照亦未
复现原大延迟。最初probe使用Humble不支持的两参数callback导致
TypeError，已保留失败；修正为既有DiagnosticExecutor同一次take记录
后再试，不改变QoS或伪造消息。上述暂停仅无飞行自有进程，不是SITL
负向飞控注入。旧Gazebo/semantic专项未恢复。

### 26.2 普通入口新增退出失败与精确清理顺序修复

mission-default-final未启用任何三种诊断，正式任务UUID
e51c8ea52b414027b5667af80ffdd388真4/true、3步、新鲜disarm及同UUID释放；
但landing_transform在SIGINT退出时，栈落于Humble executor的
sub.handle.take_message，报RuntimeError: Unable to convert call argument
to Python object，子进程exit1，所以整轮passed=false；不是旧Gazebo/
semantic崩溃，不因为飞行成功将整轮签收。

观察节点main改为显式不启用rclpy默认自动关闭context的信号处理，
SIGINT/SIGTERM仅设停机请求；当前单线程executor回调返回后退出循环，
然后executor shutdown、节点销毁、context shutdown，最后恢复信号
handler。默认/诊断保持相同处理顺序，业务校验与QoS不改；不新增
RuntimeError捕获，不忽略正常运行异常。四项信号期间context存活/
清理顺序/同期间RuntimeError仍抛出的反例通过；真实typed take紧邻
两种信号和两种executor的补充测试及改后普通SITL仍待验收。

任务准入日志追加同Goal UUID，并用原实际SDK快照。17项任务回归曾
因编辑期间已加载旧fixture的handle NameError失败，修正当前fixture
后完整17项通过；保留原失败日志。这是本批测试修改问题，不是生产
任务故障。状态旧源/新receipt拒绝日志验证fresh=0、receipt_fresh=1、
source_time_valid=1及精确被拒Goal UUID。当前真实SITL四轮均已准入，
第25节那次REJECTED仍缺当时snapshot，未认定或修复其唯一原因。

### 26.3 本轮收尾：退出顺序签收，间歇时序仍开放

改后mission-default-signal-fix所有诊断关闭、正式QoS深度1、原配置/
三相机负载不变：任务4b508f137d2b4b8cba8f37300ed56746真4/true，
完整三步及align→descend→land_handoff；新鲜disarmed，任务及精降
精确UUID释放，四组exit0、child_exit_failures全空、leftovers空，
整轮passed=true。当前transform Python SHA aec42696…（完整值见
result.json），新增runtime指纹记录该实现；飞控控制源码4f8b935a…、
ELF cf0eff4e…和兼容PX4 ELF5df38060…仍不变。新增退出顺序路径已
验证；不将此PASS覆盖输入延迟FAIL或追认历史所有RuntimeError唯一原因。

相关组件：landing 4/4CTest通过；mission executor 17/17用例通过
（含拒绝日志精确UUID/同SDK快照）；precision 20/20行为CTest通过。
随后补真实native take边界：SIGINT/SIGTERM×普通/诊断executor
四项均真正take并完成typed转换，期间context仍有效，进程exit0，
不是catch后假造成功；清理顺序/异常仍传播反例另四项通过。
最新CLI26/26通过。六个本批Python文件flake8、信号相关pep257、
新增文件Apache-2.0检查、三个landing C++文件uncrustify、package XML
schema通过；cppcheck最初按2.7工具规则skip，随后仅对这三个小文件
显式进程局部允许该版本检查，通过。最初错误--check命令/样式FAIL
和测试fixture的NameError日志保留，不宣称全仓lint或全负载长期验收。

final-audit.json包含本轮五次正式任务全部实际结果/ELF指纹与PID/
start_ticks核对（均无残留）。原输入FAIL与普通退出FAIL保留；
overall_current_d5_regression_closed=false。测试与仿真已全部结束；
生产tag订阅仍是可靠depth1，未晋级候选depth10、未扩大任何安全门槛，
未提交git、未改系统库/配置，也未重开旧Gazebo/semantic专项。

剩余工作：针对已捕获tag→LandingNode native接收/可读调度异常，继续
建立真实负载与接收顺序的确定性反例，区分DDS传输/历史可读性/
执行器唤醒，而非重复成功飞行或直接套用depth10。历史任务准入拒绝
保持原因未知；新增日志用于下次实际拒绝，不通过固定等待或自动
重发绕过准入。此前已通过的负向飞控场景仍保留原证据，本批没有
将新增观察节点退出改动追认成全部D5矩阵再次验收。
