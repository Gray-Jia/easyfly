// Copyright 2026 EasyFly Project
//
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

#pragma once
#include <algorithm>
#include <chrono>
#include <cmath>
#include <string>
#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/header.hpp>
namespace ef_safety
{
inline double steady()
{
  return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
}
inline int64_t stamp(const std_msgs::msg::Header & h)
{
  if (h.stamp.sec < 0 || h.stamp.nanosec >= 1000000000u) {
    return 0;
  }
  return static_cast<int64_t>(h.stamp.sec) * 1000000000LL + h.stamp.nanosec;
}
struct ClockGate
{
  int64_t last{0};
  double progress{0};

  bool check(int64_t now, double age)
  {
    const double s = steady();
    const bool backwards = last > 0 && now < last;

    if (now != last) {
      progress = s;
    }
    last = now;
    return now > 0 && !backwards && s - progress <= age;
  }
};

inline bool fresh(
  const std_msgs::msg::Header & h, int64_t now, double receipt, double age,
  const std::string & frame)
{
  const auto source = stamp(h);
  const double source_age = static_cast<double>(now - source) * 1e-9;

  return now > 0 && source > 0 && std::isfinite(receipt) && std::isfinite(age) && age > 0 &&
         h.frame_id == frame && source_age >= -std::min(0.2, age) && source_age <= age &&
         steady() - receipt >= 0 && steady() - receipt <= age;
}
}  // namespace ef_safety
