# D2 SDK、参数与平台服务

D2实现范围依据plan-v3第7节。公开飞行动作不改变，SDK和服务不发布UAVCommand或MAVROS setpoint；所有运动仍经现有执行层。项目所有者确认：任务只管理现有格式，正式版本化YAML/搜索/复杂编排留在D3；参数只开放明确动态白名单。

## 启动与示例

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
# 仅启动服务，不启动仿真、感知、飞控或自动发起任务：
ros2 launch easyfly_mission_srvs platform.launch.py use_sim_time:=false
# 已有仿真profile自动加载同一服务集合，不重复启动mission_fsm：
ros2 launch easyfly_sim_launcher profile.launch.py profile:=navigation_dev
# C++和Python示例默认仅查询状态；实际运动必须显式选择命令：
ros2 run easyfly_core sdk_state_example
ros2 run easyfly_pybind sdk_state_example
# 查询正在运行的SITL状态时，须匹配仿真时钟：
ros2 run easyfly_core sdk_state_example --sim-time
ros2 run easyfly_pybind sdk_state_example --sim-time
```

服务launch默认use_sim_time=true；独立系统时钟调试显式false。start_mission_executor默认false，已有完整仿真链会启动原执行器；只有尚无`/execute_mission`时才显式true。硬件未验证profile拒绝启动。

## C++ / Python SDK

`easyfly_core::Client`持有独立ROS Context、Node、executor和工作线程，不接管外部节点。C++客户端覆盖takeoff、land、go_to、navigate、follow、track、execute_mission，Goal沿用现有类型。Python的`easyfly_pybind.Client`绑定同一实现，最小集合为state、takeoff、land、navigate、execute_mission、cancel。

每次请求返回Operation；snapshot区分：

- admission：pending、accepted、rejected、unavailable、unsupported、capacity_exceeded、closed。
- status/success/message：真实动作成功/失败/取消或未发送原因。服务器SUCCEEDED但success=false仍为失败。
- local_status：本地准入超时、关闭或传输异常，不能当作远端已停。
- cancel_status：请求/响应状态；取消响应接受不等于真实CANCELED。
- remote_execution_pending：仍未确认远端终态；feedback是当前操作最新反馈。

wait(timeout)仅观察，超时返回false，不自动取消。SDK已经close且无其他未决任务时，最后一个Operation的wait还在同一超时预算内等待DDS清理完成，以免真实终态返回后立即退出撞上后台析构；等待清理超时也可返回false，snapshot中的真实终态不会被改写。其他任务仍未决时，一个Operation完成不保证整套SDK可退出。cancel()只请求精确所属Goal；未知句柄保留待取消标志，迟到接受后再取消。可独立配置准入响应超时策略，自动取消默认关闭。默认32个未决请求上限，超限不发送。

close(timeout)停止新请求、冻结并取消状态订阅、取消所属任务；返回false表示任务或运行时清理尚未完成。客户端门面析构后，无Python对象/门面裸指针的独立运行时继续处理迟到响应，真实终态收齐后才释放Context。永远无回应的服务器会保留未决运行时；进程退出不保证外部服务器停止。用户需保留Operation观察结果，不能用析构代替飞行停止证明。

Python只轮询/等待，不在SDK的ROS线程调用Python回调；wait与close释放GIL，支持with语法。running只表示SDK运行中，server_ready(action)分别检查后端，不能把SDK创建成功当成可飞。

状态快照保留原header和各独立有效标志；时钟选择、源时间及接收时间新鲜度必须分别核对，fresh不代替pose/velocity/connected等准入条件。SITL须使用与消息匹配的仿真时钟选项，系统时间调试使用系统时钟。

```python
from easyfly_pybind import Client, Status

# 只有已有有效定位/飞控/地图/规划链且用户明确要飞行时才调用：
client = Client(use_sim_time=True)  # SITL；系统时间环境改为False
operation = client.navigate(2.0, 0.0, 1.5, 1.0)
if not operation.wait(30.0):
    operation.cancel()
    # cancel是请求，继续观察snapshot.remote_execution_pending及真实终态。
print(operation.snapshot().status, operation.snapshot().message)
print('drained:', client.close(5.0))
```

SDK调用已有`/execute_mission`，不执行任意Python代码。目录管理/服务执行使用下述正式任务门面；SDK直接传mission_file仍遵循已有后端的文件路径协议，不自动获得目录管理能力。

## 参数服务

`easyfly_params`复用D0 profile/schema_version=1、安全契约解析和启动有效值；非法启动覆盖直接失败。标准ROS参数服务提供有类型的读取/描述/原子写入。

当前动态白名单：

| 节点 | 可写参数 | 实际作用/限制 |
|---|---|---|
| /easyfly_params | operator_note | 导出注记，UTF-8≤512字节；允许真正空字符串 |
| /easyfly_params | export_pretty | bool；控制有效配置JSON缩进 |
| /easyfly_perception_srvs | max_age | double，0.05–10s；控制查询与能力ready的新鲜度窗口 |

profile、schema_version、冻结安全契约、话题、任务目录/服务超时和时钟等不动态修改；只读或重启生效。不会把导出的冻结源契约当成所有运行中节点的真实参数，也不代理任意远程节点写入。

`/platform/params/query`兼容QueryParams：param_name为本节点名；空param_value只读，非空必须为JSON标量。实际空字符串写入编码为`""`，因此与读取明确区分；current_value也始终为JSON。未知参数、类型/范围错误、null/对象/数组、只读更新失败且原值保持。`/platform/params/export`（Trigger）导出当前有效profile、启动输入、冻结源契约与注记；success是导出成功，不是飞行就绪。

```bash
ros2 param set /easyfly_params export_pretty true
ros2 service call /platform/params/query easyfly_msgs/srv/QueryParams "{param_name: operator_note, param_value: ''}"
ros2 service call /platform/params/export std_srvs/srv/Trigger '{}'
```

## 感知服务

`/platform/perception/query`（GetPerception）支持kind=targets或obstacles，源为`/target_positions`和`/obstacles`；range_limit≤0返回全部，正值按当前UAV位置到目标/障碍中心距离筛选，非监督模块的AABB净距。正范围要求新鲜有效的UAV位姿。

响应status明确区分NOT_READY、VALID、STALE、INVALID、UNSUPPORTED；source_topic、observed_at、age_sec说明源数组时间。有效空数组保持原非零header，不与未就绪混淆。全部数组/条目须为odom、新鲜且几何有限；无效position_valid、非法尺寸/时间/置信度等失败关闭，不将损坏的目标悄悄过滤成“有效空”。只有VALID响应提供可用数据。steady接收间隔与ROS源时间同时检查，避免持续重播旧数据伪装新观测。

`/platform/perception/capabilities`（GetCapabilities）分别返回names/implemented/ready/details；实现查询接口不表示数据就绪，标签/精准降落明确unsupported。节点不推理、预测或发布控制命令。

## 任务服务

`/platform/mission/manage`（ManageMission）操作：list、validate、start、query、cancel。列表只包含配置目录直属常规文件（.mission/.yaml/.yml），名称必须basename，不接受任意路径或越界symlink；≤256个目录项、≤64KiB单任务。

默认目录由安装包内可信示例的真实路径定位，兼容`--symlink-install`；显式目录仍严格限制canonical父目录，越界软链接不列出也不执行。快照以本机临时路径传给原执行器，服务与执行器须能读取同一文件系统；本批不提供跨主机任务文件传输。

当前格式仍是平坦key=value/key:value与`---`分隔，仅支持takeoff/waypoint/hover/land。后缀.yaml不代表完整YAML支持。任务服务和原mission_fsm共享同一校验实现，先完整验证再执行；未知步骤/字段、重复字段、非有限数字、缺失必需字段、非法范围均拒绝整份任务。静态遗留范围：高度≤50m、速度≤20m/s、坐标绝对值≤1000m、yaw∈[-π,π]、hover等待≤3600s、≤256步。后端更低的运行时限制、状态与相对距离仍由实际飞行动作准入，validate成功不是飞行许可。

start向原`/execute_mission`发送经校验的私有快照，不再读取可变目录原文。返回accepted只证明后端接受；query(execution_id)观察running/succeeded/failed/canceled等状态。最多保留最近32项终态记录，过旧ID返回not_found；反馈另有feedback_valid与源时间，不能把进度当最终结果。

cancel必须匹配门面生成的execution_id，只取消对应真实Goal，不取消直接客户端或其他任务。等待准入/取消响应有预算；超时仍保持旧任务所有权，迟到准入后精确取消，真实终态后才释放槽/清理私有快照。未确认的执行快照不会因超时被删掉；如果服务进程退出时仍未确认，快照可能留在临时目录，不能删除它推断外部执行已停。

`/platform/mission/capabilities`列出legacy_mission，versioned_yaml/search暂unsupported。目录中任务可能含真实运动，list/validate不会自动执行；没有任意Python脚本上传/执行入口，也不新建飞行或任务执行状态机。

```bash
ros2 service call /platform/mission/manage easyfly_msgs/srv/ManageMission "{operation: list}"
ros2 service call /platform/mission/manage easyfly_msgs/srv/ManageMission "{operation: validate, mission_name: waypoint_demo.mission}"
# start后保存返回execution_id，再query/cancel；需要已有实际飞行链和明确执行意图。
```

## 验证边界

本批以实际ROS组件、mock后端和短软件plant验证SDK/服务/控制层连接，不宣称完整PX4/Gazebo SITL、硬件、G9–G11通过。三项新增服务只增加类型，不修改D1轨迹链消息布局；部署仍需正常同步构建。实际结果及失败历史以schedule-v4第8节为准。
