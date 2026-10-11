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
#include <chrono>
#include <future>
#include <thread>
#include <tuple>
#include <vector>
#include "rcl/time.h"
#include "std_msgs/msg/u_int8.hpp"
#include "easyfly_flight_control/flight_controller.hpp"

namespace easyfly_flight_control
{
class PrecisionLandingTestPeer
{
public:
  struct Snapshot
  {
    bool ready;
    int64_t source;
    uint64_t sequence;
    uint64_t generation;
  };

  static Snapshot snapshot(FlightController & node)
  {
    std::lock_guard<std::recursive_mutex> lock(node.flight_mtx_);
    return {node.precision_target_ready(), node.precision_last_stamp_,
      node.precision_target_sequence_, node.precision_receiver_generation_};
  }

  static auto retire(FlightController & node)
  {
    std::lock_guard<std::recursive_mutex> lock(node.flight_mtx_);
    auto old = node.sub_precision_;
    node.precision_receiver_progress_time_ = std::chrono::steady_clock::now() -
      std::chrono::seconds(1);
    EXPECT_FALSE(node.precision_receiver_progress());
    EXPECT_EQ(node.precision_target_receipt_, std::chrono::steady_clock::time_point{});
    const auto qos = node.sub_precision_->get_actual_qos().get_rmw_qos_profile();
    EXPECT_EQ(qos.depth, 1u);
    EXPECT_EQ(qos.durability, RMW_QOS_POLICY_DURABILITY_VOLATILE);
    EXPECT_EQ(qos.reliability, RMW_QOS_POLICY_RELIABILITY_RELIABLE);
    return old;
  }

  static bool retired_unchanged(
    FlightController & node,
    rclcpp::Subscription<easyfly_msgs::msg::LandingGuidanceTarget>::SharedPtr old)
  {
    std::lock_guard<std::recursive_mutex> lock(node.flight_mtx_);
    const auto before = snapshot(node);
    const auto receipt = node.precision_target_receipt_;
    const auto progress = node.precision_receiver_progress_time_;
    auto invalid = std::make_shared<easyfly_msgs::msg::LandingGuidanceTarget>();
    std::shared_ptr<void> erased = invalid;
    old->handle_message(erased, rclcpp::MessageInfo{});
    const auto after = snapshot(node);
    return before.ready && after.ready && before.source == after.source &&
           before.sequence == after.sequence && before.generation == after.generation &&
           receipt == node.precision_target_receipt_ &&
           progress == node.precision_receiver_progress_time_;
  }

  static void hold_mutex(FlightController & node, std::promise<void> & entered)
  {
    std::lock_guard<std::recursive_mutex> lock(node.flight_mtx_);
    entered.set_value();
    std::this_thread::sleep_for(std::chrono::milliseconds(450));
  }

  static void future_trigger(FlightController & node)
  {
    std::lock_guard<std::recursive_mutex> lock(node.flight_mtx_);
    const auto watermark = node.precision_last_stamp_;
    node.precision_receiver_progress_time_ = std::chrono::steady_clock::now() -
      std::chrono::seconds(1);
    auto old = node.sub_precision_;
    auto target = std::make_shared<easyfly_msgs::msg::LandingGuidanceTarget>();
    target->header.stamp = rclcpp::Time(node.now().nanoseconds() + 1000000000);
    target->header.frame_id = "odom";
    target->source_header = target->header;
    target->source_header.frame_id = "camera_down_optical_frame";
    target->tag_id = 7;
    target->valid = true;
    std::shared_ptr<void> erased = target;
    old->handle_message(erased, rclcpp::MessageInfo{});
    EXPECT_EQ(node.precision_last_stamp_, watermark);
    EXPECT_FALSE(node.precision_target_.valid);
  }

  static bool receipt_empty(FlightController & node)
  {
    std::lock_guard<std::recursive_mutex> lock(node.flight_mtx_);
    return node.precision_target_receipt_ == std::chrono::steady_clock::time_point{};
  }

  static void check_diagnostics(FlightController & node)
  {
    // The fixture executor is stopped before changing this read-only flag.
    std::lock_guard<std::recursive_mutex> lock(node.flight_mtx_);
    easyfly_msgs::msg::LandingGuidanceTarget target;
    target.header.stamp = rclcpp::Time(10000000000LL);
    EXPECT_FALSE(node.precision_timing_diagnostics_);
    node.record_precision_timing("stored", target, rclcpp::MessageInfo{}, 1, 1, 0, 0, 99);
    EXPECT_TRUE(node.precision_timing_events_.empty());
    EXPECT_EQ(node.precision_timing_dropped_, 0u);
    node.precision_timing_diagnostics_ = true;
    for (int index = 0; index < 300; ++index) {
      node.record_precision_timing("stored", target, rclcpp::MessageInfo{}, 1, 1, 0, 0, 99);
    }
    ASSERT_EQ(node.precision_timing_events_.size(), 256u);
    EXPECT_EQ(node.precision_timing_dropped_, 44u);
    const auto & event = node.precision_timing_events_.back();
    EXPECT_NE(event.find("\"receive_to_callback_ms\":null"), std::string::npos);
    EXPECT_NE(event.find("\"session_active\":false"), std::string::npos);
    EXPECT_NE(event.find("\"callback_generation\":99"), std::string::npos);
    EXPECT_NE(event.find("\"lock_wait_ms\":0"), std::string::npos);
    node.flush_precision_timing();
    EXPECT_TRUE(node.precision_timing_events_.empty());
    EXPECT_EQ(node.precision_timing_dropped_, 44u);
    node.precision_timing_diagnostics_ = false;
  }

  static std::vector<std::string> timing_events(FlightController & node)
  {
    std::lock_guard<std::recursive_mutex> lock(node.flight_mtx_);
    return {node.precision_timing_events_.begin(), node.precision_timing_events_.end()};
  }

  static rclcpp::Subscription<std_msgs::msg::UInt8>::SharedPtr blocker(
    FlightController & node, double delay, std::promise<void> & entered,
    std::promise<void> & completed)
  {
    rclcpp::SubscriptionOptions options;
    options.callback_group = node.state_cb_group_;
    return node.create_subscription<std_msgs::msg::UInt8>(
      "/precision_queue_test/block", rclcpp::QoS(1),
      [delay, &entered, &completed](std_msgs::msg::UInt8::SharedPtr) {
        entered.set_value();
        std::this_thread::sleep_for(std::chrono::duration<double>(delay));
        completed.set_value();
      }, options);
  }
};

class PrecisionQueue : public ::testing::TestWithParam<std::tuple<int, double, double>>
{
protected:
  virtual bool timing_enabled() const {return false;}
  virtual std::chrono::milliseconds spin_start_delay() const
  {
    return std::chrono::milliseconds(0);
  }

  void SetUp() override
  {
    context = std::make_shared<rclcpp::Context>();
    context->init(0, nullptr);
    rclcpp::NodeOptions options;
    options.context(context).parameter_overrides(
      {
        rclcpp::Parameter("precision_enabled", true),
        rclcpp::Parameter("precision_timing_diagnostics", timing_enabled()),
        rclcpp::Parameter("precision_tag_id", 7),
        rclcpp::Parameter("precision_tag_size_m", 0.2),
        rclcpp::Parameter("precision_horizontal_speed", 0.2),
        rclcpp::Parameter("precision_descent_speed", 0.1),
        rclcpp::Parameter("precision_align_tolerance", 0.1),
        rclcpp::Parameter("precision_handoff_height", 0.3),
        rclcpp::Parameter("precision_descent_floor_height", 0.2),
        rclcpp::Parameter("precision_max_height", 3.0),
        rclcpp::Parameter("precision_max_radius", 2.0),
        rclcpp::Parameter("precision_plane_z", 0.0),
        rclcpp::Parameter("precision_target_max_age", 0.3)});
    controller = std::make_shared<FlightController>(options);
    ASSERT_EQ(
      rcl_enable_ros_time_override(controller->get_clock()->get_clock_handle()),
      RCL_RET_OK);
    set_clock(10000000000LL);
    peer =
      std::make_shared<rclcpp::Node>(
      "precision_queue_peer", rclcpp::NodeOptions().context(
        context));
    targets = peer->create_publisher<easyfly_msgs::msg::LandingGuidanceTarget>(
      "/landing/guidance_target", rclcpp::QoS(10));
    block = peer->create_publisher<std_msgs::msg::UInt8>("/precision_queue_test/block", 1);
    rclcpp::ExecutorOptions execution;
    execution.context = context;
    executor = std::make_shared<rclcpp::executors::MultiThreadedExecutor>(execution, 4);
    executor->add_node(controller);
    executor->add_node(peer);
    worker = std::thread(
      [this]() {
        std::this_thread::sleep_for(spin_start_delay());
        executor->spin();
      });
    // Discovery can complete before the worker starts spin(). A cancel in that
    // window is lost when spin() sets its flag, causing an unbounded test join.
    ASSERT_TRUE(wait([this]() {return executor->is_spinning();}));
    ASSERT_TRUE(wait([this]() {return targets->get_subscription_count() > 0;}));
  }

  void TearDown() override
  {
    if (executor) {executor->cancel();}
    // If SetUp's startup wait itself failed, a late spin must observe an
    // invalid context rather than undo cancellation and make join unbounded.
    if (context) {context->shutdown("non-flying DDS guidance test complete");}
    if (worker.joinable()) {worker.join();}
    executor.reset();
    blocker.reset();
    controller.reset();
    peer.reset();
  }

  void set_clock(int64_t source)
  {
    ASSERT_EQ(
      rcl_set_ros_time_override(controller->get_clock()->get_clock_handle(), source), RCL_RET_OK);
  }

  void send(int64_t source)
  {
    easyfly_msgs::msg::LandingGuidanceTarget target;
    target.header.stamp = rclcpp::Time(source);
    target.header.frame_id = "odom";
    target.source_header = target.header;
    target.source_header.frame_id = "camera_down_optical_frame";
    target.tag_id = 7;
    target.tag_size_m = 0.2;
    target.valid = true;
    target.plane_normal.z = 1.0;
    targets->publish(target);
  }

  template<typename Predicate>
  bool wait(Predicate predicate, double seconds = 3.0)
  {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::duration<double>(seconds);
    while (std::chrono::steady_clock::now() < deadline) {
      if (predicate()) {return true;}
      std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
    return predicate();
  }

  rclcpp::Context::SharedPtr context;
  std::shared_ptr<FlightController> controller;
  std::shared_ptr<rclcpp::Node> peer;
  std::shared_ptr<rclcpp::executors::MultiThreadedExecutor> executor;
  std::thread worker;
  rclcpp::Publisher<easyfly_msgs::msg::LandingGuidanceTarget>::SharedPtr targets;
  rclcpp::Publisher<std_msgs::msg::UInt8>::SharedPtr block;
  rclcpp::Subscription<std_msgs::msg::UInt8>::SharedPtr blocker;
};

TEST_P(PrecisionQueue, ReaderDelayCannotRenewOldGuidance)
{
  const auto count = std::get<0>(GetParam());
  const auto delay = std::get<1>(GetParam());
  const auto clock_scale = std::get<2>(GetParam());
  const int64_t initial = 10000000000LL;
  send(initial);
  ASSERT_TRUE(wait([this]() {return PrecisionLandingTestPeer::snapshot(*controller).ready;}));
  std::promise<void> entered, completed;
  auto began = entered.get_future();
  auto done = completed.get_future();
  blocker = PrecisionLandingTestPeer::blocker(*controller, delay, entered, completed);
  ASSERT_TRUE(wait([this]() {return block->get_subscription_count() > 0;}));
  block->publish(std_msgs::msg::UInt8());
  ASSERT_EQ(began.wait_for(std::chrono::seconds(3)), std::future_status::ready);
  std::vector<int64_t> inputs;
  for (int index = 0; index < count; ++index) {
    inputs.push_back(initial + 1000000LL + index * 1000LL);
    send(inputs.back());
  }
  set_clock(inputs.back() + static_cast<int64_t>(delay * clock_scale * 1e9));
  ASSERT_EQ(done.wait_for(std::chrono::seconds(3)), std::future_status::ready);
  // Allow the callback group to consume the queued message (or retire its reader).
  wait(
    [&]() {
      return PrecisionLandingTestPeer::snapshot(*controller).source == inputs.back();
    }, 0.08);
  const auto observed = PrecisionLandingTestPeer::snapshot(*controller);
  std::cout << "GUIDANCE_QUEUE count=" << count << " delay=" << delay <<
    " clock_scale=" << clock_scale << " old_source=" << inputs.back() <<
    " accepted_source=" << observed.source << " ready=" << observed.ready << std::endl;
  if (delay > 0.3) {
    EXPECT_FALSE(observed.ready) << "queued guidance must not renew callback receipt TTL";
    EXPECT_GT(observed.generation, 0u);
  } else {
    EXPECT_TRUE(observed.ready);
    EXPECT_EQ(observed.source, inputs.back());
    EXPECT_EQ(observed.sequence, 2u) << "depth=1 must consume only the latest burst frame";
    EXPECT_EQ(observed.generation, 0u);
  }
  // A genuinely advancing stream may recover after new volatile readers rematch.
  int64_t fresh = inputs.back() + static_cast<int64_t>(delay * clock_scale * 1e9);
  ASSERT_TRUE(
    wait(
      [&]() {
        fresh += 1000000;
        set_clock(fresh);
        send(fresh);
        const auto value = PrecisionLandingTestPeer::snapshot(*controller);
        return value.ready && value.source > inputs.back();
      }));
}

INSTANTIATE_TEST_SUITE_P(
  ActualDDS, PrecisionQueue,
  ::testing::Values(
    std::make_tuple(1, 0.45, 1.0), std::make_tuple(1, 0.45, 0.1),
    std::make_tuple(8, 0.18, 0.1)));

class PrecisionReceiverBoundaries : public PrecisionQueue {};

class PrecisionDelayedStartup : public PrecisionQueue
{
protected:
  std::chrono::milliseconds spin_start_delay() const override
  {
    return std::chrono::milliseconds(120);
  }
};

TEST_F(PrecisionDelayedStartup, ImmediateCancelWaitsForActualExecutorStartup)
{
  EXPECT_TRUE(executor->is_spinning());
  executor->cancel();
  worker.join();
  EXPECT_FALSE(executor->is_spinning());
}

class PrecisionFrameTiming : public PrecisionQueue
{
protected:
  bool timing_enabled() const override {return true;}
};

TEST_F(PrecisionFrameTiming, ActualDDSCallbackRecordsSourceAndOutcome)
{
  send(10000000000LL);
  ASSERT_TRUE(
    wait([this]() {return !PrecisionLandingTestPeer::timing_events(*controller).empty();}));
  const auto events = PrecisionLandingTestPeer::timing_events(*controller);
  ASSERT_FALSE(events.empty());
  EXPECT_NE(events.back().find("\"source_ns\":10000000000"), std::string::npos);
  EXPECT_NE(events.back().find("\"outcome\":\"stored\""), std::string::npos);
  EXPECT_NE(events.back().find("\"ready_at_exit\":true"), std::string::npos);
  EXPECT_NE(events.back().find("\"received_wall_ns\":"), std::string::npos);
}

TEST_F(PrecisionFrameTiming, RetiredCallbackKeepsItsOriginalGeneration)
{
  executor->cancel();
  worker.join();
  auto old = PrecisionLandingTestPeer::retire(*controller);
  auto target = std::make_shared<easyfly_msgs::msg::LandingGuidanceTarget>();
  std::shared_ptr<void> erased = target;
  old->handle_message(erased, rclcpp::MessageInfo{});
  const auto events = PrecisionLandingTestPeer::timing_events(*controller);
  ASSERT_FALSE(events.empty());
  EXPECT_NE(events.back().find("\"outcome\":\"retired\""), std::string::npos);
  EXPECT_NE(events.back().find("\"generation\":1"), std::string::npos);
  EXPECT_NE(events.back().find("\"callback_generation\":0"), std::string::npos);
}

TEST_F(PrecisionReceiverBoundaries, DiagnosticsAreReadOnlyDisabledAndBounded)
{
  EXPECT_FALSE(controller->get_parameter("precision_timing_diagnostics").as_bool());
  EXPECT_TRUE(controller->describe_parameter("precision_timing_diagnostics").read_only);
  executor->cancel();
  worker.join();
  PrecisionLandingTestPeer::check_diagnostics(*controller);
}

TEST_F(PrecisionReceiverBoundaries, RetiredCallbackCannotInvalidateRecoveredEvidence)
{
  send(10000000000LL);
  ASSERT_TRUE(wait([this]() {return PrecisionLandingTestPeer::snapshot(*controller).ready;}));
  auto old = PrecisionLandingTestPeer::retire(*controller);
  EXPECT_FALSE(PrecisionLandingTestPeer::snapshot(*controller).ready);
  ASSERT_TRUE(
    wait(
      [this]() {
        const auto fresh = controller->now().nanoseconds() + 1000000;
        set_clock(fresh);
        send(fresh);
        return PrecisionLandingTestPeer::snapshot(*controller).ready;
      }));
  EXPECT_TRUE(PrecisionLandingTestPeer::retired_unchanged(*controller, old));
}

TEST_F(PrecisionReceiverBoundaries, CallbackWaitingOnFlightMutexCannotRenewEvidence)
{
  send(10000000000LL);
  ASSERT_TRUE(wait([this]() {return PrecisionLandingTestPeer::snapshot(*controller).ready;}));
  std::promise<void> entered;
  auto began = entered.get_future();
  std::thread holding([this, &entered]() {
      PrecisionLandingTestPeer::hold_mutex(*controller, entered);
    });
  const auto reached = began.wait_for(std::chrono::seconds(3));
  if (reached == std::future_status::ready) {
    send(10001000000LL);
    set_clock(10046000000LL);
  }
  holding.join();
  ASSERT_EQ(reached, std::future_status::ready);
  ASSERT_TRUE(
    wait(
      [this]() {
        return PrecisionLandingTestPeer::snapshot(*controller).generation > 0;
      }));
  EXPECT_FALSE(PrecisionLandingTestPeer::snapshot(*controller).ready);
}

TEST_F(PrecisionReceiverBoundaries, FarFutureGapTriggerCannotPoisonSourceWatermark)
{
  send(10000000000LL);
  ASSERT_TRUE(wait([this]() {return PrecisionLandingTestPeer::snapshot(*controller).ready;}));
  PrecisionLandingTestPeer::future_trigger(*controller);
  EXPECT_GT(PrecisionLandingTestPeer::snapshot(*controller).generation, 0u);
}

TEST_F(PrecisionReceiverBoundaries, ReaderCreationFailureClearsEvidenceBeforeThrowing)
{
  send(10000000000LL);
  ASSERT_TRUE(wait([this]() {return PrecisionLandingTestPeer::snapshot(*controller).ready;}));
  executor->cancel();
  worker.join();
  context->shutdown("test-only invalid context to fail reader creation");
  EXPECT_ANY_THROW(PrecisionLandingTestPeer::retire(*controller));
  EXPECT_FALSE(PrecisionLandingTestPeer::snapshot(*controller).ready);
  EXPECT_TRUE(PrecisionLandingTestPeer::receipt_empty(*controller));
}
}  // namespace easyfly_flight_control
