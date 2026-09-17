#!/bin/bash
# run_navigate_acceptance.sh — M4.2 全局导航验收编排器
# 流程: 清理 → 启动感知全链路 (含规划节点) → N1-N5 用例 → 清理
# 退出码: 0=全部通过; launch 日志: /tmp/easyfly_navigate_launch.log
set -u
WS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="${LOG:-/tmp/easyfly_navigate_launch.log}"

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
echo "[1/3] 启动感知全链路 (含规划节点): 日志 $LOG"
setsid ros2 launch easyfly_px4_sitl perception_sitl.launch.py > "$LOG" 2>&1 &
LAUNCH_PGID=$!
sleep 3
if ! kill -0 "$LAUNCH_PGID" 2>/dev/null; then
  echo "ERROR: launch 启动失败, 日志尾部:"
  tail -20 "$LOG"
  exit 1
fi

echo "[2/3] 运行验收用例 (N1-N5, 约 5-7 分钟)..."
python3 "$WS/test/navigate_acceptance.py"
RC=$?

echo "[3/3] 清理完成, 退出码: $RC"
exit $RC
