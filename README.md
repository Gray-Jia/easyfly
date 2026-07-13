# EasyFly

自主无人机开源平台，基于 ROS2 Humble + PX4 1.16 + Gazebo Classic。

## 架构

| 层 | 子层 | 说明 |
|---|------|------|
| ① 通信层 | C1 驱动 / C2 协议 / C3 媒体 | 传感器驱动、MAVLink桥接、视频推流 |
| ② 感知层 | P1 预处理 / P2 检测 / P3 跟踪 / P4 融合 | 目标检测跟踪、SLAM、深度估计 |
| ③ 执行层 | E1 状态机 / E2 规划 / E3 控制 | 任务调度、路径规划、飞行控制 |
| ④ 应用接口层 | A1 SDK / A2 服务 / A3 任务 | 对外API、ROS2服务、任务编排 |

## 编译

```bash
source /opt/ros/humble/setup.bash
source easyfly_env.bash
build_all.bash
```

## 许可证

Apache-2.0
