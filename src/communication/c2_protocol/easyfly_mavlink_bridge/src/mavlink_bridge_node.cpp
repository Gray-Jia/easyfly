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
