#!/bin/bash
# 按层编译, 用法: ./build_layer.bash c|p|e|a
set -e

case "${1:-}" in
  c|communication)
    colcon build --symlink-install --packages-up-to c3_media
    ;;
  p|perception)
    colcon build --symlink-install --packages-up-to p4_fusion
    ;;
  e|execution)
    colcon build --symlink-install --packages-up-to e3_control
    ;;
  a|application)
    colcon build --symlink-install --packages-up-to a3_mission
    ;;
  *)
    echo "用法: $0 {c|p|e|a}"
    echo "  c = 通信层  p = 感知层  e = 执行层  a = 应用接口层"
    exit 1
    ;;
esac
echo "=== 编译完成 ==="
