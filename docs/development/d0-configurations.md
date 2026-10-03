# D0 开发配置使用说明

本配置入口只组织已有仿真能力，不执行起飞目标，不恢复 G9-G11。

## 构建与检查

```bash
source /opt/ros/humble/setup.bash
./build_layer.bash a --dry-run
colcon build --base-paths src --packages-select easyfly_params easyfly_sim_launcher easyfly_px4_sitl --symlink-install --cmake-args -DBUILD_TESTING=ON
source install/setup.bash
ros2 run easyfly_params config_tool --profile navigation_dev --workspace /home/jia/easyfly_ws
```

`config_tool` 输出 profile 元数据、可实现能力、实际传给组合入口的 launch 参数和冻结的安全契约。`--workspace` 额外对照该工作树的源码默认值进行 10 项一致性检查，失败退出码为 2；它不读取运行中节点，也不声称导出全部运行时参数。使用非默认工作区时替换绝对路径。

源树未安装时也可离线检查：

```bash
PYTHONPATH=src/application/a1_sdk/easyfly_params python3 -m easyfly_params.configuration --profile navigation_dev --config-dir src/application/a1_sdk/easyfly_params/config --workspace /home/jia/easyfly_ws
```

## 配置集合

| profile | 实际组合入口 | 作用与限制 |
|---|---|---|
| base_sim | easyfly_sim.launch.py | PX4/Gazebo、MAVROS、bridge、RC；不包含飞控 Action server 或完整感知 |
| full_perception | perception_sitl.launch.py | 已有完整感知/地图/飞控/FSM/跟随/A*/EGO 组合 |
| navigation_dev | perception_sitl.launch.py | 同一已实现组合，用于后续导航开发；D0 不新增统一导航功能 |
| landing_dev | perception_sitl.launch.py | preparation_only：仅现有传感器/TF/核心链；标签、降落检测与精准降落均为 false |
| hardware_unverified | disabled | 可导出查看的未验证结构模板；profile launch 明确拒绝，不含真实设备参数 |

所有仿真 profile 默认 headless=true；已有直接 launch 的交互默认保持不变。受管 profile 入口只开放 `profile` 参数，并隔离父 launch 的通用 `config_file` 等上下文；需要交互诊断可直接使用已有 launch。

```bash
# 以下为功能开发启动方式，本轮 D0 未实际启动动态环境。
ros2 launch easyfly_sim_launcher profile.launch.py profile:=base_sim
ros2 launch easyfly_sim_launcher profile.launch.py profile:=navigation_dev
```

`capabilities=true` 指选定入口包含该类现有实现，不表示节点已就绪、当前数据有效或本轮通过动态验收。标签/降落未实现状态不得通过修改元数据变为可用。

## 安全参数来源与覆盖规则

`easyfly_params/config/safety_contracts.yaml` 是 D0 对现有默认值的冻结核对表，不会覆盖 C++ 或各节点 yaml。避免为集中配置而改动已验收控制链，D0 选择跨包一致性检查路线。

| 契约 | 生产者/来源 | 消费者/核对 |
|---|---|---|
| odom | pointcloud_filter output_frame、pixel_to_3d target_frame、semantic_map world_frame | EGO grid_map/frame_id |
| 200000 非地面点预算 | semantic_map max_nonground_points | EGO max_trusted_cloud_points |
| 0.5m 规划下界 / 3.2m 默认上界 | local_planner ground_height、virtual_ceil_height 默认参数 | profile 向 perception_sitl 显式传入 3.2m，再转交 local_planner |
| 首帧宽限 8s | flight_control.yaml | flight_control 内的有限宽限实现 |
| 首帧后断流 0.5s | trajectory_startup_timeout.hpp 常量 | FollowTrajectory watchdog；不是首帧宽限 |

检查针对源树默认值；绕过 profile 的自定义 launch/参数覆盖不在这次静态检查保证范围内。既有 G8 特定场景曾使用 2.0m 上界，那是专用场景约束，不能替换通用默认值。修改默认契约必须同步配置、生产者、消费者、负向测试和记录，不能单独改核对表使检查变绿。

开发 profile 与参数 SDK 分开：D0 不实现运行时参数写入、自动应用真实飞控参数或设备配置；这些属于后续 D2/设备开发。
