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
#include <atomic>
#include <future>
#include <thread>
#include <type_traits>
#include "easyfly_flight_control/flight_controller.hpp"

using namespace std::chrono_literals;

namespace easyfly_flight_control
{
class FlightSafetyTestPeer
{
public:
  static easyfly_msgs::srv::GetCapabilities::Response readiness(FlightController & node)
  {
    std::lock_guard<std::recursive_mutex> lock(node.flight_mtx_);
    return node.takeoff_readiness();
  }
  static void forgetState(FlightController & node)
  {
    std::lock_guard<std::recursive_mutex> flight_lock(node.flight_mtx_);
    std::lock_guard<std::mutex> lock(node.state_mtx_);
    node.uav_ = easyfly_msgs::msg::UAVState();
    node.state_received_ = false;
    node.state_sequence_ = 0;
    node.state_receipt_ = {};
  }
  static void faultLatch(FlightController & node) {node.command_uncertain_ = true;}
  static void prepare(FlightController & node, uint8_t mode = 7)
  {
    std::lock_guard<std::recursive_mutex> lock(node.flight_mtx_);
    node.timer_ctl_->cancel();
    node.active_ = FlightController::HOVER;
    node.action_reserved_ = false;
    state(node, true, true, -2.0);
    confirmMode(node, mode);
  }
  static void state(FlightController & node, bool connected, bool armed, double z)
  {
    std::lock_guard<std::recursive_mutex> flight_lock(node.flight_mtx_);
    auto msg = std::make_shared<easyfly_msgs::msg::UAVState>();
    msg->header.stamp = node.now();
    msg->connected = connected;
    msg->armed = armed;
    msg->pose_valid = msg->attitude_valid = true;
    msg->flight_mode = 7;
    msg->position_z = z;
    node.cb_uav_state(msg);
  }
  static void stale(FlightController & node)
  {
    std::lock_guard<std::recursive_mutex> flight_lock(node.flight_mtx_);
    std::lock_guard<std::mutex> lock(node.state_mtx_);
    node.state_receipt_ -= 2s;
  }
  static void confirmMode(FlightController & node, uint8_t mode)
  {
    std::lock_guard<std::recursive_mutex> flight_lock(node.flight_mtx_);
    std::lock_guard<std::mutex> lock(node.state_mtx_);
    node.uav_.flight_mode = mode;
  }
  static bool landing(FlightController & node)
  {
    std::lock_guard<std::recursive_mutex> lock(node.flight_mtx_);
    return node.active_ == FlightController::LANDING;
  }
  static void tick(FlightController & node) {node.control_loop();}
  static bool waitMode(FlightController & node, double timeout)
  {
    return node.wait_mode_engaged(3, timeout);
  }
  static bool arm(FlightController & node) {return node.call_arm(false);}
  static bool mode(FlightController & node) {return node.call_set_mode(3);}
  static bool modeReady(FlightController & node) {return node.cli_mode_->service_is_ready();}
  static size_t pendingModes(FlightController & node)
  {
    return node.cli_mode_->prune_pending_requests();
  }
  static size_t pendingArms(FlightController & node)
  {
    return node.cli_arm_->prune_pending_requests();
  }
  static bool commandMatched(FlightController & node)
  {
    return node.pub_uav_cmd_->get_subscription_count() > 0;
  }
  static void idle(FlightController & node, uint8_t mode = 3, double z = 0.0)
  {
    prepare(node, mode);
    std::lock_guard<std::recursive_mutex> lock(node.flight_mtx_);
    node.active_ = FlightController::NONE;
    state(node, true, false, z);
    confirmMode(node, mode);
  }
  static void refresh(FlightController & node)
  {
    std::lock_guard<std::recursive_mutex> flight_lock(node.flight_mtx_);
    auto msg = std::make_shared<easyfly_msgs::msg::UAVState>(node.get_uav());
    msg->header.stamp = node.now();
    node.cb_uav_state(msg);
  }
  static void invalid(FlightController & node)
  {
    std::lock_guard<std::recursive_mutex> flight_lock(node.flight_mtx_);
    auto msg = std::make_shared<easyfly_msgs::msg::UAVState>(node.get_uav());
    msg->header.stamp = node.now();
    msg->pose_valid = false;
    node.cb_uav_state(msg);
  }
  static void armed(FlightController & node, bool value)
  {
    std::lock_guard<std::recursive_mutex> flight_lock(node.flight_mtx_);
    auto msg = std::make_shared<easyfly_msgs::msg::UAVState>(node.get_uav());
    msg->header.stamp = node.now();
    msg->armed = value;
    node.cb_uav_state(msg);
  }
  static bool isIdle(FlightController & node)
  {
    std::lock_guard<std::recursive_mutex> lock(node.flight_mtx_);
    return node.active_ == FlightController::NONE && !node.action_reserved_;
  }
  static bool fault(FlightController & node) {return node.command_uncertain_;}
  static void command(FlightController & node)
  {
    auto msg = std::make_shared<quadrotor_msgs::msg::PositionCommand>();
    msg->header.stamp = node.now();
    msg->header.frame_id = "odom";
    msg->trajectory_id = 1;
    msg->trajectory_flag = quadrotor_msgs::msg::PositionCommand::TRAJECTORY_STATUS_READY;
    msg->position.z = 1.0;
    node.cb_position_cmd(msg);
  }
  static void finishOldTakeoff(
    FlightController & node,
    std::shared_ptr<rclcpp_action::ServerGoalHandle<FlightController::Takeoff>> goal)
  {
    node.finish_takeoff_goal(goal, "retired callback cleanup");
  }
  static bool owns(FlightController & node, const rclcpp_action::GoalUUID & uuid)
  {
    std::lock_guard<std::recursive_mutex> lock(node.flight_mtx_);
    return node.action_reserved_ && node.reserved_goal_id_ == uuid;
  }
  static void badStamp(FlightController & node, int scenario)
  {
    std::lock_guard<std::recursive_mutex> flight_lock(node.flight_mtx_);
    auto msg = std::make_shared<easyfly_msgs::msg::UAVState>(node.get_uav());
    msg->header.stamp = node.now();
    if (scenario == 0) {
      msg->header.stamp.sec = 0;
      msg->header.stamp.nanosec = 0;
    }
    if (scenario == 1) {msg->header.stamp.sec += 1;}
    if (scenario == 2) {msg->header.stamp.sec -= 2;}
    node.cb_uav_state(msg);
  }
  template<typename ActionT>
  static rclcpp_action::GoalResponse admit(
    FlightController & node,
    const rclcpp_action::GoalUUID & uuid, std::shared_ptr<const typename ActionT::Goal> goal)
  {
    if constexpr (std::is_same_v<ActionT, FlightController::Takeoff>) {
      return node.handle_takeoff_goal(uuid, goal);
    } else if constexpr (std::is_same_v<ActionT, FlightController::Land>) {
      return node.handle_land_goal(uuid, goal);
    } else if constexpr (std::is_same_v<ActionT, FlightController::GoToWaypoint>) {
      return node.handle_waypoint_goal(uuid, goal);
    } else {
      return node.handle_traj_goal(uuid, goal);
    }
  }
  template<typename ActionT>
  static void accept(
    FlightController & node,
    std::shared_ptr<rclcpp_action::ServerGoalHandle<ActionT>> goal)
  {
    if constexpr (std::is_same_v<ActionT, FlightController::Takeoff>) {
      node.handle_takeoff_accepted(goal);
    } else if constexpr (std::is_same_v<ActionT, FlightController::Land>) {
      node.handle_land_accepted(goal);
    } else if constexpr (std::is_same_v<ActionT, FlightController::GoToWaypoint>) {
      node.handle_waypoint_accepted(goal);
    } else {
      node.handle_traj_accepted(goal);
    }
  }
};

class FlightSafety : public ::testing::Test
{
protected:
  void SetUp() override
  {
    context_ = std::make_shared<rclcpp::Context>();
    context_->init(0, nullptr);
    rclcpp::NodeOptions options;
    options.context(context_).parameter_overrides(
      {
        rclcpp::Parameter("use_sim_time", true), rclcpp::Parameter("land_timeout", 0.08)});
    node_ = std::make_shared<FlightController>(options);
    ASSERT_EQ(rcl_enable_ros_time_override(node_->get_clock()->get_clock_handle()), RCL_RET_OK);
    ASSERT_EQ(
      rcl_set_ros_time_override(node_->get_clock()->get_clock_handle(), 10000000000LL),
      RCL_RET_OK);
    FlightSafetyTestPeer::prepare(*node_);
  }
  void TearDown() override
  {
    if (executor_) {executor_->cancel();}
    if (spin_.joinable()) {spin_.join();}
    if (context_->is_valid()) {context_->shutdown("test complete");}
  }
  void startGraph()
  {
    rclcpp::NodeOptions options;
    options.context(context_);
    peer_ = std::make_shared<rclcpp::Node>("flight_safety_peer", options);
    peer_group_ = peer_->create_callback_group(rclcpp::CallbackGroupType::Reentrant);
    mode_service_ = peer_->create_service<easyfly_msgs::srv::SetFlightMode>(
      "/set_flight_mode", [this](
        easyfly_msgs::srv::SetFlightMode::Request::SharedPtr request,
        easyfly_msgs::srv::SetFlightMode::Response::SharedPtr response) {
        ++mode_calls_;
        if (request->flight_mode == 3) {++offboard_calls_;}
        if (mode_hook_) {
          mode_hook_(request, response);
          return;
        }
        FlightSafetyTestPeer::confirmMode(*node_, request->flight_mode);
        response->success = true;
      }, rmw_qos_profile_services_default, peer_group_);
    arm_service_ = peer_->create_service<easyfly_msgs::srv::ArmMotors>(
      "/arm_motors", [this](easyfly_msgs::srv::ArmMotors::Request::SharedPtr request,
      easyfly_msgs::srv::ArmMotors::Response::SharedPtr response) {
        ++arm_calls_;
        if (!request->arm) {++disarm_calls_;}
        if (arm_hook_) {
          arm_hook_(request, response);
          return;
        }
        response->success = true;
      }, rmw_qos_profile_services_default, peer_group_);
    client_ = rclcpp_action::create_client<FlightController::Land>(peer_, "/land");
    heartbeat_ = peer_->create_wall_timer(
      20ms, [this]() {
        if (heartbeat_enabled_) {FlightSafetyTestPeer::refresh(*node_);}
      }, peer_group_);
    rclcpp::ExecutorOptions executor_options;
    executor_options.context = context_;
    executor_ = std::make_unique<rclcpp::executors::MultiThreadedExecutor>(executor_options, 6);
    executor_->add_node(node_);
    executor_->add_node(peer_);
    FlightSafetyTestPeer::confirmMode(*node_, 3);
    spin_ = std::thread([this]() {executor_->spin();});
    const auto spin_deadline = std::chrono::steady_clock::now() + 2s;
    while (!executor_->is_spinning() && std::chrono::steady_clock::now() < spin_deadline) {
      std::this_thread::sleep_for(1ms);
    }
    ASSERT_TRUE(executor_->is_spinning());
  }
  template<typename ActionT>
  void rejectBadEvidence(const std::string & name, const typename ActionT::Goal & goal)
  {
    auto client = rclcpp_action::create_client<ActionT>(peer_, name);
    ASSERT_TRUE(client->wait_for_action_server(2s));
    for (int scenario = 0; scenario < 4; ++scenario) {
      if constexpr (std::is_same_v<ActionT, FlightController::Takeoff>) {
        FlightSafetyTestPeer::idle(*node_);
      } else {
        FlightSafetyTestPeer::prepare(*node_, 3);
      }
      if (scenario == 3) {FlightSafetyTestPeer::stale(*node_);} else {
        FlightSafetyTestPeer::badStamp(*node_, scenario);
      }
      auto sent = client->async_send_goal(goal);
      ASSERT_EQ(sent.wait_for(2s), std::future_status::ready);
      EXPECT_EQ(sent.get(), nullptr);
    }
  }
  template<typename ActionT>
  void acceptedEvidenceRace(
    const std::string & name, const typename ActionT::Goal & goal,
    std::shared_ptr<rclcpp_action::ServerGoalHandle<ActionT>> * retired = nullptr)
  {
    auto accepted_handle = std::make_shared<std::promise<
          std::shared_ptr<rclcpp_action::ServerGoalHandle<ActionT>>>>();
    auto accepted_future = accepted_handle->get_future();
    if constexpr (std::is_same_v<ActionT, FlightController::Takeoff>) {
      FlightSafetyTestPeer::idle(*node_);
    } else {
      FlightSafetyTestPeer::prepare(*node_, 3);
    }
    auto server = rclcpp_action::create_server<ActionT>(
      peer_, name,
      [this](const rclcpp_action::GoalUUID & uuid,
      std::shared_ptr<const typename ActionT::Goal> request) {
        return FlightSafetyTestPeer::admit<ActionT>(*node_, uuid, request);
      }, [](auto) {return rclcpp_action::CancelResponse::REJECT;},
      [this, accepted_handle](std::shared_ptr<rclcpp_action::ServerGoalHandle<ActionT>> handle) {
        accepted_handle->set_value(handle);
        FlightSafetyTestPeer::invalid(*node_);
        FlightSafetyTestPeer::accept<ActionT>(*node_, handle);
      }, rcl_action_server_get_default_options(), peer_group_);
    auto client = rclcpp_action::create_client<ActionT>(peer_, name);
    ASSERT_TRUE(client->wait_for_action_server(2s));
    auto sent = client->async_send_goal(goal);
    ASSERT_EQ(sent.wait_for(2s), std::future_status::ready);
    auto handle = sent.get();
    ASSERT_NE(handle, nullptr);
    auto result = client->async_get_result(handle);
    ASSERT_EQ(result.wait_for(2s), std::future_status::ready);
    EXPECT_EQ(result.get().code, rclcpp_action::ResultCode::ABORTED);
    if (retired) {*retired = accepted_future.get();}
    EXPECT_TRUE(FlightSafetyTestPeer::isIdle(*node_));
    EXPECT_EQ(arm_calls_.load(), 0);
    EXPECT_EQ(mode_calls_.load(), 0);
  }
  template<typename ActionT>
  void rejectFreshFault(const std::string & name, const typename ActionT::Goal & goal)
  {
    if constexpr (std::is_same_v<ActionT, FlightController::Takeoff>) {
      FlightSafetyTestPeer::idle(*node_);
    } else {
      FlightSafetyTestPeer::prepare(*node_, 3);
    }
    auto client = rclcpp_action::create_client<ActionT>(peer_, name);
    ASSERT_TRUE(client->wait_for_action_server(2s));
    auto sent = client->async_send_goal(goal);
    ASSERT_EQ(sent.wait_for(2s), std::future_status::ready);
    EXPECT_EQ(sent.get(), nullptr);
  }
  void unknownCancellation(bool arming)
  {
    auto replied = std::make_shared<std::atomic<bool>>(false);
    if (arming) {
      arm_hook_ = [this, replied](auto, auto response) {
          FlightSafetyTestPeer::armed(*node_, true);
          std::this_thread::sleep_for(6s);
          response->success = true;
          *replied = true;
        };
    } else {
      mode_hook_ = [this, replied](auto request, auto response) {
          FlightSafetyTestPeer::confirmMode(*node_, request->flight_mode);
          std::this_thread::sleep_for(6s);
          response->success = true;
          *replied = true;
        };
    }
    startGraph();
    FlightSafetyTestPeer::idle(*node_, arming ? 3 : 2);
    auto received = std::make_shared<std::atomic<int>>(0);
    rclcpp::SubscriptionOptions options;
    options.callback_group = peer_group_;
    auto commands = peer_->create_subscription<easyfly_msgs::msg::UAVCommand>(
      "/uav_command", 10,
      [received](easyfly_msgs::msg::UAVCommand::SharedPtr) {++*received;}, options);
    auto deadline = std::chrono::steady_clock::now() + 2s;
    while (!FlightSafetyTestPeer::commandMatched(*node_) &&
      std::chrono::steady_clock::now() < deadline)
    {
      std::this_thread::sleep_for(5ms);
    }
    ASSERT_TRUE(FlightSafetyTestPeer::commandMatched(*node_));
    auto client = rclcpp_action::create_client<FlightController::Takeoff>(peer_, "/takeoff");
    ASSERT_TRUE(client->wait_for_action_server(2s));
    FlightController::Takeoff::Goal goal;
    goal.target_altitude = 1.0;
    auto sent = client->async_send_goal(goal);
    ASSERT_EQ(sent.wait_for(2s), std::future_status::ready);
    auto handle = sent.get();
    ASSERT_NE(handle, nullptr);
    auto result = client->async_get_result(handle);
    deadline = std::chrono::steady_clock::now() + 3s;
    while ((arming ? arm_calls_.load() : mode_calls_.load()) == 0 &&
      std::chrono::steady_clock::now() < deadline)
    {
      std::this_thread::sleep_for(5ms);
    }
    ASSERT_EQ(arming ? arm_calls_.load() : mode_calls_.load(), 1);
    ASSERT_GE(received->load(), 1);
    auto cancel = client->async_cancel_goal(handle);
    ASSERT_EQ(cancel.wait_for(500ms), std::future_status::ready);
    ASSERT_EQ(cancel.get()->goals_canceling.size(), 1U);
    EXPECT_EQ(cancel.get()->goals_canceling.front().goal_id.uuid, handle->get_goal_id());
    EXPECT_TRUE(FlightSafetyTestPeer::owns(*node_, handle->get_goal_id()));
    EXPECT_FALSE(FlightSafetyTestPeer::fault(*node_));
    EXPECT_EQ(result.wait_for(100ms), std::future_status::timeout);
    const auto baseline = received->load();
    for (int tick = 0; tick < 8; ++tick) {
      FlightSafetyTestPeer::tick(*node_);
      std::this_thread::sleep_for(20ms);
    }
    EXPECT_EQ(received->load(), baseline);
    ASSERT_EQ(result.wait_for(6s), std::future_status::ready);
    EXPECT_EQ(result.get().code, rclcpp_action::ResultCode::CANCELED);
    EXPECT_FALSE(result.get().result->success);
    EXPECT_EQ(
      result.get().result->message,
      "command_result_unknown: flight fault latch set; manual audit required");
    EXPECT_TRUE(FlightSafetyTestPeer::fault(*node_));
    EXPECT_TRUE(FlightSafetyTestPeer::isIdle(*node_));
    EXPECT_EQ(FlightSafetyTestPeer::pendingModes(*node_), 0U);
    EXPECT_EQ(FlightSafetyTestPeer::pendingArms(*node_), 0U);
    deadline = std::chrono::steady_clock::now() + 2s;
    while (!*replied && std::chrono::steady_clock::now() < deadline) {
      std::this_thread::sleep_for(5ms);
    }
    ASSERT_TRUE(*replied);
    EXPECT_TRUE(FlightSafetyTestPeer::fault(*node_));
    rejectFreshFault<FlightController::Takeoff>("/takeoff", goal);
    EXPECT_EQ(mode_calls_.load(), arming ? 0 : 1);
    EXPECT_EQ(arm_calls_.load(), arming ? 1 : 0);
    EXPECT_EQ(disarm_calls_.load(), 0);
  }
  std::shared_ptr<rclcpp::Context> context_;
  std::shared_ptr<FlightController> node_;
  std::shared_ptr<rclcpp::Node> peer_;
  rclcpp::Service<easyfly_msgs::srv::SetFlightMode>::SharedPtr mode_service_;
  rclcpp::Service<easyfly_msgs::srv::ArmMotors>::SharedPtr arm_service_;
  rclcpp::CallbackGroup::SharedPtr peer_group_;
  rclcpp::TimerBase::SharedPtr heartbeat_;
  std::atomic<bool> heartbeat_enabled_{true};
  std::function<void(easyfly_msgs::srv::ArmMotors::Request::SharedPtr,
    easyfly_msgs::srv::ArmMotors::Response::SharedPtr)> arm_hook_;
  std::function<void(easyfly_msgs::srv::SetFlightMode::Request::SharedPtr,
    easyfly_msgs::srv::SetFlightMode::Response::SharedPtr)> mode_hook_;
  rclcpp_action::Client<FlightController::Land>::SharedPtr client_;
  std::unique_ptr<rclcpp::executors::MultiThreadedExecutor> executor_;
  std::thread spin_;
  std::atomic<int> arm_calls_{0}, mode_calls_{0};
  std::atomic<int> offboard_calls_{0}, disarm_calls_{0};
};

TEST_F(FlightSafety, FrozenPositiveRosTimeModeMismatchHasSteadyDeadline)
{
  const auto start = std::chrono::steady_clock::now();
  EXPECT_FALSE(FlightSafetyTestPeer::waitMode(*node_, 0.15));
  const auto elapsed = std::chrono::steady_clock::now() - start;
  EXPECT_GE(elapsed, 150ms);
  EXPECT_LT(elapsed, 600ms);
  EXPECT_EQ(node_->now().nanoseconds(), 10000000000LL);
}

TEST_F(FlightSafety, ContextShutdownStopsWaitAndBlocksFurtherServices)
{
  auto waiting = std::async(
    std::launch::async, [this]() {
      return FlightSafetyTestPeer::waitMode(*node_, 30.0);
    });
  std::this_thread::sleep_for(60ms);
  context_->shutdown("shutdown during mode confirmation");
  ASSERT_EQ(waiting.wait_for(500ms), std::future_status::ready);
  EXPECT_FALSE(waiting.get());
  const auto start = std::chrono::steady_clock::now();
  EXPECT_FALSE(FlightSafetyTestPeer::arm(*node_));
  EXPECT_FALSE(FlightSafetyTestPeer::mode(*node_));
  EXPECT_LT(std::chrono::steady_clock::now() - start, 100ms);
}

TEST_F(FlightSafety, ShutdownClearsUnansweredModeServiceRequest)
{
  startGraph();
  const auto discovery_deadline = std::chrono::steady_clock::now() + 2s;
  while (!FlightSafetyTestPeer::modeReady(*node_) &&
    std::chrono::steady_clock::now() < discovery_deadline) {std::this_thread::sleep_for(5ms);}
  ASSERT_TRUE(FlightSafetyTestPeer::modeReady(*node_));
  // Stop execution, not the context: the discovered server remains available
  // but cannot answer. This exercises shutdown while a request is pending.
  executor_->cancel();
  spin_.join();
  auto waiting = std::async(
    std::launch::async, [this]() {
      return FlightSafetyTestPeer::mode(*node_);
    });
  EXPECT_EQ(waiting.wait_for(100ms), std::future_status::timeout);
  context_->shutdown("unanswered service shutdown");
  ASSERT_EQ(waiting.wait_for(500ms), std::future_status::ready);
  EXPECT_FALSE(waiting.get());
  EXPECT_EQ(FlightSafetyTestPeer::pendingModes(*node_), 0U);
}

TEST_F(FlightSafety, LiveContextUnansweredServiceHasSteadyTimeoutAndClearsPending)
{
  startGraph();
  const auto discovery_deadline = std::chrono::steady_clock::now() + 2s;
  while (!FlightSafetyTestPeer::modeReady(*node_) &&
    std::chrono::steady_clock::now() < discovery_deadline) {std::this_thread::sleep_for(5ms);}
  ASSERT_TRUE(FlightSafetyTestPeer::modeReady(*node_));
  executor_->cancel();
  spin_.join();
  // Keep the context valid and ROS time frozen. The discovered service cannot
  // answer without an executor, so only the steady response deadline can end it.
  const auto start = std::chrono::steady_clock::now();
  EXPECT_FALSE(FlightSafetyTestPeer::mode(*node_));
  const auto elapsed = std::chrono::steady_clock::now() - start;
  EXPECT_GE(elapsed, 5s);
  EXPECT_LT(elapsed, 6s);
  EXPECT_TRUE(context_->is_valid());
  EXPECT_EQ(node_->now().nanoseconds(), 10000000000LL);
  EXPECT_EQ(FlightSafetyTestPeer::pendingModes(*node_), 0U);
}

TEST_F(FlightSafety, LandRequiresFreshConnectedDisarmAndNeverDisarmsFromLocalZ)
{
  startGraph();
  ASSERT_TRUE(client_->wait_for_action_server(2s));
  heartbeat_enabled_ = false;
  // Armed negative Z, armed low positive Z, stale false, disconnected false,
  // and fresh connected false each traverse the real Land action result path.
  for (int scenario = 0; scenario < 5; ++scenario) {
    FlightSafetyTestPeer::prepare(*node_, 3);
    auto sent = client_->async_send_goal(FlightController::Land::Goal{});
    ASSERT_EQ(sent.wait_for(2s), std::future_status::ready);
    auto goal = sent.get();
    ASSERT_NE(goal, nullptr);
    const auto deadline = std::chrono::steady_clock::now() + 2s;
    while (!FlightSafetyTestPeer::landing(*node_) &&
      std::chrono::steady_clock::now() < deadline) {std::this_thread::sleep_for(5ms);}
    ASSERT_TRUE(FlightSafetyTestPeer::landing(*node_));
    auto result = client_->async_get_result(goal);
    const bool armed = scenario < 2;
    FlightSafetyTestPeer::state(*node_, scenario != 3, armed, scenario == 1 ? 0.1 : -2.0);
    if (scenario == 2) {FlightSafetyTestPeer::stale(*node_);}
    FlightSafetyTestPeer::tick(*node_);
    if (scenario < 2) {
      EXPECT_EQ(result.wait_for(20ms), std::future_status::timeout);
      std::this_thread::sleep_for(100ms);
      // Refresh armed feedback: failure must not depend on stale telemetry.
      if (armed) {FlightSafetyTestPeer::state(*node_, true, true, scenario == 1 ? 0.1 : -2.0);}
      FlightSafetyTestPeer::tick(*node_);
    }
    ASSERT_EQ(result.wait_for(2s), std::future_status::ready);
    const auto terminal = result.get();
    EXPECT_EQ(
      terminal.code, scenario == 4 ? rclcpp_action::ResultCode::SUCCEEDED :
      rclcpp_action::ResultCode::ABORTED);
    EXPECT_EQ(terminal.result->success, scenario == 4);
    EXPECT_EQ(arm_calls_.load(), 0);
    EXPECT_EQ(mode_calls_.load(), scenario + 1);
  }
}

TEST_F(FlightSafety, ConfirmedCancelTakesPriorityOverExpiredLandDeadline)
{
  startGraph();
  ASSERT_TRUE(client_->wait_for_action_server(2s));
  auto sent = client_->async_send_goal(FlightController::Land::Goal{});
  ASSERT_EQ(sent.wait_for(2s), std::future_status::ready);
  auto goal = sent.get();
  ASSERT_NE(goal, nullptr);
  const auto deadline = std::chrono::steady_clock::now() + 2s;
  while (!FlightSafetyTestPeer::landing(*node_) &&
    std::chrono::steady_clock::now() < deadline) {std::this_thread::sleep_for(5ms);}
  ASSERT_TRUE(FlightSafetyTestPeer::landing(*node_));
  auto result = client_->async_get_result(goal);
  std::this_thread::sleep_for(100ms);
  auto canceled = client_->async_cancel_goal(goal);
  ASSERT_EQ(canceled.wait_for(2s), std::future_status::ready);
  ASSERT_EQ(canceled.get()->goals_canceling.size(), 1U);
  FlightSafetyTestPeer::tick(*node_);
  ASSERT_EQ(result.wait_for(2s), std::future_status::ready);
  EXPECT_EQ(result.get().code, rclcpp_action::ResultCode::CANCELED);
  EXPECT_EQ(arm_calls_.load(), 0);
}
TEST_F(FlightSafety, FourActionsRejectStaleZeroFutureAndOldStateEvidence)
{
  startGraph();
  heartbeat_enabled_ = false;
  FlightController::Takeoff::Goal takeoff;
  takeoff.target_altitude = 1.0;
  rejectBadEvidence<FlightController::Takeoff>("/takeoff", takeoff);
  rejectBadEvidence<FlightController::Land>("/land", FlightController::Land::Goal{});
  FlightController::GoToWaypoint::Goal waypoint;
  waypoint.target_z = 1.0;
  rejectBadEvidence<FlightController::GoToWaypoint>("/goto_waypoint", waypoint);
  FlightController::FollowTrajectory::Goal trajectory;
  trajectory.target_z = 1.0;
  rejectBadEvidence<FlightController::FollowTrajectory>("/follow_trajectory", trajectory);
}

TEST_F(FlightSafety, FourAcceptedCallbacksRecheckEvidenceBeforeSideEffects)
{
  startGraph();
  heartbeat_enabled_ = false;
  FlightController::Takeoff::Goal takeoff;
  takeoff.target_altitude = 1.0;
  acceptedEvidenceRace<FlightController::Takeoff>("/accept_race_takeoff", takeoff);
  acceptedEvidenceRace<FlightController::Land>("/accept_race_land", FlightController::Land::Goal{});
  FlightController::GoToWaypoint::Goal waypoint;
  waypoint.target_z = 1.0;
  acceptedEvidenceRace<FlightController::GoToWaypoint>("/accept_race_waypoint", waypoint);
  FlightController::FollowTrajectory::Goal trajectory;
  trajectory.target_z = 1.0;
  acceptedEvidenceRace<FlightController::FollowTrajectory>("/accept_race_trajectory", trajectory);
}

TEST_F(FlightSafety, StaleMatchingModeIsNotConfirmation)
{
  FlightSafetyTestPeer::confirmMode(*node_, 3);
  FlightSafetyTestPeer::stale(*node_);
  EXPECT_FALSE(FlightSafetyTestPeer::waitMode(*node_, 0.15));
  FlightSafetyTestPeer::refresh(*node_);
  EXPECT_TRUE(FlightSafetyTestPeer::waitMode(*node_, 0.15));
}

TEST_F(FlightSafety, RepeatedTargetObservationCannotCompleteWaypointOrTrajectory)
{
  startGraph();
  heartbeat_enabled_ = false;
  FlightSafetyTestPeer::prepare(*node_, 3);
  FlightSafetyTestPeer::state(*node_, true, true, 1.0);
  FlightSafetyTestPeer::confirmMode(*node_, 3);
  auto waypoint = rclcpp_action::create_client<FlightController::GoToWaypoint>(
    peer_,
    "/goto_waypoint");
  ASSERT_TRUE(waypoint->wait_for_action_server(2s));
  FlightController::GoToWaypoint::Goal goal;
  goal.target_z = 1.0;
  auto sent = waypoint->async_send_goal(goal);
  ASSERT_EQ(sent.wait_for(2s), std::future_status::ready);
  ASSERT_NE(sent.get(), nullptr);
  auto result = waypoint->async_get_result(sent.get());
  for (int i = 0; i < 8; ++i) {
    FlightSafetyTestPeer::tick(*node_);
  }
  EXPECT_EQ(result.wait_for(20ms), std::future_status::timeout);
  for (int i = 0; i < 5; ++i) {
    FlightSafetyTestPeer::refresh(*node_);
    FlightSafetyTestPeer::tick(*node_);
  }
  ASSERT_EQ(result.wait_for(2s), std::future_status::ready);
  EXPECT_EQ(result.get().code, rclcpp_action::ResultCode::SUCCEEDED);

  auto trajectory = rclcpp_action::create_client<FlightController::FollowTrajectory>(
    peer_, "/follow_trajectory");
  ASSERT_TRUE(trajectory->wait_for_action_server(2s));
  FlightController::FollowTrajectory::Goal trajectory_goal;
  trajectory_goal.target_z = 1.0;
  auto sent_trajectory = trajectory->async_send_goal(trajectory_goal);
  ASSERT_EQ(sent_trajectory.wait_for(2s), std::future_status::ready);
  ASSERT_NE(sent_trajectory.get(), nullptr);
  auto trajectory_result = trajectory->async_get_result(sent_trajectory.get());
  FlightSafetyTestPeer::command(*node_);
  for (int i = 0; i < 8; ++i) {
    FlightSafetyTestPeer::tick(*node_);
  }
  EXPECT_EQ(trajectory_result.wait_for(20ms), std::future_status::timeout);
  for (int i = 0; i < 5; ++i) {
    FlightSafetyTestPeer::refresh(*node_);
    FlightSafetyTestPeer::tick(*node_);
  }
  ASSERT_EQ(trajectory_result.wait_for(2s), std::future_status::ready);
  EXPECT_EQ(trajectory_result.get().code, rclcpp_action::ResultCode::SUCCEEDED);
}

TEST_F(FlightSafety, DelayedArmTakeoverDrainsBeforeReleasingSlotWithoutDisarm)
{
  std::atomic<bool> response_sent{false};
  arm_hook_ = [&response_sent](auto, auto response) {
      std::this_thread::sleep_for(600ms);
      response->success = true;
      response_sent = true;
    };
  startGraph();
  FlightSafetyTestPeer::idle(*node_, 3, -2.0);
  auto client = rclcpp_action::create_client<FlightController::Takeoff>(peer_, "/takeoff");
  ASSERT_TRUE(client->wait_for_action_server(2s));
  FlightController::Takeoff::Goal goal;
  goal.target_altitude = 1.0;
  auto sent = client->async_send_goal(goal);
  ASSERT_EQ(sent.wait_for(2s), std::future_status::ready);
  ASSERT_NE(sent.get(), nullptr);
  auto result = client->async_get_result(sent.get());
  const auto deadline = std::chrono::steady_clock::now() + 2s;
  while (arm_calls_ == 0 && std::chrono::steady_clock::now() < deadline) {
    std::this_thread::sleep_for(5ms);
  }
  ASSERT_EQ(arm_calls_.load(), 1);
  FlightSafetyTestPeer::armed(*node_, true);
  FlightSafetyTestPeer::confirmMode(*node_, 6);
  FlightSafetyTestPeer::tick(*node_);
  EXPECT_EQ(result.wait_for(50ms), std::future_status::timeout);
  auto competing = client->async_send_goal(goal);
  ASSERT_EQ(competing.wait_for(1s), std::future_status::ready);
  EXPECT_EQ(competing.get(), nullptr);
  ASSERT_EQ(result.wait_for(2s), std::future_status::ready);
  EXPECT_TRUE(response_sent);
  EXPECT_EQ(result.get().code, rclcpp_action::ResultCode::ABORTED);
  EXPECT_TRUE(FlightSafetyTestPeer::isIdle(*node_));
  EXPECT_EQ(disarm_calls_.load(), 0);
  EXPECT_EQ(offboard_calls_.load(), 0);
}

TEST_F(FlightSafety, DelayedArmCancellationStopsStreamAndWaitsForLocalTransactionDrain)
{
  std::atomic<bool> response_sent{false};
  arm_hook_ = [&response_sent](auto, auto response) {
      std::this_thread::sleep_for(600ms);
      response->success = true;
      response_sent = true;
    };
  startGraph();
  FlightSafetyTestPeer::idle(*node_);
  auto client = rclcpp_action::create_client<FlightController::Takeoff>(peer_, "/takeoff");
  ASSERT_TRUE(client->wait_for_action_server(2s));
  FlightController::Takeoff::Goal goal;
  goal.target_altitude = 1.0;
  auto sent = client->async_send_goal(goal);
  ASSERT_EQ(sent.wait_for(2s), std::future_status::ready);
  ASSERT_NE(sent.get(), nullptr);
  auto result = client->async_get_result(sent.get());
  const auto deadline = std::chrono::steady_clock::now() + 2s;
  while (arm_calls_ == 0 && std::chrono::steady_clock::now() < deadline) {
    std::this_thread::sleep_for(5ms);
  }
  ASSERT_EQ(arm_calls_.load(), 1);
  auto cancel = client->async_cancel_goal(sent.get());
  ASSERT_EQ(cancel.wait_for(500ms), std::future_status::ready);
  ASSERT_EQ(cancel.get()->goals_canceling.size(), 1U);
  FlightSafetyTestPeer::tick(*node_);
  EXPECT_EQ(result.wait_for(50ms), std::future_status::timeout);
  auto competing = client->async_send_goal(goal);
  ASSERT_EQ(competing.wait_for(500ms), std::future_status::ready);
  EXPECT_EQ(competing.get(), nullptr);
  ASSERT_EQ(result.wait_for(2s), std::future_status::ready);
  EXPECT_TRUE(response_sent);
  EXPECT_EQ(result.get().code, rclcpp_action::ResultCode::CANCELED);
  EXPECT_TRUE(FlightSafetyTestPeer::isIdle(*node_));
  EXPECT_EQ(disarm_calls_.load(), 0);
}

TEST_F(FlightSafety, UnknownArmCancellationDrainsThenRetainsFaultAfterLateReply)
{
  unknownCancellation(true);
}

TEST_F(FlightSafety, UnknownModeCancellationNeverArmsAndRetainsFaultAfterLateReply)
{
  unknownCancellation(false);
}

TEST_F(FlightSafety, FailedModeConfirmationNeverArmsOrDisarmsFromLowLocalZ)
{
  mode_hook_ = [this](auto, auto response) {
      // Fresh armed telemetry in the non-OFFBOARD baseline must not be treated
      // as proof that a low/negative local Z makes automatic disarm safe.
      FlightSafetyTestPeer::armed(*node_, true);
      response->success = true;
    };
  startGraph();
  auto client = rclcpp_action::create_client<FlightController::Takeoff>(peer_, "/takeoff");
  ASSERT_TRUE(client->wait_for_action_server(2s));
  for (double z : {-2.0, 0.1}) {
    FlightSafetyTestPeer::idle(*node_, 2, z);
    FlightController::Takeoff::Goal goal;
    goal.target_altitude = 1.0;
    auto sent = client->async_send_goal(goal);
    ASSERT_EQ(sent.wait_for(2s), std::future_status::ready);
    ASSERT_NE(sent.get(), nullptr);
    auto result = client->async_get_result(sent.get());
    ASSERT_EQ(result.wait_for(5s), std::future_status::ready);
    EXPECT_EQ(result.get().code, rclcpp_action::ResultCode::ABORTED);
    EXPECT_EQ(arm_calls_.load(), 0);
  }
}

TEST_F(FlightSafety, LandExternalTakeoverAndCancellationWindowNeverRequestOffboard)
{
  startGraph();
  ASSERT_TRUE(client_->wait_for_action_server(2s));
  for (int scenario = 0; scenario < 4; ++scenario) {
    FlightSafetyTestPeer::prepare(*node_, 3);
    auto sent = client_->async_send_goal(FlightController::Land::Goal{});
    ASSERT_EQ(sent.wait_for(2s), std::future_status::ready);
    ASSERT_NE(sent.get(), nullptr);
    const auto deadline = std::chrono::steady_clock::now() + 2s;
    while (!FlightSafetyTestPeer::landing(*node_) && std::chrono::steady_clock::now() < deadline) {
      std::this_thread::sleep_for(5ms);
    }
    ASSERT_TRUE(FlightSafetyTestPeer::landing(*node_));
    auto result = client_->async_get_result(sent.get());
    if (scenario < 2) {
      FlightSafetyTestPeer::confirmMode(*node_, scenario == 0 ? 6 : 0);
      auto cancel = client_->async_cancel_goal(sent.get());
      ASSERT_EQ(cancel.wait_for(1s), std::future_status::ready);
      EXPECT_TRUE(cancel.get()->goals_canceling.empty());
      FlightSafetyTestPeer::tick(*node_);
    } else {
      auto cancel = client_->async_cancel_goal(sent.get());
      std::this_thread::sleep_for(100ms);
      FlightSafetyTestPeer::confirmMode(*node_, scenario == 2 ? 6 : 0);
      FlightSafetyTestPeer::tick(*node_);
      ASSERT_EQ(cancel.wait_for(1s), std::future_status::ready);
      EXPECT_TRUE(cancel.get()->goals_canceling.empty());
    }
    ASSERT_EQ(result.wait_for(2s), std::future_status::ready);
    EXPECT_EQ(result.get().code, rclcpp_action::ResultCode::ABORTED);
    EXPECT_TRUE(FlightSafetyTestPeer::isIdle(*node_));
    EXPECT_EQ(offboard_calls_.load(), 0);
    EXPECT_EQ(disarm_calls_.load(), 0);
  }
}
TEST_F(FlightSafety, DelayedModeResponseAfterTimeoutLatchesFaultAndRejectsAllFreshActions)
{
  std::atomic<bool> late_response{false};
  mode_hook_ = [this, &late_response](auto request, auto response) {
      std::this_thread::sleep_for(6s);
      FlightSafetyTestPeer::confirmMode(*node_, request->flight_mode);
      response->success = true;
      late_response = true;
    };
  startGraph();
  FlightSafetyTestPeer::idle(*node_, 2);
  auto takeoff = rclcpp_action::create_client<FlightController::Takeoff>(peer_, "/takeoff");
  ASSERT_TRUE(takeoff->wait_for_action_server(2s));
  FlightController::Takeoff::Goal goal;
  goal.target_altitude = 1.0;
  auto sent = takeoff->async_send_goal(goal);
  ASSERT_EQ(sent.wait_for(2s), std::future_status::ready);
  ASSERT_NE(sent.get(), nullptr);
  auto result = takeoff->async_get_result(sent.get());
  ASSERT_EQ(result.wait_for(7s), std::future_status::ready);
  EXPECT_EQ(result.get().code, rclcpp_action::ResultCode::ABORTED);
  EXPECT_EQ(result.get().result->message.rfind("command_result_unknown:", 0), 0U);
  EXPECT_TRUE(FlightSafetyTestPeer::fault(*node_));
  EXPECT_EQ(FlightSafetyTestPeer::pendingModes(*node_), 0U);
  const auto deadline = std::chrono::steady_clock::now() + 2s;
  while (!late_response && std::chrono::steady_clock::now() < deadline) {
    std::this_thread::sleep_for(5ms);
  }
  ASSERT_TRUE(late_response);
  EXPECT_TRUE(FlightSafetyTestPeer::fault(*node_));
  rejectFreshFault<FlightController::Takeoff>("/takeoff", goal);
  rejectFreshFault<FlightController::Land>("/land", FlightController::Land::Goal{});
  FlightController::GoToWaypoint::Goal waypoint;
  waypoint.target_z = 1.0;
  rejectFreshFault<FlightController::GoToWaypoint>("/goto_waypoint", waypoint);
  FlightController::FollowTrajectory::Goal trajectory;
  trajectory.target_z = 1.0;
  rejectFreshFault<FlightController::FollowTrajectory>("/follow_trajectory", trajectory);
  EXPECT_EQ(arm_calls_.load(), 0);
  EXPECT_EQ(mode_calls_.load(), 1);
}

TEST_F(FlightSafety, BridgeUnknownResultPrefixLatchesFaultButExplicitRejectionDoesNot)
{
  std::atomic<bool> unknown{false};
  mode_hook_ = [&unknown](auto, auto response) {
      response->success = false;
      response->message =
        unknown ? "command_result_unknown: upstream timed out" : "explicitly rejected";
    };
  startGraph();
  FlightSafetyTestPeer::idle(*node_, 2);
  auto takeoff = rclcpp_action::create_client<FlightController::Takeoff>(peer_, "/takeoff");
  ASSERT_TRUE(takeoff->wait_for_action_server(2s));
  FlightController::Takeoff::Goal goal;
  goal.target_altitude = 1.0;
  auto sent = takeoff->async_send_goal(goal);
  ASSERT_EQ(sent.wait_for(2s), std::future_status::ready);
  ASSERT_NE(sent.get(), nullptr);
  auto result = takeoff->async_get_result(sent.get());
  ASSERT_EQ(result.wait_for(2s), std::future_status::ready);
  EXPECT_EQ(result.get().code, rclcpp_action::ResultCode::ABORTED);
  EXPECT_FALSE(FlightSafetyTestPeer::fault(*node_));
  unknown = true;
  FlightSafetyTestPeer::idle(*node_, 2);
  sent = takeoff->async_send_goal(goal);
  ASSERT_EQ(sent.wait_for(2s), std::future_status::ready);
  ASSERT_NE(sent.get(), nullptr);
  result = takeoff->async_get_result(sent.get());
  ASSERT_EQ(result.wait_for(2s), std::future_status::ready);
  EXPECT_EQ(result.get().code, rclcpp_action::ResultCode::ABORTED);
  EXPECT_TRUE(FlightSafetyTestPeer::fault(*node_));
  EXPECT_EQ(arm_calls_.load(), 0);
}

TEST_F(FlightSafety, LandUnknownResultIsNotReportedAsKnownModeFailure)
{
  std::atomic<bool> unknown{false};
  mode_hook_ = [this, &unknown](auto request, auto response) {
      if (unknown) {FlightSafetyTestPeer::confirmMode(*node_, request->flight_mode);}
      response->success = false;
      response->message = unknown ?
        "command_result_unknown: upstream reply lost" : "explicitly rejected";
    };
  startGraph();
  ASSERT_TRUE(client_->wait_for_action_server(2s));
  for (bool fault : {false, true}) {
    unknown = fault;
    FlightSafetyTestPeer::prepare(*node_, 3);
    auto sent = client_->async_send_goal(FlightController::Land::Goal{});
    ASSERT_EQ(sent.wait_for(2s), std::future_status::ready);
    ASSERT_NE(sent.get(), nullptr);
    auto result = client_->async_get_result(sent.get());
    ASSERT_EQ(result.wait_for(2s), std::future_status::ready);
    EXPECT_EQ(result.get().code, rclcpp_action::ResultCode::ABORTED);
    EXPECT_FALSE(result.get().result->success);
    EXPECT_EQ(FlightSafetyTestPeer::fault(*node_), fault);
    EXPECT_EQ(
      result.get().result->message,
      fault ? "command_result_unknown: flight fault latch set; manual audit required" :
      "AUTO.LAND not engaged");
  }
  EXPECT_EQ(mode_calls_.load(), 2);
  EXPECT_EQ(offboard_calls_.load(), 0);
  EXPECT_EQ(arm_calls_.load(), 0);
}

TEST_F(FlightSafety, LandDisarmCanCompleteWithoutPoseButNotWithoutTrustedStamp)
{
  startGraph();
  heartbeat_enabled_ = false;
  ASSERT_TRUE(client_->wait_for_action_server(2s));
  for (int scenario = 0; scenario < 4; ++scenario) {
    FlightSafetyTestPeer::prepare(*node_, 3);
    auto sent = client_->async_send_goal(FlightController::Land::Goal{});
    ASSERT_EQ(sent.wait_for(2s), std::future_status::ready);
    ASSERT_NE(sent.get(), nullptr);
    const auto deadline = std::chrono::steady_clock::now() + 2s;
    while (!FlightSafetyTestPeer::landing(*node_) && std::chrono::steady_clock::now() < deadline) {
      std::this_thread::sleep_for(5ms);
    }
    ASSERT_TRUE(FlightSafetyTestPeer::landing(*node_));
    auto result = client_->async_get_result(sent.get());
    FlightSafetyTestPeer::armed(*node_, false);
    FlightSafetyTestPeer::invalid(*node_);
    if (scenario > 0) {FlightSafetyTestPeer::badStamp(*node_, scenario - 1);}
    FlightSafetyTestPeer::tick(*node_);
    ASSERT_EQ(result.wait_for(2s), std::future_status::ready);
    EXPECT_EQ(
      result.get().code, scenario == 0 ? rclcpp_action::ResultCode::SUCCEEDED :
      rclcpp_action::ResultCode::ABORTED);
    EXPECT_EQ(disarm_calls_.load(), 0);
  }
}
TEST_F(FlightSafety, UnrecognizedTakeoffBaselineModesAreRejected)
{
  startGraph();
  auto client = rclcpp_action::create_client<FlightController::Takeoff>(peer_, "/takeoff");
  ASSERT_TRUE(client->wait_for_action_server(2s));
  FlightController::Takeoff::Goal goal;
  goal.target_altitude = 1.0;
  for (uint8_t mode : {8, 99, 255}) {
    FlightSafetyTestPeer::idle(*node_, mode);
    auto sent = client->async_send_goal(goal);
    ASSERT_EQ(sent.wait_for(2s), std::future_status::ready);
    EXPECT_EQ(sent.get(), nullptr);
  }
  EXPECT_EQ(mode_calls_.load(), 0);
  EXPECT_EQ(arm_calls_.load(), 0);
}

TEST_F(FlightSafety, InitialManualAndResidualLandCanStartOnlyAfterFreshOffboardAndArmedFeedback)
{
  arm_hook_ = [this](auto request, auto response) {
      FlightSafetyTestPeer::armed(*node_, request->arm);
      response->success = true;
    };
  startGraph();
  auto client = rclcpp_action::create_client<FlightController::Takeoff>(peer_, "/takeoff");
  ASSERT_TRUE(client->wait_for_action_server(2s));
  FlightController::Takeoff::Goal goal;
  goal.target_altitude = 1.0;
  for (uint8_t mode : {0, 7}) {
    FlightSafetyTestPeer::idle(*node_, mode, 1.0);
    auto sent = client->async_send_goal(goal);
    ASSERT_EQ(sent.wait_for(2s), std::future_status::ready);
    ASSERT_NE(sent.get(), nullptr);
    auto result = client->async_get_result(sent.get());
    const auto deadline = std::chrono::steady_clock::now() + 3s;
    while (result.wait_for(0s) != std::future_status::ready &&
      std::chrono::steady_clock::now() < deadline)
    {
      FlightSafetyTestPeer::tick(*node_);
      std::this_thread::sleep_for(5ms);
    }
    ASSERT_EQ(result.wait_for(0s), std::future_status::ready);
    EXPECT_EQ(result.get().code, rclcpp_action::ResultCode::SUCCEEDED);
  }
  EXPECT_EQ(offboard_calls_.load(), 2);
  EXPECT_EQ(arm_calls_.load(), 2);
  EXPECT_EQ(disarm_calls_.load(), 0);
}
TEST_F(FlightSafety, RetiredAcceptedCallbackCannotClearNewGoalReservation)
{
  arm_hook_ = [this](auto request, auto response) {
      std::this_thread::sleep_for(300ms);
      FlightSafetyTestPeer::armed(*node_, request->arm);
      response->success = true;
    };
  startGraph();
  heartbeat_enabled_ = false;
  FlightController::Takeoff::Goal goal;
  goal.target_altitude = 1.0;
  std::shared_ptr<rclcpp_action::ServerGoalHandle<FlightController::Takeoff>> retired;
  acceptedEvidenceRace<FlightController::Takeoff>("/retired_takeoff", goal, &retired);
  ASSERT_NE(retired, nullptr);
  heartbeat_enabled_ = true;
  FlightSafetyTestPeer::idle(*node_, 3, 1.0);
  auto client = rclcpp_action::create_client<FlightController::Takeoff>(peer_, "/takeoff");
  ASSERT_TRUE(client->wait_for_action_server(2s));
  auto sent = client->async_send_goal(goal);
  ASSERT_EQ(sent.wait_for(2s), std::future_status::ready);
  auto handle = sent.get();
  ASSERT_NE(handle, nullptr);
  auto result = client->async_get_result(handle);
  EXPECT_TRUE(FlightSafetyTestPeer::owns(*node_, handle->get_goal_id()));
  FlightSafetyTestPeer::finishOldTakeoff(*node_, retired);
  EXPECT_TRUE(FlightSafetyTestPeer::owns(*node_, handle->get_goal_id()));
  const auto deadline = std::chrono::steady_clock::now() + 2s;
  while (result.wait_for(0s) != std::future_status::ready &&
    std::chrono::steady_clock::now() < deadline)
  {
    FlightSafetyTestPeer::tick(*node_);
    std::this_thread::sleep_for(5ms);
  }
  ASSERT_EQ(result.wait_for(0s), std::future_status::ready);
  EXPECT_EQ(result.get().code, rclcpp_action::ResultCode::SUCCEEDED);
  EXPECT_EQ(disarm_calls_.load(), 0);
}
TEST_F(FlightSafety, TakeoffReadinessObservesWithoutReservingAndAdmissionRechecks)
{
  FlightSafetyTestPeer::idle(*node_, 2);
  for (int index = 0; index < 5; ++index) {
    const auto response = FlightSafetyTestPeer::readiness(*node_);
    ASSERT_EQ(response.names, std::vector<std::string>({"takeoff"}));
    ASSERT_TRUE(response.ready.at(0));
    EXPECT_TRUE(FlightSafetyTestPeer::isIdle(*node_));
  }
  auto goal = std::make_shared<FlightController::Takeoff::Goal>();
  goal->target_altitude = 1.0;
  FlightSafetyTestPeer::invalid(*node_);
  EXPECT_FALSE(FlightSafetyTestPeer::readiness(*node_).ready.at(0));
  EXPECT_EQ(
    FlightSafetyTestPeer::admit<FlightController::Takeoff>(*node_, {}, goal),
    rclcpp_action::GoalResponse::REJECT);
  EXPECT_TRUE(FlightSafetyTestPeer::isIdle(*node_));
  FlightSafetyTestPeer::idle(*node_, 2);
  EXPECT_EQ(
    FlightSafetyTestPeer::admit<FlightController::Takeoff>(*node_, {}, goal),
    rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE);
  EXPECT_FALSE(FlightSafetyTestPeer::readiness(*node_).ready.at(0));
  EXPECT_EQ(arm_calls_.load(), 0);
  EXPECT_EQ(mode_calls_.load(), 0);
}

TEST_F(FlightSafety, TakeoffReadinessDistinguishesMissingStateAndUninitializedClock)
{
  FlightSafetyTestPeer::idle(*node_, 2);
  FlightSafetyTestPeer::forgetState(*node_);
  auto response = FlightSafetyTestPeer::readiness(*node_);
  ASSERT_FALSE(response.ready.at(0));
  EXPECT_NE(response.details.at(0).find("state_not_received"), std::string::npos);
  auto goal = std::make_shared<FlightController::Takeoff::Goal>();
  goal->target_altitude = 1.0;
  EXPECT_EQ(
    FlightSafetyTestPeer::admit<FlightController::Takeoff>(*node_, {}, goal),
    rclcpp_action::GoalResponse::REJECT);
  FlightSafetyTestPeer::idle(*node_, 2);
  ASSERT_EQ(rcl_set_ros_time_override(node_->get_clock()->get_clock_handle(), 0), RCL_RET_OK);
  response = FlightSafetyTestPeer::readiness(*node_);
  ASSERT_FALSE(response.ready.at(0));
  EXPECT_NE(response.details.at(0).find("clock_not_initialized"), std::string::npos);
  EXPECT_EQ(
    FlightSafetyTestPeer::admit<FlightController::Takeoff>(*node_, {}, goal),
    rclcpp_action::GoalResponse::REJECT);
  EXPECT_TRUE(FlightSafetyTestPeer::isIdle(*node_));
  EXPECT_EQ(arm_calls_.load(), 0);
}

TEST_F(FlightSafety, TakeoffReadinessDoesNotRenewFrozenSourceOrClearFaultLatch)
{
  FlightSafetyTestPeer::idle(*node_, 2);
  ASSERT_EQ(
    rcl_set_ros_time_override(node_->get_clock()->get_clock_handle(), 12000000000LL), RCL_RET_OK);
  FlightSafetyTestPeer::badStamp(*node_, 2);
  auto response = FlightSafetyTestPeer::readiness(*node_);
  ASSERT_FALSE(response.ready.at(0));
  EXPECT_NE(response.details.at(0).find("source_stale_or_future"), std::string::npos);
  FlightSafetyTestPeer::idle(*node_, 2);
  FlightSafetyTestPeer::faultLatch(*node_);
  response = FlightSafetyTestPeer::readiness(*node_);
  EXPECT_FALSE(response.ready.at(0));
  EXPECT_NE(response.details.at(0).find("command_uncertain"), std::string::npos);
  EXPECT_TRUE(FlightSafetyTestPeer::fault(*node_));
  EXPECT_TRUE(FlightSafetyTestPeer::isIdle(*node_));
}
}  // namespace easyfly_flight_control
