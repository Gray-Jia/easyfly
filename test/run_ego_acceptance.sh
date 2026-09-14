#!/bin/bash
# run_ego_acceptance.sh — M4.3 EGO-Planner 验收编排器 (轻链)
#
# 流程: 清理 → 启动 ego_acceptance.launch.py (perception_demo.world 轻链) → E1-E4 用例 → 清理
# 用例内容见 test/ego_acceptance.py 头注释
#
# 用法:
#   bash test/run_ego_acceptance.sh
#   LOG=/tmp/my.log bash test/run_ego_acceptance.sh
#
# 退出码: 0=全部硬断言通过; 1=有失败 (launch 日志见 $LOG)

set -u
WS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="${LOG:-/tmp/easyfly_ego_launch.log}"

set +u  # ROS setup.bash 与 set -u 冲突
source /opt/ros/humble/setup.bash
source "$WS/install/setup.bash"
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
echo "[1/3] 启动 EGO 轻链仿真 (perception_demo.world): 日志 $LOG"
setsid ros2 launch "$WS/test/ego_acceptance.launch.py" > "$LOG" 2>&1 &
LAUNCH_PGID=$!
sleep 3
if ! kill -0 "$LAUNCH_PGID" 2>/dev/null; then
  echo "ERROR: launch 启动失败, 日志尾部:"
  tail -20 "$LOG"
  exit 1
fi

echo "[2/3] 运行验收用例 (E1-E4, 约 5-8 分钟)..."
python3 "$WS/test/ego_acceptance.py"
RC=$?

echo "[3/3] 清理完成, 退出码: $RC"
exit $RC
