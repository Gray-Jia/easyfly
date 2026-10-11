// Copyright 2026 EasyFly Project
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//     http://www.apache.org/licenses/LICENSE-2.0
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#ifndef LIVOX_LASER_SIMULATION__RAY_GEOMETRY_HPP_
#define LIVOX_LASER_SIMULATION__RAY_GEOMETRY_HPP_

#include <ignition/math/Vector3.hh>

namespace easyfly_livox
{

// Gazebo MultiRayShape::GetRange adds min_range to the measured ray length.
// Both initial construction and per-frame updates must start at min_range,
// not at the sensor origin; otherwise every return is biased by min_range.
inline ignition::math::Vector3d rayStart(
  const ignition::math::Vector3d & origin,
  const ignition::math::Vector3d & unit_axis, double min_range)
{
  return origin + unit_axis * min_range;
}

}  // namespace easyfly_livox

#endif  // LIVOX_LASER_SIMULATION__RAY_GEOMETRY_HPP_
