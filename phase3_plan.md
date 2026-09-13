# EasyFly 阶段三（感知流水线）执行计划

> 已确认决策：
> - FAST-LIO：基于 AstraDroneOpen 的 ROS1 版本，自行移植到 ROS2 Humble
> - 目标检测：YOLO11n ONNX + COCO 预训练类别起步；架构须支持自定义模型/数据集（细节执行时由用户说明）
> - 节奏：里程碑制，不排具体时间
> - 验收场景：标准场景（起飞 → 飞过行人/车辆场景 → 检测+跟踪+3D定位 RViz2 显示 + FAST-LIO 同步建图）

---

## 一、现状基线（2026-09 核实）

| 项 | 现状 |
|----|------|
| 感知层 18 个包 | 全部空壳（仅 CMakeLists + package.xml，src/ 为空） |
| `easyfly_iris.sdf` | 无任何传感器插件 |
| 仿真场景 | 仅 `empty.world`，无行人/车辆等目标模型 |
| 可参考资源 | AstraDroneOpen：带 MID-360+双相机的 iris SDF、Gazebo 模型库、ROS1 版 FAST_LIO；easyfly_msgs 已有 DetectionInfo/TrackInfo 等消息契约 |

## 二、技术风险（前置声明）

| # | 风险 | 应对 |
|---|------|------|
| R1 | **YOLO11n ONNX 与系统 OpenCV 版本兼容性**：Ubuntu 22.04 apt 的 OpenCV 4.5.4 大概率不支持 YOLO11 的 ONNX 算子（通常需 4.10+） | M2 第一步先做推理验证；若不支持，切换 **onnxruntime CPU 后端**（官方支持 22.04，C++ 集成简单），不编译升级 OpenCV（避免与 cv_bridge 冲突） |
| R2 | FAST-LIO ROS1→ROS2 移植工作量（消息类型、launch、tf、PCL API） | M3 独立里程碑，与视觉线并行；若严重受阻，上报并评估 LIO-SAM 备选 |
| R3 | 仿真 LiDAR 数据格式：FAST-LIO 依赖 livox CustomMsg（含 IMU） | M0 仿真相机/雷达插件时，参照 AstraDroneOpen 的 px4_iris_sdf 方案输出 CustomMsg + IMU |
| R4 | Gazebo 深度图质量影响 3.5 精度 | 仿真用理想内外参，先验证数据流；必要时 rosbag 回灌 |

## 三、里程碑划分

### M0 仿真传感器就绪（唯一硬阻塞，所有工作的根）

| 任务 | 内容 |
|------|------|
| M0-1 | `easyfly_iris.sdf` 增加前视深度相机插件（D435i 风格：color + depth + aligned camera_info + IMU），参照 AstraDroneOpen px4_iris_sdf |
| M0-2 | 增加 MID-360 仿真 LiDAR（平放），输出 `/livox/lidar`（CustomMsg，含 IMU）+ 兼容 sensor_msgs/PointCloud2 |
| M0-3 | 搭建标准验收场景 world（从 AstraDroneOpen 模型库引入行人/车辆模型），替换/扩展现有 empty.world |
| M0-4 | 更新 `px4_sitl.launch.py` + 新建感知调试 launch（RViz2 预配置） |

**验收**：`ros2 topic list` 出现相机/雷达全部话题；RViz2 图像与点云显示正常；录制 rosbag 并检查数据质量（时间戳、帧率、深度值有效性）。

### M1 P1 预处理就绪（依赖 M0）

| 任务 | 内容 |
|------|------|
| M1-1 | `easyfly_camera_calib`：内参/外参 YAML 加载与 `/camera_info` 发布（仿真用理想内参） |
| M1-2 | `easyfly_coord_transform`：TF 树管理（map→odom→base_link→camera/lidar）+ 坐标变换工具（消息契约沿用 easyfly_msgs） |

**验收**：`ros2 run tf2_tools view_frames` TF 树结构正确；外参配置一处管理、各节点共用。

### M2 目标检测（依赖 M1，与 M3 并行）

| 任务 | 内容 |
|------|------|
| M2-1 | **推理后端验证（R1 风险前置）**：先用最小示例验证 OpenCV DNN 能否加载 YOLO11n ONNX；不行则引入 onnxruntime |
| M2-2 | 后端抽象：`IDetectorBackend` 接口（OpenCV DNN / onnxruntime / 预留 cuda·intel 目录对应 TensorRT/OpenVINO），模型路径、类别表、置信度阈值全部 config 化 |
| M2-3 | 完整节点：订阅 `/camera/color` → 推理 → 发布 `DetectionInfoArray`；调试图像话题（画框可视化） |
| M2-4 | 自定义模型接入预留：类别/输入尺寸/前处理参数可配置（等用户提供模型后细化） |

**验收**：仿真场景中行人/车辆出现实时检测框；COCO 与自定义模型可通过配置切换。

### M3 FAST-LIO 移植（依赖 M0，与 M2 并行，独立风险线）

| 任务 | 内容 |
|------|------|
| M3-1 | ROS1→ROS2 移植 AstraDroneOpen/FAST_LIO → `easyfly_fast_lio`：替换 catkin→ament、launch→python、消息/tf API 适配、PCL 兼容性处理 |
| M3-2 | 与仿真 CustomMsg 对接、调参（仿真 LiDAR 噪声特性与实机不同） |

**验收**：RViz2 中点云地图随飞行累积成形，里程计轨迹平滑无漂移突变。**若移植严重受阻，及时上报评估 LIO-SAM 备选，不阻塞视觉线。**

### M4 多目标跟踪（依赖 M2）

| 任务 | 内容 |
|------|------|
| M4-1 | `easyfly_multi_object_tracking`：SORT（卡尔曼滤波预测 + 匈牙利算法数据关联），订阅 `DetectionInfoArray` → 发布 `TrackInfoArray`（带稳定 ID） |

**验收**：多目标稳定分配 ID，短暂遮挡/漏检后 ID 保持。

### M5 像素转 3D（依赖 M2 + M1，建议在 M4 后）

| 任务 | 内容 |
|------|------|
| M5-1 | `easyfly_pixel_to_3d`：检测框 + 深度图 → 目标 3D 位置（相机系→base_link→odom），输出带协方差的 3D 目标消息 + RViz2 marker |

**验收**：RViz2 中 3D marker 与目标模型实际位置误差在可接受范围（仿真理想条件下应较小）。

### M6 全链路集成验收（标准场景 Demo）

| 任务 | 内容 |
|------|------|
| M6-1 | 集成 launch：一次启动 = 仿真 + 感知全链路（检测→跟踪→3D 定位）+ FAST-LIO 建图 + RViz2 同屏显示 |
| M6-2 | 结合已有 mission_fsm/flight_control 执行起飞+航线飞行，完成标准场景演示 |
| M6-3 | `easyfly_pointcloud_filter` / `easyfly_time_sync`（低优先，为阶段四规划准备，按需裁剪） |
| M6-4 | 更新 `schedule.md` 进度、整理验收录屏/截图 |

**验收（阶段三整体完成标准）**：无人机起飞 → 飞过行人/车辆场景 → RViz2 中实时显示检测框、跟踪 ID、目标 3D 位置，同时 FAST-LIO 点云地图持续累积。

## 四、依赖与并行关系

```
M0 仿真传感器
 ├──→ M1 预处理 ──→ M2 检测 ──→ M4 跟踪 ──┐
 │                     └────→ M5 pixel_to_3d ──┼──→ M6 集成验收
 └──→ M3 FAST-LIO（独立并行）────────────────┘
```

- M2（视觉线）与 M3（激光线）**并行推进**，互不阻塞；
- M0 是唯一全局阻塞项，最先完成；
- M3 若受阻不影响 M1→M2→M4→M5 主线推进。

## 五、执行约定

1. 每个里程碑完成后汇报验收结果，通过后进入下一里程碑；
2. R1（YOLO11 后端）在 M2 第一步验证，切换方案前会先说明；
3. 自定义检测模型/数据集细节在 M2-4 阶段由用户补充说明；
4. 全程同步维护 `schedule.md`。
