// Copyright 2026 EasyFly Project
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

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
