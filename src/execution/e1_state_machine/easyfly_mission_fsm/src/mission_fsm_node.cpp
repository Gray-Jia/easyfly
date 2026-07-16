/**
 * mission_fsm_node.cpp — easyfly_mission_fsm 主入口
 */
#include "easyfly_mission_fsm/mission_fsm.hpp"

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<easyfly_mission_fsm::MissionFSM>();
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
