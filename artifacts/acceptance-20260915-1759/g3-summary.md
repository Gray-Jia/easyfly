# G3 组件级测试结论 — 2026-09-15
基线: 238ce3d（G2 修复提交，新 G2/G3 基线）
范围: test-v2 §10.1 P0 FlightController mock（无 PX4、无 Gazebo）

## 执行环境
- flight_control_node 后台启动, use_sim_time:=false, install-v2 环境
- 四个 Action server 全部就绪: /takeoff /land /goto_waypoint /follow_trajectory
- 测试后进程已清理, 无残留

## 结果: 14/14 PASS
1. action servers ready
2. takeoff transaction succeeds
3. non-finite goal rejected
4. old trajectory ID cannot activate new goal
5. wrong trajectory frame rejected
6. trajectory wait cancel is CANCELED
7. old-time N+1 stays in trajectory wait
8. new trajectory ID activates trajectory
9. valid trajectory reaches TRAJECTORY encoder
10. active trajectory rejects rollback ID
11. trajectory stream loss aborts explicitly
12. concurrent goals reserve one slot
13. waypoint cancel is CANCELED
14. land cancel confirms OFFBOARD before CANCELED

## 范围缺口（非失败项）
test-v2 §10.2 列出的故障注入测试（Bridge 命令校验/watchdog、UAVState 各遥测独立过期、
MissionFSM 并发与电池失效、traj_server 非法输入、/mission_status 所有权）尚未编写，
属待补测试范围，不阻塞本次 mock 结论。
