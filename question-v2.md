# EasyFly 复验期问题登记簿（question-v2.md）

> 创建时间：2026-09-15
> 基线：master / 04d99d4（G0 已冻结，PX4 已对齐 v1.16.2）
> 性质：配合 schedule-v2.md / test-v2.md 的暂停期复验问题记录。**只记录、不在验收中途修改**；仅当问题阻塞验收时才允许修复（修复 = 新基线编号 + 从受影响最低门禁重跑，见 test-v2 §7、§18）。
> 每条记录须绑定：发现门禁、test-v2 §18 分类、证据、风险结论、处置决定。

## 记录索引

| 编号 | 发现门禁 | 分类 | 概要 | 状态 |
|---|---|---|---|---|
| V2-01 | G1 第 2 组构建 | TEST-adj / lint 债务（非阻塞） | semantic_map 符号比较警告 | 已记录，待批量修复 |
| V2-02 | G1 第 3 组构建 | lint 债务 + 构建系统兼容性债务（非阻塞，third_party） | EGO 第三方栈 6 包警告簇 | 已记录，修复前需先补 UPSTREAM.md |
| V2-03 | G1 第 4 批驱动构建 | lint 债务 + 构建工具行为说明（非阻塞） | fast_lio 警告 + colcon override 提示 + $ART 未设置过程事件 | 已记录，已补救归档 |
| V2-04 | G2 单元测试 | **TEST（测试架子缺陷，已解决）** | test_sort 已改为原生 gtest，结果文件正常生成，6/6 通过 | 已解决（2026-09-15） |
| V2-05 | G2 单元测试 | lint 债务（非阻塞） | 四包 lint 失败 79 项；V2-04 修复后降为 75 项 | 已记录，列入债务清单 |
| V2-06 | G3 组件测试 | 测试范围缺口（非阻塞，待补） | §10.2 五组故障注入测试尚未编写，G3 现有范围仅 mock 14/14 | 已记录，G4 前或期间补齐 |

---

## V2-01 semantic_map 符号比较警告（-Wsign-compare）

- **发现时间**：2026-09-15，G1 第 2 组（感知基础）隔离构建
- **构建结果**：通过。`Summary: 9 packages finished [19.3s]`，0 failed；`1 package had stderr output: easyfly_semantic_map`（stderr 内容为下述警告，非 error）
- **test-v2 §18 分类**：非失败项。归入 **lint/warning 债务**（对应 schedule-v2 §8 里程碑 3 的 lint 债务清单），不按 CODE/CONTRACT 处理

### 现象

~~~text
semantic_map_node.cpp:403:37: warning: comparison of integer expressions of different
signedness: 'unsigned int' and 'int' [-Wsign-compare]
  403 |   if (++grid_miss_[i] > params_.grid_persist_frames) {
~~~

### 位置与根因

| 位置 | 内容 |
|---|---|
| `src/perception/p4_fusion/easyfly_semantic_map/src/semantic_map_node.cpp:488` | `std::vector<uint32_t> grid_miss_;`（无符号） |
| `src/perception/p4_fusion/easyfly_semantic_map/src/semantic_map_node.cpp:121` | `int grid_persist_frames{20};`（有符号） |
| `src/perception/p4_fusion/easyfly_semantic_map/src/semantic_map_node.cpp:153` | 从 YAML 以 `as<int>` 加载 |
| `src/perception/p4_fusion/easyfly_semantic_map/config/semantic_map.yaml:28` | 当前值 `grid_persist_frames: 20` |
| `src/perception/p4_fusion/easyfly_semantic_map/src/semantic_map_node.cpp:403` | 触发点：`++grid_miss_[i] > params_.grid_persist_frames` |

根因：`uint32_t` 与 `int` 直接比较，GCC `-Wsign-compare` 例行提示。

### 风险结论

- **当前配置（20，正数）下无害**，占据格保持/释放行为正确。
- **理论边角**：若 YAML 将 `grid_persist_frames` 配为负数，比较时负 int 转为巨大无符号数，条件永远为假 → 占据格子**永远不会被释放**，栅格地图只增不减。属于配置鲁棒性瑕疵，不是当前功能 bug；语义上该参数不应为负，但加载路径未做下界校验。

### 处置

- **本轮处置：只记录，不修复。** 该警告不阻塞 G1 及任何下游门禁；按 G0 规则，验收中途改代码会产生新基线编号并重跑受影响门禁，为化妆品级警告不值得。
- **修复建议（供将来批量修复）**：
  1. `grid_persist_frames` 声明与 YAML 加载改为 `uint32_t`（连带第 121/153 行），或比较处显式 `static_cast<uint32_t>`；
  2. 顺手在加载处加下界校验（`< 1` 时回退默认值），一并消除负配置边角。
- **修复时机与后果**：攒入暂停期允许的"补测试/提升可复现性"批次或恢复开发后的首个代码批次一起提交；提交后按 test-v2 §7 产生新基线编号，从 G1 重跑受影响包即可（纯编译层改动，不触及 T/F/N/E 套件）。
- **证据留存**：`log-v2/latest_build/easyfly_semantic_map/`（本轮构建日志）；已按 G1 要求归档至当轮 `artifacts/acceptance-*/warnings.txt`。

---

## V2-02 EGO 第三方栈构建警告簇（6 包）

- **发现时间**：2026-09-15，G1 第 3 组（规划）隔离构建
- **构建结果**：通过。`Summary: 16 packages finished [8min 4s]`，0 failed
- **test-v2 §18 分类**：非失败项。归入 **lint 债务 + 构建系统兼容性债务**；涉及包全部位于 `src/third_party/planners/ego_planner/`（上游代码），自研的 easyfly_global_planner、easyfly_local_planner 无警告

### 警告分类明细

| # | 类别 | 数量 | 位置 | 判定 |
|---|---|---|---|---|
| 1 | `-Wsign-compare` | 8 | `traj_utils_so/include/traj_utils/polynomial_traj.h:47/186/206/221/254/293`、`traj_utils_so/src/planning_visualization.cpp:195`、`plan_env/src/obj_predictor.cpp:54` | `int` 循环变量 vs `size_type`，上游代码风格，无功能风险 |
| 2 | `-Wunused-parameter` | 10 | `bspline_opt/include/bspline_opt/lbfgs.hpp:723`（gp）、`bspline_opt/src/bspline_optimizer.cpp:779`（earlyExit 回调 x/g/fx/xnorm/gnorm/step/n/k/ls） | L-BFGS 回调签名强制要求全部参数，无功能风险 |
| 3 | `-Wpedantic` 多余分号 | 1 | `bspline_opt/include/bspline_opt/gradient_descent_optimizer.h:14`（`EIGEN_MAKE_ALIGNED_OPERATOR_NEW;`） | 无功能风险 |
| 4 | CMake 弃用警告 | 1 | `traj_utils_so/CMakeLists.txt:76`：`rosidl_target_interfaces()` 已弃用，应改用 `rosidl_get_typesupport_target()` + `target_link_libraries()` | Humble 上可正常工作；未来 ROS 发行版升级时的兼容性债务 |
| 5 | CMake CMP0074 未设置 | 2 | `plan_env/CMakeLists.txt:22`、`path_searching/CMakeLists.txt:19` 的 `find_package(PCL)`：`PCL_ROOT=/usr` 被忽略 | PCL 经默认路径正常找到，构建通过；仅 dev 警告 |
| 6 | PCL pcap 功能禁用提示 | 1 | `ego_planner` 包：`io features related to pcap will be disabled` | 系统未装 libpcap，仅影响"回放 pcap 抓包文件"功能，本项目不用，运行时无影响 |

### 附带正面证据（供 G1 验收检查取用）

`bspline_opt` 编译时的头文件搜索路径为 `install-v2/traj_utils_so/include/...`——直接证明 v2 构建链引用的是 install-v2 产物而非旧 `install/`，可作为 G1"无旧工作区产物污染"检查项的证据（见 `log-v2/latest_build/bspline_opt/stdout.log`）。

另：`ego_planner` 单包编译 7min24s 属 PCL/Eigen 重模板编译的正常耗时，非异常。

### 处置

- **本轮处置：只记录，不修复。** 全部为警告，不阻塞 G1 及任何下游门禁。
- **与 V2-01 的关键区别**：本簇位于 third_party 上游代码。修改会产生本地 patch，加重 test-v2 §4.9 / schedule-v2 §6.3 已指出的"上游版本不可追溯"问题。因此：
  1. 修复优先级低于自研代码（V2-01）；
  2. 任何修复前必须先为 `third_party/planners/ego_planner` 建立 UPSTREAM.md（记录仓库 URL、branch、commit、导入日期和已有本地 patch），否则 patch 无从追溯；
  3. 类别 4（rosidl_target_interfaces 弃用）建议仅在计划升级 ROS 发行版时一并处理。
- **证据留存**：`log-v2/latest_build/{traj_utils_so,plan_env,path_searching,bspline_opt,ego_planner,traj_utils}/`；已按 G1 要求归档至当轮 `artifacts/acceptance-*/warnings.txt`。

---

## V2-03 驱动批构建警告与过程事件

- **发现时间**：2026-09-15，G1 第 4 批（驱动：realsense2_camera、livox_ros_driver2、fast_lio 逐包构建）
- **构建结果**：通过。三个包各 `N packages finished [0 failed]`，退出码均 0
- **test-v2 §18 分类**：非失败项。类别 1-2 归入 lint 债务；类别 3-4 为构建工具行为说明；另记录一次 TEST 类过程事件（证据留存失误，已补救）

### 警告/提示分类明细

| # | 内容 | 位置 | 判定 |
|---|---|---|---|
| 1 | CMake CMP0074 未设置（PCL_ROOT 被忽略） | `fast_lio/CMakeLists.txt:81` | 与 V2-02 #5 同类；PCL 经默认路径正常找到，无风险 |
| 2 | Boost bind placeholder 弃用 pragma message | 系统头文件链 `/usr/include/pcl-1.12/...` → `/usr/include/boost/bind.hpp:36` | Ubuntu 22.04（boost 1.74）+ PCL 1.12 的已知系统级噪音，**非 EasyFly/fast_lio 代码产生，本项目无法修复**，无功能风险 |
| 3 | `Current CPU archtecture: x86_64 / Processer number: 20 / core for MP: 3` | fast_lio CMakeLists 信息打印 | 上游构建信息输出（OpenMP 配置），非警告 |
| 4 | colcon override-check WARNING：`livox_ros_driver2 is in: .../install-v2/livox_ros_driver2` | 构建驱动批时 | 见下方说明 |

### 类别 4 说明（colcon override 警告）

- **原因**：`livox_ros_driver2` 已在前序组作为依赖闭包被构建安装（install-v2 中已存在）；驱动批 source 了 `install-v2/setup.bash` 后又选择同一包构建——colcon 把"向已 source 的 underlay 中同名包再次构建"视为潜在 override 并告警。
- **风险结论**：无实际风险。同源、同 build-v2 目录、同 install base 的"自 overlay"，不存在版本错配或 ABI 不一致；`Finished [0.25s]` 即无变更的空构建。
- **前瞻**：colcon-override-check 提示"未来版本可能升级为 error"。届时两种处理：构建命令前不 source 本工作区 `install-v2`（colcon 构建本身不需要 source 本工作区），或按提示加 `--allow-overriding`。

### 过程事件（TEST 类）：$ART 未设置导致 tee 存档失败

- **现象**：执行驱动批时 `$ART` 环境变量未设置（新终端未重新 export），`tee "$ART/build-driver-*.log"` 展开为 `/build-driver-*.log`，写根目录被拒（权限不够），三份构建日志未当场存档。
- **影响**：不影响构建结果；colcon 自身日志完整保存在 `log-v2/build_2026-09-15_17-57-*/`。
- **补救**：已重建证据目录 `artifacts/acceptance-20260915-1759/`，从 log-v2 回收归档全部 G1 证据（git 基线、warnings.txt 共 156 条、五项验收检查输出、依赖图 67 包、驱动 SDK 预检、驱动链接验证）。
- **教训（写入执行守则）**：每轮验收开新终端后，第一步 `export ART=artifacts/acceptance-$(date +%Y%m%d-%H%M) && mkdir -p "$ART"`。

### 处置

- **本轮处置：只记录，不修复。** 全部无功能风险。
- 类别 2（boost placeholder）为系统噪音，永久豁免；类别 1 与 V2-02 #5 同批处理；类别 4 观察 colcon 版本演进，暂不动。
- **证据留存**：`artifacts/acceptance-20260915-1759/`（driver-sdk-precheck.txt、driver-verification.txt、warnings.txt 等）。

---

## V2-04 test_sort 测试架子缺陷：注册为 gtest 但不生成结果文件

- **发现时间**：2026-09-15，G2（colcon test，easyfly_multi_object_tracking）
- **test-v2 §18 分类**：**TEST（测试自身缺陷）**。阻塞 G2 的"colcon 全绿"结论，但不构成功能失败
- **现象**：`colcon test-result` 报 `test_sort.gtest.xml: 1 test, 1 error`，错误消息为 `The test did not generate a result file`；错误内容中嵌入的 stdout 显示 6 项断言**全部实际通过**（PASS 1: ID 不同 / PASS 2: 交叉期 2 稳定 track / PASS 3: 遮挡 10 帧后 ID 保持 / PASS 4: 干扰目标独立 ID / PASS 5: 类别隔离 / PASS 6: 速度估计合理）

### 根因

| 位置 | 内容 |
|---|---|
| `src/perception/p3_tracking/easyfly_multi_object_tracking/CMakeLists.txt:44` | `ament_add_gtest(test_sort test/test_sort.cpp)` —— 按 gtest 二进制注册，ament 包装器运行后期望 gtest 结果文件 |
| `src/perception/p3_tracking/easyfly_multi_object_tracking/test/test_sort.cpp` | 手写 main() + `<cassert>`/`<cstdio>`，自打印 PASS 文本；文件头注释写明"编译: g++ test_sort.cpp && ./a.out"。不是 gtest 二进制，不产生 xml |
| 对照组 | 同包 `test_id_consolidator.cpp` 正确使用 `<gtest/gtest.h>`，10/10 带结果文件通过 |

即：**不是假阳性，是"假阴性"式架子缺陷**——功能通过但无法被结果系统采信。ctest 层面因退出码为 0 判 PASS，xunit 层面因无结果文件记 error。

### 处置

- **已采用方案 A**：将 `test_sort.cpp` 的手写 `main()`、`assert` 和自打印 PASS 文本改写为 6 个原生 gtest 用例，CMake 注册方式保持不变。
- **同时消除测试假通过路径**：类别隔离现在具有明确断言；速度测试在找不到已确认目标时会由 `ASSERT_TRUE` 失败；测试不再受 Release 模式下 `NDEBUG` 禁用 `assert` 的影响。
- **验证结果（2026-09-15）**：
  - `cmake --build build-v2/easyfly_multi_object_tracking --target test_sort -j2`：通过；
  - `ctest --test-dir build-v2/easyfly_multi_object_tracking -R '^test_sort$' --output-on-failure`：1/1 通过；
  - `colcon test --build-base build-v2 --install-base install-v2 --packages-select easyfly_multi_object_tracking --event-handlers console_direct+`：`test_sort` 6/6、`test_id_consolidator` 10/10 功能测试通过；
  - `test_sort.gtest.xml`：6 tests、0 errors、0 failures，结果文件缺失错误已消失。
- **结论**：V2-04 已解决，不再阻塞 G2 功能验收。整包测试中仍报告的失败来自 V2-05 lint 债务，应继续与功能测试分开统计。
- **基线影响（G0 规则）**：这是测试文件变更，已随 2026-09-15 提交，该提交即 G2 复验基线（新基线编号以 `git log` 为准）。
- **证据留存**：`build-v2/easyfly_multi_object_tracking/test_results/easyfly_multi_object_tracking/test_sort.gtest.xml`；`artifacts/acceptance-20260915-1759/v2-04-resolution.md`。

---

## V2-05 G2 lint 债务清单（初测 79 项，V2-04 修复后 75 项）

- **发现时间**：2026-09-15，G2
- **test-v2 §18 分类**：lint 债务，非阻塞（test-v2 §9 明确"功能 gtest 与 lint 分开统计"，lint 失败不影响 G2 功能结论）
- **明细**：

| 类型 | 失败/总数 | 涉及包 |
|---|---|---|
| cpplint | 45/45 | easyfly_global_planner、easyfly_multi_object_tracking、easyfly_pointcloud_filter 全败 |
| copyright | 16/16 | 同上三包全败 |
| uncrustify | 12/13 | 同上三包 |
| pep257 | 6/6 | 同上三包全败 |
| cppcheck / flake8 / lint_cmake / xmllint | 0 失败（cppcheck 另有 13 项 skipped） | — |

- **与历史对照**：本轮 79 项 lint 失败 + V2-04 的 1 error + ctest 聚合层重复计数 13 项 ≈ 历史记载的"131 项 84 失败主要为 lint"，量级与构成吻合，未发现新增恶化。
- **复测更新（V2-04 修复后）**：easyfly_multi_object_tracking 重写 test_sort.cpp 后，本包 copyright 8→7、cpplint 25→23、uncrustify 6→5，全工作区 lint 债务 79→**75** 项（cpplint 43、copyright 15、uncrustify 11、pep257 6）。
- **处理**：列入暂停期债务清单（schedule-v2 §8 里程碑 3"单独建立 lint 债务清单"即此项）。修复属机械性整改（加 copyright 头、格式化），建议恢复开发前用工具批量处理，不逐项手改；本轮只记录。
- **备注**：easyfly_serial 未注册任何 lint 测试，与其他三包不一致；若要求全工作区 lint 口径统一，需补注册（同样属测试补齐，非阻塞）。

---

## V2-06 G3 测试范围缺口：§10.2 故障注入测试未编写

- **发现时间**：2026-09-15，G3 执行时
- **test-v2 §18 分类**：TEST（测试范围缺口），非缺陷、非阻塞
- **现象**：test-v2 §10.2 要求的组件级故障注入测试尚不存在：Bridge 命令校验/watchdog、UAVState 各遥测独立过期、MissionFSM 双 Goal/电池失效/析构 join、traj_server 非法 knot/时间倒退、/mission_status 单一发布者所有权。G3 当前可执行范围仅为 §10.1 的 P0 mock。
- **G3 现有范围结论**：P0 FlightController mock **14/14 PASS**（2026-09-15，基线 238ce3d，use_sim_time:=false，四 Action server 就绪，测后无残留进程）。
- **处理**：按 schedule-v2 §9"补测试"允许范围择机编写（建议 G4 定位姿态故障前后，这些确定性测试正好可用于区分 Bridge/FlightController 责任）；编写后从 G3 补跑。
- **证据**：`artifacts/acceptance-20260915-1759/g3-summary.md`、`g3-mock-output.log`、`g3-flight-control-node.log`。

---

## V2-07 px4_sitl.launch 默认 PX4 路径与实际目录漂移

- **发现时间**：2026-09-15，G4 准备阶段
- **test-v2 §18 分类**：ENV/CONTRACT 边界（配置漂移，非阻塞，有环境变量级规避）
- **现象**：`src/simulation/easyfly_px4_sitl/launch/px4_sitl.launch.py` 的 `_resolve_px4_dir()` 解析优先级为 `PX4_DIR` 环境变量 > `~/PX4-Autopilot-1.16.1` > `~/PX4-Autopilot`。用户已将 PX4 目录改名为 `PX4-Autopilot-1.16.2`（G0 对齐 v1.16.2），两个默认候选路径均已不存在，不设 `PX4_DIR` 时启动将失败或解析到错误路径。
- **规避（G4 全程使用）**：每个终端先 `export PX4_DIR=/home/jia/PX4-Autopilot-1.16.2`。
- **根治建议**：恢复开发后将默认路径改为 `PX4-Autopilot-1.16.2`（或改为宽松匹配 `~/PX4-Autopilot*`）；属 launch 文件一行级修改，随下一批代码修改一起提交并更新基线。
- **备注**：test-v2 §4.3 已记载"目录名不能作为版本依据"，本条是它在启动层的具体体现。

---

## V2-08 PX4 目录改名致 SITL 构建缓存失效

- **发现时间**：2026-09-15，G4 第 1 步（make px4_sitl gazebo-classic）
- **test-v2 §18 分类**：ENV（环境固化问题，非代码缺陷）
- **现象**：make 报 CMakeCache 目录不一致、`Tools/check_submodules.sh: not found`、`can't cd to /home/jia/PX4-Autopilot/msg`。
- **根因**：该 PX4 树最初在 `/home/jia/PX4-Autopilot` 名下编译（CMakeCache `PX4_SOURCE_DIR=/home/jia/PX4-Autopilot`），后两次改名（→1.16.1→1.16.2），build 树内缓存与 ninja 规则中的绝对路径全部失效。EasyFly 的 px4_sitl.launch.py 直接运行旧二进制不触发重编，故此前未暴露。
- **处置**：删除 `build/px4_sitl_default` 后全量重编（进行中）；重编后二进制路径不变，EasyFly 链无影响。拒绝符号链接应急方案（固化旧路径，违背冻结基线方向）。
- **附带发现**：build 树内无任何历史 ulog——既往 Attitude failure 会话从未保存 ulog，test-v2 §4.3/§11 的 ulog 要求正是补此窟窿；G4 每轮必须归档 ulog。
- **备注**：重编不改变 PX4 git 状态（仍为 54f0455ffc / v1.16.2-dirty）；EasyFly 仓库无改动，不产生新基线。
