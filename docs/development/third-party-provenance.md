# 第三方来源与本地补丁登记（D0 / D1 / D4 修复）

D0/D1/D4登记只使用当时本地源码、Git与交接记录，不升级依赖；2026-10-07相机修复另有显式上游导入，见下节。未知来源如实标记。README 链接表示线索，不等于已确认导入 commit。

| 目录/组件 | 可确认来源与版本 | 来源缺口 | 许可证证据 | 本地补丁入口 |
|---|---|---|---|---|
| src/third_party/slam/fast_lio（含 ikd-Tree） | README 指向 Ericsii/FAST_LIO ROS2 fork、hku-mars/ikd-Tree；包版本0.0.0 | 精确导入 branch/commit、ikd-Tree 来源基点未知；无独立 .git | 根 LICENSE 为 GPL v2；嵌入组件需按各自文件进一步清点 | `git log -- .../fast_lio`：7455e06 入库、b52a4fd 外参/启动保护；集成 launch 位于 easyfly_fast_lio_integration |
| src/third_party/planners/ego_planner（8包） | 当前工作树绑定 EasyFly commit；历史参考来自 EGO ROS2 移植 | 精确上游仓库、fork、branch、commit未知 | 多数 package.xml 为 TODO，未发现统一根许可证；ego_to_mavros 为MIT、quadrotor_msgs 为BSD元数据；不能据此认定整个源码许可 | 7455e06 导入；04d99d4、51d0375、0724742 安全/控制修复；D0 planner_manager.cpp初始化修复；D1会话service/消息字段、managed速度/固定终点约束、预设模式隔离、会话急停事件、FSM及traj_server停流/闲置时钟修复，详见schedule-v4及d1-navigation |
| src/third_party/livox_sdk2 | README 指向 Livox-SDK/Livox-SDK2；交接约1.2.5 | 无独立版本commit/tag，精确基点未知 | LICENSE.txt 列示部分为MIT及文件范围，按原文保留 | c707cd3；以当前源码和Git历史为准 |
| src/communication/c1_drivers/livox_ros_driver2 | README 上游 Livox ROS Driver2；package版本1.0.0 | 精确上游commit、设备固件/配置未冻结 | LICENSE.txt 明确部分代码范围为MIT | c707cd3及当前集成修改；仿真插件是另一包 |
| src/communication/c1_drivers/realsense_ros | 本地origin为IntelRealSense/realsense-ros；gitlink及实际HEAD均d69f05c1b4a3f0d5740e25d6429d4417c7f3d75d | 本地适配提交不保证存在于上游；根 .gitmodules 缺映射，不能自动复原 | 嵌套仓库 LICENSE / package.xml 为Apache-2.0，实际分发按仓库各组件文件 | d69f05c1 `adapt realsense packages for workspace build`；本次嵌套状态无修改 |
| src/third_party/librealsense | 随主仓库源码；交接API2.56.5 | 精确导入commit未知，无独立git来源锁定 | 根LICENSE为Apache-2.0；third-party各自许可需保留 | c707cd3及当前CMake集成；不自动安装固件/udev |
| src/third_party/onnxruntime | 本地SDK/源码存在；交接1.23.2、a83fc4d5；VERSION_NUMBER可核对 | 主仓库忽略此目录；下载来源、包校验和与本地构建参数尚未形成重建清单 | 本地LICENSE为MIT，按实际文件核对 | 不在主仓库可重建输入中；GPU provider/CUDA ABI见test-v2，不能凭目录存在认定GPU可用 |
| geographic_lib / nlopt / nlohmann_json 空目录 | 没有可导入源码；GeographicLib当前主要使用系统安装 | 空目录不是依赖锁定；NLopt/JSON未实现需求不能假定存在 | 无vendored许可证证据 | 将来实际依赖时记录系统包或明确源码来源 |

2026-10-05 用户选定自有代码采用 Apache-2.0；根 LICENSE、README 与51个自有包
元数据已统一。第三方目录、驱动原许可未改，EGO 上游许可 TODO 不以平台许可替代。
混合来源的 `easyfly_gazebo_plugins`（Livox 移植）、`easyfly_gazebo_models`（模型资源）
保留原包元数据并继续待逐项核对；不能据此认定整包第三方内容为 MIT 或 Apache-2.0。

D4 lint/SITL 修复另外修改 EGO `plan_manage/src/traj_server.cpp`：在单线程
`spin` 返回后 cancel/reset timer，释放订阅、全局 publishers、clock 与 node，
避免全局 ROS 对象晚于 middleware/default context 析构而崩溃或挂起。
新增 `test/test_traj_shutdown.py`、CTest 注册及测试依赖，实际进程在独立
ROS domain 193 下覆盖系统时间、正值冻结/运行仿真时间的 SIGINT/SIGTERM。
修改仅为本地生命周期补丁，不能补足上游精确 commit 与许可来源缺口；未改第三方声明。

## 如何定位现有补丁

```bash
git log --oneline -- src/third_party/slam/fast_lio
git show b52a4fd -- src/third_party/slam/fast_lio src/perception/p3_tracking/easyfly_fast_lio_integration
git show 0724742 -- src/third_party/planners/ego_planner
git -C src/communication/c1_drivers/realsense_ros show d69f05c1
```

这些是 EasyFly 导入后的差异线索，不能当作“相对于未知上游commit的完整patch”。后续冻结每个依赖时需补：真实仓库URL、branch/tag/commit、来源归档hash、导入日期、本地patch、许可证与初始化步骤。D0允许这些字段明确为未知；不虚构日期或通过更新依赖掩盖来源缺口。

## 2026-10-07 导航仿真的局部算法补丁

本轮改动 EGO `plan_env` 的最新帧 QoS、处理时间诊断与库的 Debug 热路径优化，
以及 `plan_manage` 的当前会话曲线归属检查，防止已 STOP 的旧曲线被下一任务
当作运行中曲线。保留全部源/接收新鲜度、占据与碰撞安全判断；自有辅助测试
不补足 EGO 原始版本/许可来源缺口，第三方声明保持原样。

Livox 仿真插件两处射线起点改为 origin+min_range*axis，消除从 origin 测长
却由 Gazebo GetRange 再加 min_range 的系统偏差。约定依据是
[Gazebo 11.10.2 官方 MultiRayShape](https://raw.githubusercontent.com/gazebosim/gazebo-classic/gazebo11_11.10.2/gazebo/physics/MultiRayShape.cc)，
不是导入新的插件版本或改变系统 Gazebo。新增的 `ray_geometry.hpp` 和原生 ODE
几何测试为 EasyFly 自有 Apache-2.0 文件；保留原 Livox 派生文件的来源说明及
包内混合许可，不把整包重新标为自有 Apache-2.0。结果和边界见 schedule-v4 §20。

## 2026-10-07 项目局部相机加载保护

`easyfly_gazebo_plugins/safe_camera`明确从ros-simulation/gazebo_ros_pkgs **3.9.0**
导入camera源文件及头，SHA和官方原路径见其README。保留OSRF版权/Apache-2.0；
仅独立class/library/header命名＋Node::Get空指针保护。未覆盖/升级系统安装，未
导入整个gazebo_ros包，仍链接原camera base/multi_camera/ROS node实现。
包元数据追加Apache-2.0表示该明确派生部分；原混合Livox来源/原MIT元数据保留，
不能据此为整包第三方内容补出未知许可证证据。版本固定是来源tag及原字节hash，
不是声称整个已安装Debian构建与上游源码逐字一致。

## 2026-10-07 项目局部 transport 生命周期修复

`easyfly_gazebo_plugins/safe_transport`来自Gazebo Classic官方tag
`gazebo11_11.10.2`，来源归档SHA256为
`51976f29e375463e3bbf1343b7532b038728f13389e94e78b2fa8271911b2dcb`。
`upstream/`的11个transport实现文件与该归档逐字相同，保留原OSRF/Apache-2.0
声明，逐文件清单在`upstream/SHA256SUMS`，已实际cmp核对；IOManager及server
main的派生文件保留上游版权，增加EasyFly自有修改声明，安装Apache LICENSE。

局部补丁为完整私有transport库＋独立`easyfly_gzserver`，不是改写系统库或下载
运行未知二进制。只有私有server的RPATH选择同SONAME副本，不将其目录加入通用
LD_LIBRARY_PATH或GAZEBO_PLUGIN_PATH；系统gz/gzclient/PX4/其他ROS节点不使用
该副本。正常析构同步join，自线程析构转交独立清理线程，join后再释放全套资源。
main释放Server后drain并要求live/pending为0，join清理线程后才签成功退出。

构建要求精确Gazebo11.10.2、IOManager头及原transport二进制SHA匹配；运行校验
Connection和兼容代码来自同一私有库，并校验实际Gazebo core SHA。具体固定值
和回滚入口见该目录README。配置不匹配拒绝，不覆盖/升级/usr或/opt，原系统
transport/core/camera hash已核对保持不变。并不追认历史自然self-join的唯一归因，
亦不涉及未知来源EGO许可/退出根因。

## 2026-10-07–08 PX4 POSIX HRT仿真局部补丁

来源为本机`/home/jia/PX4-Autopilot-1.16.2`，Git HEAD
`54f0455ffcd755534539a7cf33a09a20bf71d29d`；现有Gazebo子模块脏状态保持原样。
实际原HRT源码SHA256为
`eb826fde8a1eaae3eef98c8f37c686bc21f62ad061d9cc86c8d2fa2a1ea1ede2`，
原ELF为`9484a69221d73465f621b80662b51d72cd4739b216c9a4526dbaef35ba67c9a4`。
不以HEAD替代实际输入字节验证，不修改工程外原安装。

补丁位于`src/simulation/easyfly_px4_sitl/compat/px4-1.16.2-hrt.patch`，SHA256为
`be22a4dfcf1fcb242906d893687052ccb19a0cdd48cf205e2f7e6bfa39bef8ab`。锁覆盖
tick/回调/周期重排的方法参照[PX4官方实现](https://github.com/PX4/PX4-Autopilot/blob/main/platforms/posix/src/px4/common/drv_hrt.cpp)，
不是导入整个main或升级所有模块；实际派生输入及补丁均由SHA固定。局部构建
保留PX4 BSD-3-Clause源版权，许可证原文副本`compat/PX4-LICENSE`随资源安装；
不能用EasyFly根Apache-2.0替代PX4派生部分的原许可。自有构建工具、选择器、
原生fixture及诊断入口为Apache-2.0。

只替换局部HRT对象并复用原生产编译/链接参数；原生对照的外层timer/log桩
不进入运行二进制。用户确认仿真默认选择局部兼容版、输入不符明确拒绝；
实机不启用。重建步骤、测试证据及仍保留的退出FAIL见
[电池专项说明](battery-sitl.md)和schedule-v4 §22，不宣称全部历史故障唯一同因。

## 2026-10-09 EGO managed短轨迹细化补丁

本批修改EGO `plan_manage`的planner_manager及FSM：managed细化后重新检查
动力学，对短轨迹改为全时间域有界重参数化，再做原优化/完整碰撞检查。
原边界导数输入不按比例伪造，固定终点和发布前严格限速继续保留；legacy
非managed不切换到新时间策略。通用FIRST_TRAJ_COLLISION误导标记改为
FIRST_TRAJ_FAILED，不改变故障消息接口或急停/排空语义。

新增`test/test_managed_refinement.py`为自有Apache-2.0组件夹具，真实运行
原EGO节点但使用测试自有合法odom/远处障碍/阻塞障碍输入，不是历史点云
回放或实际飞行。EGO原始导入commit与许可来源缺口仍按上表保留，不用
自有测试许可证替代整个第三方实现。结果与边界见schedule-v4 §23。
