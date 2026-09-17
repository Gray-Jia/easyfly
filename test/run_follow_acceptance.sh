#!/bin/bash
# run_follow_acceptance.sh — M4.1 跟随飞行验收编排器
# 流程: 清理 → 启动感知全链路 (含 mover + 跟随节点) → F1-F5 用例 → 清理
# 退出码: 0=全部通过; launch 日志: /tmp/easyfly_follow_launch.log
set -u
WS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="${LOG:-/tmp/easyfly_follow_launch.log}"

set +u  # ROS setup.bash 与 set -u 冲突
source /opt/ros/humble/setup.bash
source "$WS/install-v2/setup.bash"
set -u

cleanup() {
  echo ""
  echo "[编排器] 关闭仿真环境..."
  if [ -n "${LAUNCH_PGID:-}" ]; then
    kill -INT -- "-$LAUNCH_PGID" 2>/dev/null
    sleep 5
    kill -9 -- "-$LAUNCH_PGID" 2>/dev/null
  fi
  bash "$WS/easyfly_clean.sh" > /dev/null 2>&1
}
trap cleanup EXIT

bash "$WS/easyfly_clean.sh"
echo "[1/3] 启动感知全链路 (含移动目标 + 跟随节点): 日志 $LOG"
setsid ros2 launch easyfly_px4_sitl perception_sitl.launch.py > "$LOG" 2>&1 &
LAUNCH_PGID=$!
# headless 资源保护: 反复启停后 X/GLX 资源耗尽会使 gzclient/rviz2 (GLX 窗口)
# 崩溃并连带拖垮 gzserver 世界初始化 (PX4 等 4560 超时自杀)。自动化验收
# 不需要 GUI — 启动后清理 gzclient/rviz2, 保留 gzserver 传感器仿真。
sleep 7
pkill -f gzclient 2>/dev/null
pkill -f "rviz2" 2>/dev/null
sleep 3
if ! kill -0 "$LAUNCH_PGID" 2>/dev/null; then
  echo "ERROR: launch 启动失败, 日志尾部:"
  tail -20 "$LOG"
  exit 1
fi

echo "[2/3] 运行验收用例 (F1-F5, 约 4-5 分钟)..."
python3 "$WS/test/follow_acceptance.py"
RC=$?

echo "[3/3] 清理完成, 退出码: $RC"
exit $RC
