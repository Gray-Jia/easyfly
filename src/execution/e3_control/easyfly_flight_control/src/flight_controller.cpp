#include "easyfly_flight_control/flight_controller.hpp"

#include <cmath>
#include <chrono>

namespace easyfly_flight_control
{

using namespace std::placeholders;
using namespace std::chrono_literals;

// ================================================================
// PID
// ================================================================

double PID::update(double error, double dt)
{
  if (dt <= 0.0) return 0.0;

  integral += error * dt;
  integral = std::clamp(integral, -limit_i, limit_i);

  double deriv = (error - prev_error) / dt;
  prev_error = error;

  return kp * error + ki * integral + kd * deriv;
}

void PID::reset()
{
  integral   = 0.0;
  prev_error = 0.0;
}

// ================================================================
// Constructor
// ================================================================

FlightController::FlightController(const rclcpp::NodeOptions & options)
  : Node("flight_controller", options)
{
  // ---- params ----
  ctl_rate_ = declare_parameter("control_rate", 20.0);
  land_timeout_ = declare_parameter("land_timeout", 30.0);

  pid_x_.kp  = declare_parameter("pid_x.kp", 0.8);
  pid_x_.ki  = declare_parameter("pid_x.ki", 0.02);
  pid_x_.kd  = declare_parameter("pid_x.kd", 0.1);
  pid_y_.kp  = declare_parameter("pid_y.kp", 0.8);
  pid_y_.ki  = declare_parameter("pid_y.ki", 0.02);
  pid_y_.kd  = declare_parameter("pid_y.kd", 0.1);
  pid_z_.kp  = declare_parameter("pid_z.kp", 1.2);
  pid_z_.ki  = declare_parameter("pid_z.ki", 0.03);
  pid_z_.kd  = declare_parameter("pid_z.kd", 0.15);
  pid_yaw_.kp = declare_parameter("pid_yaw.kp", 1.0);
  pid_yaw_.ki = declare_parameter("pid_yaw.ki", 0.0);
  pid_yaw_.kd = declare_parameter("pid_yaw.kd", 0.0);

  auto period = std::chrono::milliseconds(static_cast<int>(1000.0 / ctl_rate_));
  auto qos = rclcpp::QoS(10);

  // ---- state sub ----
  sub_uav_state_ = create_subscription<easyfly_msgs::msg::UAVState>(
    "/uav_state", rclcpp::SensorDataQoS(),
    std::bind(&FlightController::cb_uav_state, this, _1));

  // ---- command pub ----
  pub_uav_cmd_ = create_publisher<easyfly_msgs::msg::UAVCommand>("/uav_command", qos);

  // ---- service clients (独立 callback group 避免与 action 回调死锁) ----
  cli_cb_group_ = create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);

  cli_arm_  = create_client<easyfly_msgs::srv::ArmMotors>(
    "/arm_motors", rmw_qos_profile_services_default, cli_cb_group_);
  cli_mode_ = create_client<easyfly_msgs::srv::SetFlightMode>(
    "/set_flight_mode", rmw_qos_profile_services_default, cli_cb_group_);

  // ---- action servers ----
  as_takeoff_ = rclcpp_action::create_server<Takeoff>(
    this, "/takeoff",
    std::bind(&FlightController::handle_takeoff_goal,   this, _1, _2),
    std::bind(&FlightController::handle_takeoff_cancel, this, _1),
    std::bind(&FlightController::handle_takeoff_accepted, this, _1));

  as_land_ = rclcpp_action::create_server<Land>(
    this, "/land",
    std::bind(&FlightController::handle_land_goal,   this, _1, _2),
    std::bind(&FlightController::handle_land_cancel, this, _1),
    std::bind(&FlightController::handle_land_accepted, this, _1));

  as_waypoint_ = rclcpp_action::create_server<GoToWaypoint>(
    this, "/goto_waypoint",
    std::bind(&FlightController::handle_waypoint_goal,   this, _1, _2),
    std::bind(&FlightController::handle_waypoint_cancel, this, _1),
    std::bind(&FlightController::handle_waypoint_accepted, this, _1));

  // ---- control timer (独立 callback group，不受 action 回调阻塞) ----
  ctl_cb_group_ = create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
  timer_ctl_ = create_wall_timer(period,
    std::bind(&FlightController::control_loop, this), ctl_cb_group_);

  RCLCPP_INFO(get_logger(), "FlightController started — %gHz, /takeoff, /land, /goto_waypoint",
    ctl_rate_);
}

// ================================================================
// callbacks
// ================================================================

void FlightController::cb_uav_state(const easyfly_msgs::msg::UAVState::SharedPtr msg)
{
  uav_ = *msg;
  state_received_ = true;
}

// ================================================================
// control loop — 20Hz
// ================================================================

void FlightController::control_loop()
{
  if (!state_received_) return;

  double dt = 1.0 / ctl_rate_;
  easyfly_msgs::msg::UAVCommand cmd;
  cmd.control_mode = easyfly_msgs::msg::UAVCommand::POSITION;

  if (active_ == TAKEOFF) {
    // ---- takeoff: smooth ascent ----
    double step = takeoff_speed_ * dt;
    double target_z = uav_.position_z + step;

    // 用简单线性插值代替 PID（起飞阶段需要平滑爬升）
    target_z = std::min(target_z, takeoff_target_z_);
    double dist = std::abs(takeoff_target_z_ - uav_.position_z);  // 到目标高度剩余距离

    cmd.position_x = uav_.position_x;
    cmd.position_y = uav_.position_y;
    cmd.position_z = target_z;
    cmd.yaw         = uav_.yaw;

    pub_uav_cmd_->publish(cmd);

    // feedback
    if (gh_takeoff_) {
      auto fb = std::make_shared<Takeoff::Feedback>();
      fb->current_altitude = uav_.position_z;
      fb->progress = std::clamp(
        static_cast<float>((uav_.position_z - takeoff_start_z_) /
          std::max(takeoff_target_z_ - takeoff_start_z_, 0.1)),
        0.0f, 1.0f);
      gh_takeoff_->publish_feedback(fb);

      if (dist < 0.2) {  // arrived
        auto res = std::make_shared<Takeoff::Result>();
        res->success = true;
        res->message = "takeoff complete";
        gh_takeoff_->succeed(res);
        gh_takeoff_.reset();
        active_ = NONE;
        RCLCPP_INFO(get_logger(), "Takeoff done at z=%.2f", uav_.position_z);
      }
    }

  } else if (active_ == WAYPOINT) {
    // ---- waypoint: PID control ----
    double err_x = wp_target_x_ - uav_.position_x;
    double err_y = wp_target_y_ - uav_.position_y;
    double err_z = wp_target_z_ - uav_.position_z;

    // yaw error (wrap to [-pi, pi])
    double err_yaw = wp_target_yaw_ - uav_.yaw;
    while (err_yaw >  M_PI) err_yaw -= 2 * M_PI;
    while (err_yaw < -M_PI) err_yaw += 2 * M_PI;

    double dist = std::sqrt(err_x * err_x + err_y * err_y + err_z * err_z);

    // clamp speed
    double vx = pid_x_.update(err_x, dt);
    double vy = pid_y_.update(err_y, dt);
    double vz = pid_z_.update(err_z, dt);
    double vyaw = pid_yaw_.update(err_yaw, dt);

    double speed = std::sqrt(vx * vx + vy * vy + vz * vz);
    if (speed > wp_max_speed_ && speed > 0.0) {
      double scale = wp_max_speed_ / speed;
      vx *= scale; vy *= scale; vz *= scale;
    }

    cmd.position_x = uav_.position_x + vx * dt;
    cmd.position_y = uav_.position_y + vy * dt;
    cmd.position_z = uav_.position_z + vz * dt;
    cmd.yaw         = uav_.yaw + vyaw * dt;

    pub_uav_cmd_->publish(cmd);

    // feedback
    if (gh_waypoint_) {
      auto fb = std::make_shared<GoToWaypoint::Feedback>();
      fb->distance_remaining = dist;
      fb->progress = 1.0f - std::clamp(
        static_cast<float>(dist / std::max(wp_start_dist_, 0.01)),
        0.0f, 1.0f);
      gh_waypoint_->publish_feedback(fb);

      if (dist < wp_accept_radius_) {
        auto res = std::make_shared<GoToWaypoint::Result>();
        res->success = true;
        res->message = "waypoint reached";
        gh_waypoint_->succeed(res);
        gh_waypoint_.reset();
        active_ = NONE;
        RCLCPP_INFO(get_logger(), "Waypoint reached (dist=%.2f)", dist);
      }
    }

  } else if (active_ == LANDING) {
    // LAND mode is handled once in land_accepted;
    // here we just monitor until relative_altitude near 0, then disarm.
    if (gh_land_) {
      auto fb = std::make_shared<Land::Feedback>();
      fb->current_altitude = uav_.position_z;
      gh_land_->publish_feedback(fb);

      if (uav_.flight_mode == 7 && uav_.relative_altitude < 0.15 &&
          std::abs(uav_.velocity_z) < 0.2) {
        // Landed — disarm
        call_arm(false);
        auto res = std::make_shared<Land::Result>();
        res->success = true;
        res->message = "landed";
        gh_land_->succeed(res);
        gh_land_.reset();
        active_ = NONE;
        RCLCPP_INFO(get_logger(), "Land done");
      }
    }
  }
}

// ================================================================
// Takeoff action
// ================================================================

rclcpp_action::GoalResponse FlightController::handle_takeoff_goal(
  const rclcpp_action::GoalUUID &, std::shared_ptr<const Takeoff::Goal> goal)
{
  if (active_ != NONE) {
    RCLCPP_WARN(get_logger(), "Takeoff rejected: another action is active");
    return rclcpp_action::GoalResponse::REJECT;
  }
  if (goal->target_altitude <= 0.0) {
    RCLCPP_WARN(get_logger(), "Takeoff rejected: altitude must be > 0");
    return rclcpp_action::GoalResponse::REJECT;
  }
  return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
}

rclcpp_action::CancelResponse FlightController::handle_takeoff_cancel(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<Takeoff>>)
{
  active_ = NONE;
  gh_takeoff_.reset();
  return rclcpp_action::CancelResponse::ACCEPT;
}

void FlightController::handle_takeoff_accepted(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<Takeoff>> gh)
{
  auto goal = gh->get_goal();

  // 1. arm
  if (!call_arm(true)) {
    auto res = std::make_shared<Takeoff::Result>();
    res->success = false; res->message = "arm failed";
    gh->abort(res); return;
  }

  // 2. 直接发初始 setpoint（不等 timer），确保桥接层有有效 setpoint 再切 OFFBOARD
  takeoff_target_z_ = goal->target_altitude;
  takeoff_speed_    = (goal->climb_speed > 0.0) ? goal->climb_speed : 1.0;
  takeoff_start_z_  = uav_.position_z;
  pid_x_.reset(); pid_y_.reset(); pid_z_.reset(); pid_yaw_.reset();

  easyfly_msgs::msg::UAVCommand init_cmd;
  init_cmd.control_mode = easyfly_msgs::msg::UAVCommand::POSITION;
  init_cmd.position_x   = uav_.position_x;
  init_cmd.position_y   = uav_.position_y;
  init_cmd.position_z   = uav_.position_z;  // 保持当前位置
  init_cmd.yaw          = uav_.yaw;
  pub_uav_cmd_->publish(init_cmd);

  gh_takeoff_ = gh;
  active_ = TAKEOFF;

  // 3. 切 OFFBOARD（setpoint 已经发出，PX4 会接受）
  if (!call_set_mode(3)) {
    auto res = std::make_shared<Takeoff::Result>();
    res->success = false; res->message = "OFFBOARD mode switch failed";
    gh->abort(res); active_ = NONE; return;
  }

  RCLCPP_INFO(get_logger(), "Takeoff started: target_z=%.1f", takeoff_target_z_);
}

// ================================================================
// Land action
// ================================================================

rclcpp_action::GoalResponse FlightController::handle_land_goal(
  const rclcpp_action::GoalUUID &, std::shared_ptr<const Land::Goal>)
{
  if (active_ != NONE) {
    return rclcpp_action::GoalResponse::REJECT;
  }
  return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
}

rclcpp_action::CancelResponse FlightController::handle_land_cancel(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<Land>>)
{
  active_ = NONE;
  gh_land_.reset();
  return rclcpp_action::CancelResponse::ACCEPT;
}

void FlightController::handle_land_accepted(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<Land>> gh)
{
  if (!call_set_mode(7)) {  // LAND mode
    auto res = std::make_shared<Land::Result>();
    res->success = false;
    res->message = "LAND mode switch failed";
    gh->abort(res);
    return;
  }

  gh_land_ = gh;
  active_ = LANDING;
  RCLCPP_INFO(get_logger(), "Land started");
}

// ================================================================
// Waypoint action
// ================================================================

rclcpp_action::GoalResponse FlightController::handle_waypoint_goal(
  const rclcpp_action::GoalUUID &, std::shared_ptr<const GoToWaypoint::Goal> goal)
{
  if (active_ != NONE) {
    return rclcpp_action::GoalResponse::REJECT;
  }
  return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
}

rclcpp_action::CancelResponse FlightController::handle_waypoint_cancel(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<GoToWaypoint>>)
{
  active_ = NONE;
  gh_waypoint_.reset();
  return rclcpp_action::CancelResponse::ACCEPT;
}

void FlightController::handle_waypoint_accepted(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<GoToWaypoint>> gh)
{
  auto g = gh->get_goal();

  wp_target_x_      = g->target_x;
  wp_target_y_      = g->target_y;
  wp_target_z_      = g->target_z;
  wp_target_yaw_    = std::isfinite(g->target_yaw) ? g->target_yaw : uav_.yaw;
  wp_max_speed_     = (g->max_speed > 0.0) ? g->max_speed : 2.0;
  wp_accept_radius_ = (g->acceptance_radius > 0.0) ? g->acceptance_radius : 0.5;

  double dx = wp_target_x_ - uav_.position_x;
  double dy = wp_target_y_ - uav_.position_y;
  double dz = wp_target_z_ - uav_.position_z;
  wp_start_dist_ = std::sqrt(dx * dx + dy * dy + dz * dz);

  pid_x_.reset(); pid_y_.reset(); pid_z_.reset(); pid_yaw_.reset();

  gh_waypoint_ = gh;
  active_ = WAYPOINT;

  RCLCPP_INFO(get_logger(), "Waypoint started: (%.1f,%.1f,%.1f) dist=%.1f",
    wp_target_x_, wp_target_y_, wp_target_z_, wp_start_dist_);
}

// ================================================================
// helpers
// ================================================================

bool FlightController::call_arm(bool arm)
{
  if (!cli_arm_->wait_for_service(3s)) {
    RCLCPP_ERROR(get_logger(), "/arm_motors not available");
    return false;
  }
  auto req = std::make_shared<easyfly_msgs::srv::ArmMotors::Request>();
  req->arm = arm;

  auto future = cli_arm_->async_send_request(req);
  if (future.wait_for(5s) != std::future_status::ready) return false;
  return future.get()->success;
}

bool FlightController::call_set_mode(uint8_t mode)
{
  if (!cli_mode_->wait_for_service(3s)) {
    RCLCPP_ERROR(get_logger(), "/set_flight_mode not available");
    return false;
  }
  auto req = std::make_shared<easyfly_msgs::srv::SetFlightMode::Request>();
  req->flight_mode = mode;

  auto future = cli_mode_->async_send_request(req);
  if (future.wait_for(5s) != std::future_status::ready) return false;
  return future.get()->success;
}

double FlightController::clamp(double v, double lo, double hi)
{
  return std::max(lo, std::min(hi, v));
}

}  // namespace easyfly_flight_control
