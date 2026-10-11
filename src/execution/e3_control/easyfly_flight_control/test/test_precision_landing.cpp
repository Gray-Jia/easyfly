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

#include <gtest/gtest.h>
#include <rcl/time.h>
#include <algorithm>
#include <limits>
#include <memory>
#include "easyfly_flight_control/flight_controller.hpp"

namespace easyfly_flight_control
{
class PrecisionLandingTestPeer
{
public:
  static void hover(FlightController & node)
  {
    node.timer_ctl_->cancel();
    node.active_ = FlightController::HOVER;
    auto state = std::make_shared<easyfly_msgs::msg::UAVState>();
    state->header.stamp = node.now();
    state->header.frame_id = "odom";
    state->connected = state->armed = state->pose_valid = state->attitude_valid = true;
    state->flight_mode = 3;
    state->position_z = 1.0;
    node.cb_uav_state(state);
  }
  static rclcpp_action::GoalResponse admit(FlightController & node, int tag = 7)
  {
    auto goal = std::make_shared<FlightController::PrecisionLand::Goal>();
    goal->tag_id = tag;
    goal->timeout = 5.0;
    rclcpp_action::GoalUUID uuid{};
    uuid[0] = 1;
    return node.handle_precision_goal(uuid, goal);
  }
  static bool externalRejected(FlightController & node)
  {
    rclcpp_action::GoalUUID uuid{};
    auto waypoint = std::make_shared<FlightController::GoToWaypoint::Goal>();
    waypoint->target_z = 1.0;
    waypoint->max_speed = 0.2;
    waypoint->acceptance_radius = 0.1;
    auto trajectory = std::make_shared<FlightController::FollowTrajectory::Goal>();
    trajectory->target_z = 1.0;
    trajectory->acceptance_radius = 0.1;
    trajectory->timeout = 5.0;
    auto takeoff = std::make_shared<FlightController::Takeoff::Goal>();
    takeoff->target_altitude = 1.0;
    auto land = std::make_shared<FlightController::Land::Goal>();
    const auto reject = rclcpp_action::GoalResponse::REJECT;
    return node.handle_waypoint_goal(uuid, waypoint) == reject &&
           node.handle_traj_goal(uuid, trajectory) == reject &&
           node.handle_takeoff_goal(uuid, takeoff) == reject &&
           node.handle_land_goal(uuid, land) == reject;
  }
  static rclcpp_action::GoalResponse handoff(
    FlightController & node, bool matching, bool fresh = true)
  {
    node.precision_handoff_ = true;
    node.precision_child_admission_pending_ = true;
    node.precision_handoff_aligned_ = true;
    node.precision_handoff_pending_ = true;
    node.precision_handoff_barrier_ns_ = node.now().nanoseconds() - 100000000;
    auto & status = node.flight_status_;
    status.header.stamp = node.now();
    status.valid = status.connected = status.armed = true;
    status.flight_mode = 3;
    status.flight_mode_name = "OFFBOARD";
    status.receipt_age_s = 0;
    node.flight_status_receipt_ = std::chrono::steady_clock::now();
    node.precision_handoff_board_ = {0, 0, 0};
    node.uav_.position_z = 0.3;
    auto & target = node.precision_target_;
    target.header.stamp = node.now();
    target.header.frame_id = "odom";
    target.source_header = target.header;
    target.source_header.frame_id = "camera_down_optical_frame";
    target.tag_id = 7;
    target.tag_size_m = 0.2;
    target.valid = true;
    target.plane_normal.z = 1;
    node.precision_target_receipt_ = std::chrono::steady_clock::now();
    if (!fresh) {node.precision_target_receipt_ -= std::chrono::seconds(1);}
    auto goal = std::make_shared<FlightController::Land::Goal>();
    goal->precision_landing_session_id = matching ? node.precision_session() : "wrong";
    return node.handle_land_goal({}, goal);
  }
  static void unknown(FlightController & node)
  {
    node.precision_handoff_ = true;
    node.precision_child_admission_pending_ = true;
    node.finish_precision(false, "admission unknown", false);
  }
  static bool owned(FlightController & node) {return node.precision_reserved_;}
  static bool modeGate(FlightController & node, int scenario)
  {
    node.precision_handoff_pending_ = true;
    node.precision_handoff_barrier_ns_ = node.now().nanoseconds() - 100000000;
    node.flight_status_receipt_ = std::chrono::steady_clock::now();
    auto & status = node.flight_status_;
    status = easyfly_msgs::msg::FlightStatus{};
    status.header.stamp = node.now();
    status.valid = status.connected = status.armed = true;
    status.flight_mode = 3;
    status.flight_mode_name = "OFFBOARD";
    if (scenario == 1) {status.header.stamp = rclcpp::Time(node.precision_handoff_barrier_ns_);}
    if (scenario == 2) {status.header.stamp.sec -= 1;}
    if (scenario == 3) {status.valid = false;}
    if (scenario == 4) {status.flight_mode = 7; status.flight_mode_name = "AUTO.LAND";}
    if (scenario == 5) {status.receipt_age_s = 1.1;}
    if (scenario == 6) {status.receipt_age_s = std::numeric_limits<double>::quiet_NaN();}
    if (scenario == 7) {node.flight_status_receipt_ -= std::chrono::seconds(2);}
    if (scenario == 8) {status.header.stamp.sec += 1;}
    if (scenario == 9) {status.armed = false;}
    return node.precision_handoff_mode_ready();
  }
  static bool externalModeBeforeAggregate(FlightController & node)
  {
    modeGate(node, 4);
    node.precision_start_source_ns_ = node.now().nanoseconds() - 200000000;
    return node.uav_.flight_mode == 3 && node.precision_mode_control_lost();
  }
  static bool target(FlightController & node, int scenario)
  {
    auto & target = node.precision_target_;
    target.header.stamp = node.now();
    target.header.frame_id = "odom";
    target.source_header = target.header;
    target.source_header.frame_id = "camera_down_optical_frame";
    target.tag_id = 7;
    target.tag_size_m = 0.2;
    target.valid = true;
    target.plane_normal.z = 1;
    node.precision_target_receipt_ = std::chrono::steady_clock::now();
    if (scenario == 1) {target.header.frame_id = "map";}
    if (scenario == 2) {target.source_header.stamp.sec += 1;}
    if (scenario == 3) {target.tag_id = 8;}
    if (scenario == 4) {target.plane_normal.z = 2;}
    if (scenario == 5) {target.position.z = std::numeric_limits<double>::quiet_NaN();}
    if (scenario == 6) {node.precision_target_receipt_ -= std::chrono::seconds(1);}
    if (scenario == 7) {target.source_header.frame_id = "other_camera";}
    if (scenario == 8) {target.header.stamp.sec = 0; target.header.stamp.nanosec = 0;}
    if (scenario == 9) {
      target.header.stamp.nanosec = 50000000;
      target.source_header.stamp = target.header.stamp;
    }
    if (scenario == 10) {
      target.header.stamp.nanosec = 250000000;
      target.source_header.stamp = target.header.stamp;
    }
    if (scenario == 11) {
      target.header.stamp.sec -= 1;
      target.source_header.stamp = target.header.stamp;
    }
    const bool ready = node.precision_target_ready();
    target = easyfly_msgs::msg::LandingGuidanceTarget{};
    return ready;
  }
  static bool ingress(FlightController & node, int64_t offset_ns)
  {
    auto target = std::make_shared<easyfly_msgs::msg::LandingGuidanceTarget>();
    target->header.stamp = rclcpp::Time(node.now().nanoseconds() + offset_ns);
    target->header.frame_id = "odom";
    target->source_header = target->header;
    target->source_header.frame_id = "camera_down_optical_frame";
    target->tag_id = 7;
    target->tag_size_m = 0.2;
    target->valid = true;
    target->plane_normal.z = 1;
    node.precision_last_stamp_ = 0;
    node.precision_target_.valid = false;
    std::shared_ptr<void> erased = target;
    node.sub_precision_->handle_message(erased, rclcpp::MessageInfo{});
    return node.precision_target_ready();
  }
};

class PrecisionLanding : public ::testing::Test
{
protected:
  void SetUp() override
  {
    context_ = std::make_shared<rclcpp::Context>();
    context_->init(0, nullptr);
    options_.context(context_).parameter_overrides(
      {
        rclcpp::Parameter("precision_enabled", true),
        rclcpp::Parameter("precision_tag_id", 7),
        rclcpp::Parameter("precision_tag_size_m", 0.2),
        rclcpp::Parameter("precision_horizontal_speed", 0.2),
        rclcpp::Parameter("precision_descent_speed", 0.1),
        rclcpp::Parameter("precision_align_tolerance", 0.1),
        rclcpp::Parameter("precision_handoff_height", 0.3),
        rclcpp::Parameter("precision_descent_floor_height", 0.2),
        rclcpp::Parameter("precision_max_height", 3.0),
        rclcpp::Parameter("precision_max_radius", 2.0),
        rclcpp::Parameter("precision_plane_z", 0.0)});
    node_ = std::make_shared<FlightController>(options_);
    ASSERT_EQ(rcl_enable_ros_time_override(node_->get_clock()->get_clock_handle()), RCL_RET_OK);
    ASSERT_EQ(
      rcl_set_ros_time_override(node_->get_clock()->get_clock_handle(), 10000000000LL),
      RCL_RET_OK);
    PrecisionLandingTestPeer::hover(*node_);
  }
  void TearDown() override
  {
    node_.reset();
    context_->shutdown("precision test complete");
  }
  rclcpp::Context::SharedPtr context_;
  rclcpp::NodeOptions options_;
  std::shared_ptr<FlightController> node_;
};

TEST_F(PrecisionLanding, ParentReservationRejectsEveryExternalAction)
{
  ASSERT_EQ(
    PrecisionLandingTestPeer::admit(*node_),
    rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE);
  EXPECT_TRUE(PrecisionLandingTestPeer::externalRejected(*node_));
}

TEST_F(PrecisionLanding, HandoffAdmitsOnlyMatchingParentSession)
{
  ASSERT_EQ(
    PrecisionLandingTestPeer::admit(*node_),
    rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE);
  EXPECT_EQ(PrecisionLandingTestPeer::handoff(*node_, false), rclcpp_action::GoalResponse::REJECT);
  EXPECT_EQ(
    PrecisionLandingTestPeer::handoff(*node_, true, false),
    rclcpp_action::GoalResponse::REJECT);
  EXPECT_EQ(
    PrecisionLandingTestPeer::handoff(*node_, true),
    rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE);
}

TEST_F(PrecisionLanding, UnknownChildAdmissionPreservesParentLock)
{
  ASSERT_EQ(
    PrecisionLandingTestPeer::admit(*node_),
    rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE);
  PrecisionLandingTestPeer::unknown(*node_);
  EXPECT_TRUE(PrecisionLandingTestPeer::owned(*node_));
  EXPECT_TRUE(PrecisionLandingTestPeer::externalRejected(*node_));
}

TEST_F(PrecisionLanding, SourceAndSteadyEvidenceCannotBeBypassed)
{
  EXPECT_TRUE(PrecisionLandingTestPeer::target(*node_, 0));
  EXPECT_TRUE(PrecisionLandingTestPeer::target(*node_, 9));
  for (int scenario = 1; scenario <= 8; ++scenario) {
    EXPECT_FALSE(PrecisionLandingTestPeer::target(*node_, scenario)) << scenario;
  }
  EXPECT_FALSE(PrecisionLandingTestPeer::target(*node_, 10));
  EXPECT_FALSE(PrecisionLandingTestPeer::target(*node_, 11));
  EXPECT_TRUE(PrecisionLandingTestPeer::ingress(*node_, 50000000));
  EXPECT_FALSE(PrecisionLandingTestPeer::ingress(*node_, 250000000));
  EXPECT_FALSE(PrecisionLandingTestPeer::ingress(*node_, -1000000000));
  EXPECT_FALSE(PrecisionLandingTestPeer::ingress(*node_, -10000000000LL));
}

TEST_F(PrecisionLanding, WrongTagCannotReserveControl)
{
  EXPECT_EQ(PrecisionLandingTestPeer::admit(*node_, -1), rclcpp_action::GoalResponse::REJECT);
  EXPECT_EQ(PrecisionLandingTestPeer::admit(*node_, 8), rclcpp_action::GoalResponse::REJECT);
  EXPECT_FALSE(PrecisionLandingTestPeer::owned(*node_));
}

TEST_F(PrecisionLanding, HandoffNeedsDistinctPostDecisionModeSource)
{
  EXPECT_TRUE(PrecisionLandingTestPeer::modeGate(*node_, 0));
  for (int scenario = 1; scenario <= 9; ++scenario) {
    EXPECT_FALSE(PrecisionLandingTestPeer::modeGate(*node_, scenario)) << scenario;
  }
}

TEST_F(PrecisionLanding, ExternalModeIsNotHiddenByFreshOffboardAggregate)
{
  EXPECT_TRUE(PrecisionLandingTestPeer::externalModeBeforeAggregate(*node_));
}

TEST_F(PrecisionLanding, DefaultDisabledAndInvalidEnabledConfiguration)
{
  rclcpp::NodeOptions disabled;
  disabled.context(context_);
  auto default_node = std::make_shared<FlightController>(disabled);
  PrecisionLandingTestPeer::hover(*default_node);
  EXPECT_EQ(
    PrecisionLandingTestPeer::admit(*default_node),
    rclcpp_action::GoalResponse::REJECT);
  for (double bad_size : {0.0, -1.0, std::numeric_limits<double>::quiet_NaN()}) {
    auto parameters = options_.parameter_overrides();
    for (auto & parameter : parameters) {
      if (parameter.get_name() == "precision_tag_size_m") {
        parameter = rclcpp::Parameter("precision_tag_size_m", bad_size);
      }
    }
    rclcpp::NodeOptions invalid;
    invalid.context(context_).parameter_overrides(parameters);
    EXPECT_THROW(std::make_shared<FlightController>(invalid), std::invalid_argument);
  }
}

TEST_F(PrecisionLanding, ExplicitFiniteReadonlyFloorRequiredBelowHandoff)
{
  EXPECT_TRUE(node_->describe_parameter("precision_descent_floor_height").read_only);
  auto missing_parameters = options_.parameter_overrides();
  missing_parameters.erase(
    std::remove_if(
      missing_parameters.begin(), missing_parameters.end(),
      [](const auto & parameter) {
        return parameter.get_name() == "precision_descent_floor_height";
      }), missing_parameters.end());
  rclcpp::NodeOptions missing;
  missing.context(context_).parameter_overrides(missing_parameters);
  EXPECT_THROW(std::make_shared<FlightController>(missing), std::invalid_argument);
  for (double bad_floor : {0.0, 0.149, 0.3, 0.4,
      std::numeric_limits<double>::infinity(), std::numeric_limits<double>::quiet_NaN()})
  {
    auto parameters = options_.parameter_overrides();
    for (auto & parameter : parameters) {
      if (parameter.get_name() == "precision_descent_floor_height") {
        parameter = rclcpp::Parameter("precision_descent_floor_height", bad_floor);
      }
    }
    rclcpp::NodeOptions invalid;
    invalid.context(context_).parameter_overrides(parameters);
    EXPECT_THROW(std::make_shared<FlightController>(invalid), std::invalid_argument);
  }
}
}  // namespace easyfly_flight_control
