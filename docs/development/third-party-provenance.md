# 第三方来源与本地补丁登记（D0）

本轮只使用本地源码、Git 与交接记录核对，不联网下载，不升级依赖。未知来源如实标记。README 链接表示线索，不等于已确认导入 commit。

| 目录/组件 | 可确认来源与版本 | 来源缺口 | 许可证证据 | 本地补丁入口 |
|---|---|---|---|---|
| src/third_party/slam/fast_lio（含 ikd-Tree） | README 指向 Ericsii/FAST_LIO ROS2 fork、hku-mars/ikd-Tree；包版本0.0.0 | 精确导入 branch/commit、ikd-Tree 来源基点未知；无独立 .git | 根 LICENSE 为 GPL v2；嵌入组件需按各自文件进一步清点 | `git log -- .../fast_lio`：7455e06 入库、b52a4fd 外参/启动保护；集成 launch 位于 easyfly_fast_lio_integration |
| src/third_party/planners/ego_planner（8包） | 当前工作树绑定 EasyFly commit；历史参考来自 EGO ROS2 移植 | 精确上游仓库、fork、branch、commit未知 | 多数 package.xml 为 TODO，未发现统一根许可证；ego_to_mavros 为MIT、quadrotor_msgs 为BSD元数据；不能据此认定整个源码许可 | 7455e06 导入；04d99d4、51d0375、0724742 安全/控制修复；本轮 planner_manager.cpp 初始化修复 |
| src/third_party/livox_sdk2 | README 指向 Livox-SDK/Livox-SDK2；交接约1.2.5 | 无独立版本commit/tag，精确基点未知 | LICENSE.txt 列示部分为MIT及文件范围，按原文保留 | c707cd3；以当前源码和Git历史为准 |
| src/communication/c1_drivers/livox_ros_driver2 | README 上游 Livox ROS Driver2；package版本1.0.0 | 精确上游commit、设备固件/配置未冻结 | LICENSE.txt 明确部分代码范围为MIT | c707cd3及当前集成修改；仿真插件是另一包 |
| src/communication/c1_drivers/realsense_ros | 本地origin为IntelRealSense/realsense-ros；gitlink及实际HEAD均d69f05c1b4a3f0d5740e25d6429d4417c7f3d75d | 本地适配提交不保证存在于上游；根 .gitmodules 缺映射，不能自动复原 | 嵌套仓库 LICENSE / package.xml 为Apache-2.0，实际分发按仓库各组件文件 | d69f05c1 `adapt realsense packages for workspace build`；本次嵌套状态无修改 |
| src/third_party/librealsense | 随主仓库源码；交接API2.56.5 | 精确导入commit未知，无独立git来源锁定 | 根LICENSE为Apache-2.0；third-party各自许可需保留 | c707cd3及当前CMake集成；不自动安装固件/udev |
| src/third_party/onnxruntime | 本地SDK/源码存在；交接1.23.2、a83fc4d5；VERSION_NUMBER可核对 | 主仓库忽略此目录；下载来源、包校验和与本地构建参数尚未形成重建清单 | 本地LICENSE为MIT，按实际文件核对 | 不在主仓库可重建输入中；GPU provider/CUDA ABI见test-v2，不能凭目录存在认定GPU可用 |
| geographic_lib / nlopt / nlohmann_json 空目录 | 没有可导入源码；GeographicLib当前主要使用系统安装 | 空目录不是依赖锁定；NLopt/JSON未实现需求不能假定存在 | 无vendored许可证证据 | 将来实际依赖时记录系统包或明确源码来源 |

另：README 的平台 Apache-2.0 描述与若干 EasyFly package.xml 的 MIT 元数据不一致，本文不擅自重写许可。D0 只登记差异，分发前需对来源及许可事实单独收口。

## 如何定位现有补丁

```bash
git log --oneline -- src/third_party/slam/fast_lio
git show b52a4fd -- src/third_party/slam/fast_lio src/perception/p3_tracking/easyfly_fast_lio_integration
git show 0724742 -- src/third_party/planners/ego_planner
git -C src/communication/c1_drivers/realsense_ros show d69f05c1
```

这些是 EasyFly 导入后的差异线索，不能当作“相对于未知上游commit的完整patch”。后续冻结每个依赖时需补：真实仓库URL、branch/tag/commit、来源归档hash、导入日期、本地patch、许可证与初始化步骤。D0允许这些字段明确为未知；不虚构日期或通过更新依赖掩盖来源缺口。
