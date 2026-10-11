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

#ifndef EASYFLY_FLIGHT_CONTROL__TRAJECTORY_STARTUP_TIMEOUT_HPP_
#define EASYFLY_FLIGHT_CONTROL__TRAJECTORY_STARTUP_TIMEOUT_HPP_

#include <cmath>

namespace easyfly_flight_control
{

// A planner may need a few bounded retries before its first valid command is
// available.  Keep this grace finite: it only applies before the first READY
// PositionCommand and never changes the action deadline or the post-start
// stream watchdog.
constexpr double kDefaultTrajectoryStartupGrace = 8.0;
constexpr double kMinTrajectoryStartupGrace = 0.5;
constexpr double kMaxTrajectoryStartupGrace = 15.0;
constexpr double kTrajectoryStreamTimeout = 0.5;

inline double sanitizeTrajectoryStartupGrace(const double configured_seconds)
{
  if (!std::isfinite(configured_seconds) ||
    configured_seconds < kMinTrajectoryStartupGrace ||
    configured_seconds > kMaxTrajectoryStartupGrace)
  {
    return kDefaultTrajectoryStartupGrace;
  }
  return configured_seconds;
}

// Treat the deadline boundary as expired.  Invalid or already elapsed timing
// evidence fails closed so a clock jump cannot extend an action.
inline bool trajectoryDeadlineExpired(
  const double elapsed_seconds,
  const double deadline_seconds)
{
  return !std::isfinite(elapsed_seconds) || elapsed_seconds < 0.0 ||
         !std::isfinite(deadline_seconds) || deadline_seconds <= 0.0 ||
         elapsed_seconds >= deadline_seconds;
}

// Before the first READY frame, the planner gets a bounded retry window, but
// that window can never extend an action past its own deadline.  The caller
// supplies the action's total deadline window (measured from acceptance), so
// this helper stays independent of ROS clock types and can be exercised
// without a node.
inline bool trajectoryStartupTimedOut(
  const double gap_seconds,
  const double startup_grace_seconds,
  const double action_deadline_seconds)
{
  if (!std::isfinite(gap_seconds) || gap_seconds < 0.0 ||
    !std::isfinite(startup_grace_seconds) || startup_grace_seconds <= 0.0 ||
    !std::isfinite(action_deadline_seconds))
  {
    return true;
  }
  return trajectoryDeadlineExpired(gap_seconds, action_deadline_seconds) ||
         gap_seconds >= startup_grace_seconds;
}

// Return true only when the relevant bounded watchdog has elapsed.  Invalid
// timing evidence fails closed instead of silently extending an action.
inline bool trajectoryStreamLost(
  const bool have_ready_command, const double gap_seconds,
  const double startup_grace_seconds,
  const double stream_timeout_seconds = kTrajectoryStreamTimeout)
{
  if (!std::isfinite(gap_seconds) || gap_seconds < 0.0) {
    return true;
  }
  const double timeout = have_ready_command ? stream_timeout_seconds : startup_grace_seconds;
  return !std::isfinite(timeout) || timeout <= 0.0 || gap_seconds >= timeout;
}

}  // namespace easyfly_flight_control

#endif  // EASYFLY_FLIGHT_CONTROL__TRAJECTORY_STARTUP_TIMEOUT_HPP_
