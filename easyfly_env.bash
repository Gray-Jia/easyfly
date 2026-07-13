#!/bin/bash
# EasyFly 环境初始化脚本
# 用法: source easyfly_env.bash

EASYFLY_WS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ROS2 环境
if [ -f /opt/ros/humble/setup.bash ]; then
  source /opt/ros/humble/setup.bash
fi

# 工作空间
if [ -f "${EASYFLY_WS}/install/setup.bash" ]; then
  source "${EASYFLY_WS}/install/setup.bash"
fi

echo "EasyFly environment loaded. Workspace: ${EASYFLY_WS}"
