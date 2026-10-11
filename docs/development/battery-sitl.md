# 电池采样失效与局部 PX4 仿真兼容版

2026-10-07–08电池专项：修复可确定复现的PX4 1.16.2 POSIX HRT并发队列缺陷。
用户确认仿真默认使用项目局部兼容版，缺少构建或来源/指纹不符时拒绝启动，
不静默回退原版；实机不启用。不改5s电池新鲜度、5s任务宽限及15%低电量
保护，不续用陈旧SYS_STATUS，不过滤非法帧或伪造电池有效标志。

## 原因与验证

原失败PX4 ULog无dropout：电池此前16.2V/约99%，battery_status却在16.674s
停止，system_power/cpuload亦停止周期更新，其它传感器/飞行状态继续，
PX4随后自行报告Battery unhealthy。不是正常耗尽，不能仅归因于ROS丢包。

本机HRT在回调期间释放队列锁，另一线程可重排正在调用的周期项，原回调
返回后又入队。编译真实PX4 HRT/queue/semaphore的原生确定性对照10/10出现
自环并丢失后续定时项；补丁串行化整个tick、回调和周期重新入队，采用
递归互斥，10/10队列完整，同线程回调重入亦通过。方法参照[PX4上游实现](https://github.com/PX4/PX4-Autopilot/blob/main/platforms/posix/src/px4/common/drv_hrt.cpp)，
不整体升级。原FAIL没有当时队列/线程快照，不能唯一还原竞争参与者和交错，
也不证明任何历史电池失效都同因；确定修复的是已复现的定时器缺陷。

## 构建与使用

构建不启动仿真或飞行，输出目录必须不存在。仅支持已核对的本机源/二进制
指纹，不改工程外PX4源码/库/二进制；复用原对象和生产编译/链接参数，只
替换HRT对象。原生测试的timer/log桩不进入真实二进制，lockstep和原飞控
模块保留。辅助代码Apache-2.0，PX4派生补丁保留BSD-3-Clause及原版权头；
[许可证副本](../../src/simulation/easyfly_px4_sitl/compat/PX4-LICENSE)随资源安装。

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
# 首次构建；本工作区已经生成该目录，再执行会拒绝覆盖。
ros2 run easyfly_px4_sitl prepare_px4_hrt \
  --px4-dir /home/jia/PX4-Autopilot-1.16.2 \
  --output-dir /home/jia/easyfly_ws/build/easyfly_px4_hrt_compat
```

默认输入为 `build/easyfly_px4_hrt_compat/px4-input`，二进制SHA256为
`5df380603e0c1b8c19e69b36bacc18a68218bb0c216e0c29976d2b6d7931e227`。
基本/完整感知入口、navigation_sitl、battery_sitl与D5仿真入口统一校验。
`PX4_DIR`指定受支持原安装时映射到兼容版；指定兼容输入/私有staging时验证
实际源、wrapper、模块别名和指纹，保持私有rootfs不被替换。不再自动尝试
1.16.1或其它未审查安装；硬件入口不调用该选择器。

需保留旧构建并重新生成时，使用另一个新目录，再明确设置
`EASYFLY_PX4_HRT_COMPAT_DIR=/绝对路径/新兼容构建目录`，指向包含
compatibility.json与px4-input的目录。不要修改manifest绕过验证，不原地
覆盖证据。不同目录可使完整ELF调试指纹不同，按各自manifest核对；本批
artifact版与默认版机器码.text逐字节一致。

下面的电池观察入口才会显式飞行：正式起飞→悬停20s→降落，最多三轮；
不注入假状态、不自动补偿失败。新目录/domain/端口必须明确且无其它仿真：

```bash
mkdir /home/jia/easyfly_ws/artifacts/my-battery-check
ros2 run easyfly_sim_launcher battery_sitl \
  --px4-dir /home/jia/PX4-Autopilot-1.16.2 \
  --output-dir /home/jia/easyfly_ws/artifacts/my-battery-check \
  --domain 216 --gazebo-port 11431 --cycles 1
```

## 结果与未解决项

证据：`artifacts/battery-diagnosis-sitl-20261007.73ebGr/`。局部版三轮起降及
导航/搜索取消、超时、AUTO.LAND接管六类均PASS；默认版普通三步任务PASS、
24正常退出。原始battery/sys_status/UAVState、所有ULog与真实终态均保存。

默认版三轮飞行/电池子范围正常，但退出semantic_map_node SIGSEGV，整轮
保持FAIL（23正常退出）。`final-battery-evidence-audit.json`明确电池专项
通过、平台9场景8PASS/1FAIL。兼容版所有场景armed电池无效观测为0；ULog
电池最大记录间隔0.200–0.212s，无dropout并持续至记录结束附近；记录速率
不等于实际采样频率，不新增0.21s生产阈值。

无效/低电量的单次RTL及任务真失败、无后续Land由真实FSM＋SDK的mock后端
组件回归核实，不冒充实际飞行故障注入。D5只做配置/启动绑定回归，不
宣称重验完整精准降落矩阵。初始FIRST_TRAJ_COLLISION和新退出崩溃单列；
旧退出专项、UI、实机及G9–G11未重启。详见[schedule-v4第22节](../../schedule-v4.md)。
