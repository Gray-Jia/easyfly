#!/bin/bash
# run_control_regression.sh — EasyFly 控制链回归测试编排器
#
# 流程: 清理残留进程 → 启动纯控制仿真 (empty.world) → 运行测试用例 → 关闭仿真
# 用例内容见 test/control_regression.py 头注释 (T1~T8, 约 6-10 分钟)
#
# 用法:
#   bash test/run_control_regression.sh
#   LOG=/tmp/my.log bash test/run_control_regression.sh   # 自定义 launch 日志路径
#
# 退出码: 0=全部硬断言通过, 1=有失败 (launch 日志在 $LOG)

set -u
WS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="${LOG:-/tmp/easyfly_regression_launch.log}"

# ---- 环境 (set +u: ROS setup.bash 引用未绑定变量, 与 set -u 冲突) ----
set +u
if [ -f /opt/ros/humble/setup.bash ]; then
  # shellcheck disable=SC1091
  source /opt/ros/humble/setup.bash
fi
if [ -f "$WS/install/setup.bash" ]; then
  # shellcheck disable=SC1091
  source "$WS/install/setup.bash"
fi
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

echo "[1/4] 清理残留仿真进程"
bash "$WS/easyfly_clean.sh"

echo "[2/4] 启动纯控制仿真 (empty.world + bridge + 控制节点)"
echo "       launch 日志: $LOG"
setsid ros2 launch "$WS/test/control_regression.launch.py" > "$LOG" 2>&1 &
LAUNCH_PGID=$!
sleep 3
if ! kill -0 "$LAUNCH_PGID" 2>/dev/null; then
  echo "ERROR: ros2 launch 启动失败, 日志尾部:"
  tail -20 "$LOG"
  exit 1
fi

echo "[3/4] 运行回归用例 (T1~T8, 全程约 6-10 分钟; T8 的 RTL 落地等待最长 4 分钟)"
python3 "$WS/test/control_regression.py"
RC=$?

echo "[4/4] 清理完成, 退出码: $RC"
exit $RC
