/**
 * flight_control_node.cpp — easyfly_flight_control 主入口
 *
 * FlightController 节点：3 个 Action Server (Takeoff / Land / GoToWaypoint)
 */
#include "easyfly_flight_control/flight_controller.hpp"

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<easyfly_flight_control::FlightController>();
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
