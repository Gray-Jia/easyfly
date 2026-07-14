/**
 * mavlink_bridge_node.cpp — easyfly_mavlink_bridge 主入口
 *
 * 启动 MavlinkBridge 节点，负责 mavros2 ↔ easyfly_msgs 的双向翻译。
 */
#include "easyfly_mavlink_bridge/mavlink_bridge.hpp"

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<easyfly_mavlink_bridge::MavlinkBridge>();
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
