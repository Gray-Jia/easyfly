# EasyFly 开发执行记录（schedule-v4）

> 开始时间：2026-10-04 07:33（Asia/Shanghai）
> 完成时间：2026-10-04 07:51（Asia/Shanghai）
> 计划依据：`plan-v3.md` D0；起点 HEAD：`1860690`。
> 状态：D0 已完成并通过最终只读评审；G9-G11 复验继续暂停。
> 分工：主 agent 负责范围、配置、契约、集成检查与记录；easyfly_coder 负责构建脚本和 EGO 限定修复；easyfly_reviewer 负责最终只读评审。

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

- D1统一导航、D2完整SDK/参数写入、D3正式任务引擎均尚未实施。
- 标签/精准降落功能仍未实现，landing_dev只是现有传感器链开发入口。
- 第三方来源缺口、EGO部分TODO许可证和平台/包许可元数据差异只做了事实登记，没有伪造来源或擅改许可。
- 配置核对覆盖源默认值和受管入口；任意自定义launch/运行时覆盖不在保证范围内。
- 本轮不做全量lint清零、长期资源/重启测试、实际传感器联调或动态飞行；历史G8状态保留，G9-G11继续暂停。
