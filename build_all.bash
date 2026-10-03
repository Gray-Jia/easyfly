#!/bin/bash
set -e
cd "$(dirname "$0")"
echo "=== EasyFly 全量编译 ==="
colcon build --base-paths src --symlink-install --event-handlers console_direct+
echo "=== 编译完成 ==="
echo "请执行: source install/setup.bash"
