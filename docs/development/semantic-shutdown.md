# semantic_map退出专项（2026-10-09，已暂缓，尚未定位原崩溃）

当前状态：用户已明确要求无法复现则先不动、做好记录。本专项暂缓，
不主动复跑、启用捕获或修改实现；下文命令仅保留为诊断说明，不是当前
执行计划。原FAIL和全部证据保留，特定条件/系统因素尚未证实。若正常
开发中自然再次出现同类异常，保留现场并报告用户，再决定是否恢复排查；
不忽略退出码或改变现有故障处理。当前决定见schedule-v4第24.6节。

原证据是电池专项`default-cycles`：三次飞行已经成功，SIGINT退出阶段
semantic_map_node退出-11，整轮FAIL。当前有界复验正常不消除该FAIL，也
不证明误操作。节点生产C++及普通ELF未改变；本批增加退出回归与默认
关闭的取栈能力，不把诊断工具或通过的复跑称作修复。

## 回归与诊断分层

新`test_shutdown_ros.py`使用合法XYZI、TF、UAVState、/clock及障碍查询，
确认真实非空障碍、有效栅格和非地面输出后才发退出信号。覆盖系统、
运行及正值冻结仿真时钟×SIGINT/SIGTERM，普通/取栈两种入口共12项。
另有2项纯路由身份拒绝测试，共14项；不启动PX4或飞行、不注入畸形
点云，强制退出不得通过。

接续新增`test_shutdown_stress_ros.py`八项：合法6686点XYZI、真实动态目标
确认、每0.25s替换附加DDS reader，持续4s；另覆盖ROS时钟回跳2s后恢复
有效地图，普通/取栈×SIGINT/SIGTERM。两组ROS夹具使用相同独立domain，
CTest设置串行，不让并行测试污染彼此输入。

`test_capture.py`六项单独验证捕获工具：退出0/7、专用fixture的
std::terminate源码栈、忽略退出信号后的20s有界清理，以及两个mock清理
异常分支。fixture不链接生产节点；其SIGABRT不是原SIGSEGV的复现。
有界清理必须返回非零并标记FAIL，不能混作真实节点正常关闭验收。
工具清理已用finally保证inferior清理报错后仍尝试回收所属debugger。

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
colcon test --packages-select easyfly_semantic_map
```

ROS component main是单线程主执行器，TF listener另有线程；现有成员顺序
已经是listener先于buffer析构。另核对[已安装版本对应的Clock实现](https://raw.githubusercontent.com/ros2/rclcpp/16.0.19/rclcpp/src/rclcpp/clock.cpp)
及[TF Buffer实现](https://raw.githubusercontent.com/ros2/geometry2/0.25.20/tf2_ros/src/buffer.cpp)，
未据此确认该退出的竞争参与者，未修改系统ROS/TF库或擅自反转成员顺序。

## 显式取栈（默认关闭）

```bash
# 仅节点；不会发送飞行动作。
ros2 launch easyfly_semantic_map semantic_map.launch.py capture_shutdown:=true

# 完整仿真取栈：这里只启动平台，取栈仅对semantic_map生效。
ros2 launch easyfly_px4_sitl perception_sitl.launch.py \
  headless:=true semantic_capture_shutdown:=true
```

程序`semantic_shutdown_capture`只启动请求的semantic_map_node，不附加到
其它既有进程，不调试Gazebo/EGO。正常SIGINT/SIGTERM转发给本次创建且
exe/PID身份匹配的真实inferior；当前转发使用pidfd避免核对后的PID复用。
异常时保留线程栈并返回失败，不忽略异常。
不修改系统core_pattern，不联网下载调试符号。缺少gdb明确拒绝取栈，不
回退普通启动。新诊断参数均默认false，普通平台不启动调试器。

显式飞行入口也支持`--semantic-capture-shutdown`，例如在新的空目录、
共享飞控端口无其它仿真时运行原三轮takeoff→hover20s→Land：

```bash
ros2 run easyfly_sim_launcher battery_sitl \
  --px4-dir /home/jia/PX4-Autopilot-1.16.2 \
  --output-dir /绝对路径/新的空目录 --domain 218 --gazebo-port 11433 \
  --cycles 3 --semantic-capture-shutdown
```

该选项会改变调度时序，result.json单列diagnostic_only=true，不能用取栈
运行的通过证明普通运行的偶发故障已修复。wrapper、debugger、真实节点
的所属进程残留都须核对；launch正常退出不能覆盖inferior异常。

## 独立内存检查构建的限制

构建位于证据目录独立build/install，不覆盖工作区普通安装。只检查
非法内存访问，detect_leaks=0明确不作为内存泄漏签收。只插桩本节点及
其main，系统PCL/ROS库未整体插桩，未检出不等于不存在数据竞争。

首次ASan构建在退出前因Eigen分配ABI不一致失败：开启ASan把本节点的
EIGEN_MALLOC_ALREADY_ALIGNED从普通编译的1变为0，而系统PCL返回普通
malloc缓冲；handmade_aligned_free错误读取指针前8字节。原诊断FAIL保留，
不能追认成历史退出根因。另开诊断目录显式使用普通构建相同的值1后再
执行测试；这是诊断构建校正，不是生产修复，未关闭非法访问检查。

当前证据根目录`artifacts/semantic-shutdown-20261009.TG2N4P/`，原普通
三轮与校正内存检查的三轮均正常，退出回归通过。实际取栈运行及最终
检查结果见[schedule-v4第24节](../../schedule-v4.md)。原-11缺真实栈，
仍待获得可验证原因及修复对照；不以更多通过次数自动销账。

## 带源码行号的接续取证

接续证据`artifacts/semantic-shutdown-continue-20261009.SF4Jzh/`另建
symbols-build/install，仅添加`-g`，未启用ASan或改变优化策略。实际比较
模块.text及.rodata与普通版逐字节相同；生成main的.text不相同，不能
宣称整个新构建机器码都相同。因此保存generated-main-with-symbols原件，
只在该独立install中使用普通main的字节相同副本。生产安装未被替换。
gdb离线行号核对与真实/proc加载映射均保留，完整三轮飞行退出正常；
这仍是diagnostic_only=true，调试器改变时序，尚未定位历史-11。
