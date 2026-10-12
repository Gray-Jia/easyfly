# EasyFly 场景资源候选清单

检索日期：2026-10-12。目标是为 ROS2 Humble + PX4 + Gazebo Classic 收集可修改、可随项目分发的三维场景。

本清单是依据上游 README、许可证原文和目录的初筛。本轮没有下载场景资产、冻结 commit、逐文件完成许可核对，也没有启动 Gazebo 验证。接入难度和适用任务是结合 EasyFly 架构作出的判断。

## 首批优先候选

| 项目 | 场景内容 | 许可证证据 | EasyFly 接入建议 |
| --- | --- | --- | --- |
| [AWS Small Warehouse](https://github.com/aws-robotics/aws-robomaker-small-warehouse-world/tree/ros2) | 仓库、货架、托盘及杂物；适合绕障与巡检 | [MIT-0 原文](https://raw.githubusercontent.com/aws-robotics/aws-robomaker-small-warehouse-world/ros2/LICENSE) | 优先提取 world 与 models；上游已有 ROS2/Gazebo Classic 启动方式，接入成本预计较低 |
| [AWS Small House](https://github.com/aws-robotics/aws-robomaker-small-house-world/tree/ros2) | 多房间住宅、家具；适合转角、门洞和室内搜索 | [MIT-0 原文](https://raw.githubusercontent.com/aws-robotics/aws-robomaker-small-house-world/ros2/LICENSE) | 使用静态环境；README 提醒物体质量/惯量不一致，不能直接把家具变为动态障碍 |
| [AWS Bookstore](https://github.com/aws-robotics/aws-robomaker-bookstore-world/tree/ros2) | 书架、桌子和服务台；适合密集障碍与多航点任务 | [MIT-0 原文](https://raw.githubusercontent.com/aws-robotics/aws-robomaker-bookstore-world/ros2/LICENSE) | 使用原静态场景，另外定义无人机出生点与航线；不沿用地面机器人出生位置 |
| [MRS Gazebo Common Resources](https://github.com/ctu-mrs/mrs_gazebo_common_resources) | README 列有森林、草地及简单树模型 | 仓库声明 BSD-3-Clause；具体提取模型仍需核对其自身声明 | 先确定所需分支：本轮默认页为 ros2，不能据此当作 Classic 直接兼容；择取几何/模型资源，不引入整套 MRS 控制系统 |
| [pcg_gazebo](https://github.com/boschresearch/pcg_gazebo) | Python 程序化生成模型与 world，可用于成批组合障碍场景 | [Apache-2.0 原文](https://github.com/boschresearch/pcg_gazebo/blob/master/LICENSE)；仓库另有第三方许可登记 | 推荐离线生成 SDF/world；其 ROS 运行时功能使用 rospy，README 明确这部分不支持 ROS2，不作为 EasyFly 运行时依赖 |

AWS 三个候选的 LICENSE 明确允许使用、修改、发布、分发、再许可和出售，文本属于 MIT-0。这里确认的是上游许可证文本；实际引入时仍应保存选中资产的来源和任何独立声明。

这些 AWS 仓库在 2026 年归档后默认分支可能只显示归档说明，上表特意链接保留原代码的 `ros2` 分支。固定实际 commit 后再导入，不依赖默认分支自动变化。其场景 README 提供本地 Gazebo 加载方式，无须使用 AWS RoboMaker 云服务。

## 扩展候选与边界

| 项目 | 场景内容 | 许可情况 | 取舍 |
| --- | --- | --- | --- |
| [AWS Hospital](https://github.com/aws-robotics/aws-robomaker-hospital-world/tree/ros2) | 医院走廊、房间、护士站、设备 | [仓库 MIT-0](https://raw.githubusercontent.com/aws-robotics/aws-robomaker-hospital-world/ros2/LICENSE)；[README](https://raw.githubusercontent.com/aws-robotics/aws-robomaker-hospital-world/ros2/README.md) 明确另引用大量 Fuel 模型 | 第二批。医院建筑与外部设备分开登记；外部模型不能一律按 MIT-0 分发。可替换许可不明的设备，并将保留依赖存到本地 |
| [OSRF gazebo_models](https://github.com/osrf/gazebo_models) | 模型素材库，含公寓、咖啡馆、建筑、车辆及各种道具 | [根许可证 CC BY 3.0](https://raw.githubusercontent.com/osrf/gazebo_models/master/LICENSE)；仍核对具体模型声明与来源 | 适合组装新地图；不是整套 world 集合。按资产登记署名、许可链接和修改记录 |
| [PX4 gazebo-models](https://github.com/PX4/PX4-gazebo-models) | [worlds](https://github.com/PX4/PX4-gazebo-models/tree/main/worlds) 有森林、Baylands、草地、山脊、墙体、风场、移动平台等 | [根许可证 BSD-3-Clause](https://raw.githubusercontent.com/PX4/PX4-gazebo-models/main/LICENSE)；被引用模型另核对 | 面向现代 Gazebo。当前 Classic 需要转换/替换插件，不能直接使用现代 Gazebo 启动脚本；可作为未来迁移资源 |
| [Clearpath cpr_gazebo](https://github.com/clearpathrobotics/cpr_gazebo) | 农业、山地巡检、桥/洞穴、办公室及施工版办公室、果园 | [office](https://raw.githubusercontent.com/clearpathrobotics/cpr_gazebo/noetic-devel/cpr_office_gazebo/package.xml)、[inspection](https://raw.githubusercontent.com/clearpathrobotics/cpr_gazebo/noetic-devel/cpr_inspection_gazebo/package.xml) 的 package.xml 声明 BSD；本轮未取得完整资产许可证据 | 场景丰富，列为待核对候选。不能凭 package.xml 的 BSD 字样把全部 meshes/textures 判为已获分发授权 |
| [Space Robotics Gazebo Environments](https://github.com/AndrejOrsula/space_robotics_gz_envs) | 月球/火星地形、岩石和太阳能板；程序化资产 | README：代码 MIT 或 Apache-2.0，自有/生成资产 CC0；第三方派生资源另有署名要求 | 后续特殊地形候选；面向现代 Gazebo，生成管线在 srb_assets 子模块中，需另外冻结和核对 |

CC BY 3.0/4.0 允许商业用途和改编，但需按要求署名、提供许可链接，并说明衍生修改；不要把这些资产重标为 EasyFly 自有 Apache-2.0。条款见 [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) 与 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。

## 暂不整包引入的合集

[IRSg-ARG/uav_gazebo_environments](https://github.com/IRSg-ARG/uav_gazebo_environments) 有三层办公室、仓库、大迷宫、学校和警察局等六种 world，适合无人机探索。其 README 明确说明一个 maze 模型来自没有许可证的仓库，且首页未提供覆盖自有 world 的明确许可证据。本轮将它作为场景设计参考，不能把“可下载”视为可随 EasyFly 发布。

它引用的 school、grey_wall、grass_plane 有来源线索，未来可从原始项目分别核对；不能用部分模型有许可推导整个合集有许可。

## 建议的接入顺序

1. 仓库 → 住宅 → 书店：先形成三种可运行的 Classic 静态场景。
2. 森林与程序化几何障碍：用确定随机种子和布局参数扩展场景数量，保持可复现。
3. 医院、办公室、农业/巡检：完成依赖资产登记后扩展。
4. 现代 Gazebo 的地形、城市和移动平台：放到独立的兼容性迁移批次。

每个 EasyFly 场景建议记录：唯一 ID、来源 URL、branch/commit、资产文件清单与 SHA256、各资产 license/作者、原始许可文件、修改说明、仿真器版本、模型依赖、出生点、可飞区域和参考任务。大资产可分包下载，日常启动使用已缓存的本地资源。

world 的 visual 与 collision 均需存在且几何一致；无人机出生点、飞行高度与通道净宽另行验证。场景加载成功只表示资源可解析，不等于导航任务或传感器效果已经通过验收。

现有 `easyfly_gazebo_worlds` 放 EasyFly 场景入口，`easyfly_gazebo_models` 放可复用模型；第三方原资产与本地改动应能追溯。新增世界只替换环境资源，继续复用现有无人机、传感器、导航 Action 和唯一飞行输出链。
