/**
 * mavlink_bridge_node.cpp — easyfly_mavlink_bridge 主入口
 *
 * 使用 MultiThreadedExecutor:
 *   回调内调用 mavros service 时，其他线程可处理 async response
 */
#include "easyfly_mavlink_bridge/mavlink_bridge.hpp"
#include <rclcpp/executors/multi_threaded_executor.hpp>

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<easyfly_mavlink_bridge::MavlinkBridge>();

  rclcpp::executors::MultiThreadedExecutor executor;
  executor.add_node(node);
  executor.spin();

  rclcpp::shutdown();
  return 0;
}
