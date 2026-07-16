#include "easyfly_flight_control/flight_controller.hpp"
#include <cmath>
#include <chrono>

namespace easyfly_flight_control
{
using namespace std::placeholders;
using namespace std::chrono_literals;

double PID::update(double error, double dt)
{
  if (dt <= 0.0) return 0.0;
  integral += error * dt; integral = std::clamp(integral, -limit_i, limit_i);
  double deriv = (error - prev_error) / dt; prev_error = error;
  return kp * error + ki * integral + kd * deriv;
}
void PID::reset() { integral = 0.0; prev_error = 0.0; }

FlightController::FlightController(const rclcpp::NodeOptions & options)
  : Node("flight_controller", options)
{
  ctl_rate_ = declare_parameter("control_rate", 20.0);
  pid_x_.kp=2.0; pid_x_.ki=0.05; pid_x_.kd=0.3;
  pid_y_.kp=2.0; pid_y_.ki=0.05; pid_y_.kd=0.3;
  pid_z_.kp=2.5; pid_z_.ki=0.05; pid_z_.kd=0.4;
  pid_yaw_.kp=2.0;
  auto period = std::chrono::milliseconds(static_cast<int>(1000.0 / ctl_rate_));
  auto qos = rclcpp::QoS(10);

  sub_uav_state_ = create_subscription<easyfly_msgs::msg::UAVState>(
    "/uav_state", rclcpp::SensorDataQoS(),
    std::bind(&FlightController::cb_uav_state, this, _1));
  sub_landed_ = create_subscription<mavros_msgs::msg::ExtendedState>(
    "/mavros/extended_state", rclcpp::SensorDataQoS(),
    [this](const mavros_msgs::msg::ExtendedState::SharedPtr m) { landed_state_ = m->landed_state; });
  pub_uav_cmd_ = create_publisher<easyfly_msgs::msg::UAVCommand>("/uav_command", qos);

  cli_cb_group_ = create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
  cli_arm_ = create_client<easyfly_msgs::srv::ArmMotors>("/arm_motors", rmw_qos_profile_services_default, cli_cb_group_);
  cli_mode_= create_client<easyfly_msgs::srv::SetFlightMode>("/set_flight_mode", rmw_qos_profile_services_default, cli_cb_group_);

  as_takeoff_ = rclcpp_action::create_server<Takeoff>(this, "/takeoff",
    std::bind(&FlightController::handle_takeoff_goal,   this, _1, _2),
    std::bind(&FlightController::handle_takeoff_cancel, this, _1),
    std::bind(&FlightController::handle_takeoff_accepted, this, _1));
  as_land_ = rclcpp_action::create_server<Land>(this, "/land",
    std::bind(&FlightController::handle_land_goal,   this, _1, _2),
    std::bind(&FlightController::handle_land_cancel, this, _1),
    std::bind(&FlightController::handle_land_accepted, this, _1));
  as_waypoint_ = rclcpp_action::create_server<GoToWaypoint>(this, "/goto_waypoint",
    std::bind(&FlightController::handle_waypoint_goal,   this, _1, _2),
    std::bind(&FlightController::handle_waypoint_cancel, this, _1),
    std::bind(&FlightController::handle_waypoint_accepted, this, _1));

  ctl_cb_group_ = create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
  timer_ctl_ = create_wall_timer(period, std::bind(&FlightController::control_loop, this), ctl_cb_group_);
  RCLCPP_INFO(get_logger(), "FlightController v4");
}

void FlightController::cb_uav_state(const easyfly_msgs::msg::UAVState::SharedPtr msg)
{ uav_ = *msg; state_received_ = true; }

void FlightController::control_loop()
{
  if (!state_received_) return;
  double dt = 1.0 / ctl_rate_;
  easyfly_msgs::msg::UAVCommand cmd;
  cmd.control_mode = easyfly_msgs::msg::UAVCommand::POSITION;

  if (active_ == TAKEOFF) {
    double t = (now() - takeoff_start_time_).seconds();
    double tz = std::min(takeoff_start_z_ + t * takeoff_speed_, takeoff_target_z_);
    cmd.position_x = takeoff_start_x_; cmd.position_y = takeoff_start_y_;
    cmd.position_z = tz; cmd.yaw = uav_.yaw;
    pub_uav_cmd_->publish(cmd);
    if (gh_takeoff_ && std::abs(takeoff_target_z_ - uav_.position_z) < 0.5) {
      auto r = std::make_shared<Takeoff::Result>(); r->success = true;
      gh_takeoff_->succeed(r); gh_takeoff_.reset();
      hover_x_ = takeoff_start_x_; hover_y_ = takeoff_start_y_;
      hover_z_ = takeoff_target_z_; hover_yaw_ = uav_.yaw;
      active_ = HOVER;
    }
  } else if (active_ == WAYPOINT) {
    double ex = wp_target_x_ - uav_.position_x, ey = wp_target_y_ - uav_.position_y;
    double ez = wp_target_z_ - uav_.position_z, eyaw = wp_target_yaw_ - uav_.yaw;
    while (eyaw >  M_PI) eyaw -= 2*M_PI;
    while (eyaw < -M_PI) eyaw += 2*M_PI;
    double dist = std::sqrt(ex*ex + ey*ey + ez*ez);
    double vx = pid_x_.update(ex, dt), vy = pid_y_.update(ey, dt);
    double vz = pid_z_.update(ez, dt), vyaw = pid_yaw_.update(eyaw, dt);
    double spd = std::sqrt(vx*vx + vy*vy + vz*vz);
    if (spd > wp_max_speed_ && spd > 0.0) { double s = wp_max_speed_/spd; vx*=s; vy*=s; vz*=s; }
    cmd.position_x = uav_.position_x + vx*dt;
    cmd.position_y = uav_.position_y + vy*dt;
    cmd.position_z = uav_.position_z + vz*dt;
    cmd.yaw = uav_.yaw + vyaw*dt;
    pub_uav_cmd_->publish(cmd);
    if (gh_waypoint_ && dist < wp_accept_radius_) {
      auto r = std::make_shared<GoToWaypoint::Result>(); r->success = true;
      gh_waypoint_->succeed(r); gh_waypoint_.reset();
      hover_x_ = wp_target_x_; hover_y_ = wp_target_y_;
      hover_z_ = wp_target_z_; hover_yaw_ = wp_target_yaw_;
      active_ = HOVER;
    }
  } else if (active_ == HOVER) {
    if (uav_.armed) {
      cmd.position_x = hover_x_; cmd.position_y = hover_y_;
      cmd.position_z = hover_z_; cmd.yaw = hover_yaw_;
      pub_uav_cmd_->publish(cmd);
    }
  } else if (active_ == LANDING) {
    if (gh_land_) {
      double t = (now() - land_start_time_).seconds();
      double tz = land_start_z_ - t * 0.3;
      if (tz < takeoff_start_z_ - 0.15) tz = takeoff_start_z_ - 0.15;
      cmd.position_x = land_target_x_; cmd.position_y = land_target_y_;
      cmd.position_z = tz; cmd.yaw = uav_.yaw;
      pub_uav_cmd_->publish(cmd);
      auto fb = std::make_shared<Land::Feedback>();
      fb->current_altitude = uav_.position_z; gh_land_->publish_feedback(fb);

      // PX4 landed_state==1 → ON_GROUND → 触地后等 3s 上锁
      if (landed_state_ == 1) {
        if (!landed_seen_) { landed_at_ = now(); landed_seen_ = true; }
        if ((now() - landed_at_).seconds() > 3.0) {
          call_arm(false);
          auto r = std::make_shared<Land::Result>(); r->success = true;
          r->message = "landed"; gh_land_->succeed(r); gh_land_.reset();
          active_ = NONE; landed_seen_ = false;
        }
      } else if (t > 60.0) {
        call_arm(false);
        auto r = std::make_shared<Land::Result>(); r->success = true;
        r->message = "timeout"; gh_land_->succeed(r); gh_land_.reset();
        active_ = NONE;
      }
    }
  }
}

rclcpp_action::GoalResponse FlightController::handle_takeoff_goal(
  const rclcpp_action::GoalUUID &, std::shared_ptr<const Takeoff::Goal> g)
{ if (active_!=NONE || g->target_altitude<=0) return rclcpp_action::GoalResponse::REJECT;
  return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE; }
rclcpp_action::CancelResponse FlightController::handle_takeoff_cancel(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<Takeoff>>)
{ active_=NONE; gh_takeoff_.reset(); return rclcpp_action::CancelResponse::ACCEPT; }
void FlightController::handle_takeoff_accepted(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<Takeoff>> gh)
{
  auto g = gh->get_goal();
  if (!call_arm(true)) { auto r=std::make_shared<Takeoff::Result>(); r->success=false; gh->abort(r); return; }
  takeoff_target_z_=g->target_altitude; takeoff_speed_=(g->climb_speed>0)?g->climb_speed:1.0;
  takeoff_start_x_=uav_.position_x; takeoff_start_y_=uav_.position_y; takeoff_start_z_=uav_.position_z;
  pid_x_.reset(); pid_y_.reset(); pid_z_.reset(); pid_yaw_.reset(); takeoff_start_time_=now();
  easyfly_msgs::msg::UAVCommand ic; ic.control_mode=easyfly_msgs::msg::UAVCommand::POSITION;
  ic.position_x=uav_.position_x; ic.position_y=uav_.position_y;
  ic.position_z=uav_.position_z; ic.yaw=uav_.yaw;
  pub_uav_cmd_->publish(ic);
  gh_takeoff_=gh; active_=TAKEOFF;
  if (!call_set_mode(3)) { auto r=std::make_shared<Takeoff::Result>(); r->success=false; gh->abort(r); active_=NONE; return; }
}

rclcpp_action::GoalResponse FlightController::handle_land_goal(
  const rclcpp_action::GoalUUID &, std::shared_ptr<const Land::Goal>)
{ if (active_!=HOVER) return rclcpp_action::GoalResponse::REJECT;
  return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE; }
rclcpp_action::CancelResponse FlightController::handle_land_cancel(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<Land>>)
{ active_=HOVER; gh_land_.reset(); return rclcpp_action::CancelResponse::ACCEPT; }
void FlightController::handle_land_accepted(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<Land>> gh)
{ land_target_x_=uav_.position_x; land_target_y_=uav_.position_y;
  land_start_z_=uav_.position_z; gh_land_=gh; active_=LANDING; land_start_time_=now(); }

rclcpp_action::GoalResponse FlightController::handle_waypoint_goal(
  const rclcpp_action::GoalUUID &, std::shared_ptr<const GoToWaypoint::Goal>)
{ if (active_!=HOVER) return rclcpp_action::GoalResponse::REJECT;
  return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE; }
rclcpp_action::CancelResponse FlightController::handle_waypoint_cancel(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<GoToWaypoint>>)
{ active_=HOVER; gh_waypoint_.reset(); return rclcpp_action::CancelResponse::ACCEPT; }
void FlightController::handle_waypoint_accepted(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<GoToWaypoint>> gh)
{
  auto g=gh->get_goal();
  wp_target_x_=g->target_x; wp_target_y_=g->target_y; wp_target_z_=g->target_z;
  wp_target_yaw_=std::isfinite(g->target_yaw)?g->target_yaw:uav_.yaw;
  wp_max_speed_=(g->max_speed>0)?g->max_speed:2.0;
  wp_accept_radius_=(g->acceptance_radius>0)?g->acceptance_radius:0.5;
  double dx=wp_target_x_-uav_.position_x, dy=wp_target_y_-uav_.position_y, dz=wp_target_z_-uav_.position_z;
  wp_start_dist_=std::sqrt(dx*dx+dy*dy+dz*dz);
  pid_x_.reset(); pid_y_.reset(); pid_z_.reset(); pid_yaw_.reset();
  gh_waypoint_=gh; active_=WAYPOINT;
}

bool FlightController::call_arm(bool arm)
{
  if (!cli_arm_->wait_for_service(3s)) return false;
  auto r=std::make_shared<easyfly_msgs::srv::ArmMotors::Request>(); r->arm=arm;
  auto f=cli_arm_->async_send_request(r);
  if (f.wait_for(5s)!=std::future_status::ready) return false;
  return f.get()->success;
}
bool FlightController::call_set_mode(uint8_t m)
{
  if (!cli_mode_->wait_for_service(3s)) return false;
  auto r=std::make_shared<easyfly_msgs::srv::SetFlightMode::Request>(); r->flight_mode=m;
  auto f=cli_mode_->async_send_request(r);
  if (f.wait_for(5s)!=std::future_status::ready) return false;
  return f.get()->success;
}

}  // namespace easyfly_flight_control
