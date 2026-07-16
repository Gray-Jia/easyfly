/**
 * flight_control_node.cpp — easyfly_flight_control 主入口
 *
 * FlightController 节点：3 个 Action Server (Takeoff / Land / GoToWaypoint)
 * 使用 MultiThreadedExecutor — 避免 service 调用死锁
 */
#include "easyfly_flight_control/flight_controller.hpp"
#include <rclcpp/executors/multi_threaded_executor.hpp>

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<easyfly_flight_control::FlightController>();

  rclcpp::executors::MultiThreadedExecutor executor;
  executor.add_node(node);
  executor.spin();

  rclcpp::shutdown();
  return 0;
}
