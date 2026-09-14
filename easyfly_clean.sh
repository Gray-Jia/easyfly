#!/bin/bash
# easyfly_clean.sh — 仿真环境一键清理
# 用途: 彻底清除所有 EasyFly 仿真相关进程 (含最易残留的 fastlio_mapping!)
#
# 什么时候用:
#   1. 启动新仿真前 (保险起见)
#   2. RViz 出现 path 乱画 / 点云飞机消失 (多实例残留的典型症状)
#   3. Ctrl+C 退出 launch 后想确认环境干净
#
# 背景 (2026-09-13 踩坑): fast_lio 的 fastlio_mapping 进程路径是
#   install/fast_lio/lib/fast_lio/fastlio_mapping (不含 "easyfly"),
#   常规 pkill 模式匹配不到 → 反复启停后累积僵尸实例 → 多个 SLAM
#   同时发布 /Odometry /path → RViz path 乱画、点云/飞机消失。
# 验证: pkill 后 `pgrep -cf fastlio_mapping` 应为 0 (无输出)。

echo "清理前:"
pgrep -af "fastlio_mapping|gzserver|gzclient|bin/px4|mavros_node|mavlink_bridge_node|rc_receiver_node|easyfly_flight_control|easyfly_mission_fsm|ego_planner_node|traj_server|easyfly_pointcloud_filter|easyfly_semantic_map|easyfly_global_planner|easyfly_target_tracking|component_container|rviz2" 2>/dev/null | head -30

pkill -9 -f fastlio_mapping        2>/dev/null   # ★ 最易残留
pkill -9 -f gzserver               2>/dev/null
pkill -9 -f gzclient               2>/dev/null
pkill -9 -f "px4_sitl_default/bin/px4" 2>/dev/null
pkill -9 -f mavros_node            2>/dev/null
pkill -9 -f mavlink_bridge_node    2>/dev/null
pkill -9 -f rc_receiver_node       2>/dev/null
pkill -9 -f easyfly_flight_control 2>/dev/null
pkill -9 -f easyfly_mission_fsm    2>/dev/null
# M4.x 规划/感知节点 (2026-09-14 踩坑: 未列入导致反复启停累积多实例,
# 每个 ego_planner_node ~100% CPU → RTF 崩 → EKF 退化 → 飞行中 failsafe 漂飞)
pkill -9 -f ego_planner_node       2>/dev/null
pkill -9 -f traj_server            2>/dev/null
pkill -9 -f easyfly_pointcloud_filter 2>/dev/null
pkill -9 -f easyfly_semantic_map   2>/dev/null
pkill -9 -f easyfly_global_planner 2>/dev/null
pkill -9 -f easyfly_target_tracking 2>/dev/null
pkill -9 -f component_container    2>/dev/null
pkill -9 -f "ros2 launch"          2>/dev/null
pkill -f    rviz2                  2>/dev/null
sleep 2

left=$(pgrep -cf "fastlio_mapping|gzserver|bin/px4|mavros_node|component_container|ego_planner_node|traj_server" 2>/dev/null || echo 0)
echo "清理完成, 残留进程: ${left:-0}"
