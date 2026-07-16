#ifndef EASYFLY_FLIGHT_CONTROL_FLIGHT_CONTROLLER_HPP_
#define EASYFLY_FLIGHT_CONTROL_FLIGHT_CONTROLLER_HPP_

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <mavros_msgs/msg/extended_state.hpp>

#include <easyfly_msgs/msg/uav_state.hpp>
#include <easyfly_msgs/msg/uav_command.hpp>
#include <easyfly_msgs/action/takeoff.hpp>
#include <easyfly_msgs/action/land.hpp>
#include <easyfly_msgs/action/go_to_waypoint.hpp>
#include <easyfly_msgs/srv/arm_motors.hpp>
#include <easyfly_msgs/srv/set_flight_mode.hpp>

namespace easyfly_flight_control
{

struct PID
{
  double kp, ki, kd;
  double integral{0.0}, prev_error{0.0};
  double limit_i{5.0};       // 积分限幅

  double update(double error, double dt);
  void   reset();
};

class FlightController : public rclcpp::Node
{
public:
  using Takeoff      = easyfly_msgs::action::Takeoff;
  using Land         = easyfly_msgs::action::Land;
  using GoToWaypoint = easyfly_msgs::action::GoToWaypoint;

  explicit FlightController(const rclcpp::NodeOptions & options = rclcpp::NodeOptions());

private:
  // ---- state callback ----
  void cb_uav_state(const easyfly_msgs::msg::UAVState::SharedPtr msg);

  // ---- control loop (20Hz) ----
  void control_loop();

  // ---- action servers ----
  rclcpp_action::GoalResponse handle_takeoff_goal(
    const rclcpp_action::GoalUUID &, std::shared_ptr<const Takeoff::Goal>);
  rclcpp_action::CancelResponse handle_takeoff_cancel(
    const std::shared_ptr<rclcpp_action::ServerGoalHandle<Takeoff>>);
  void handle_takeoff_accepted(
    const std::shared_ptr<rclcpp_action::ServerGoalHandle<Takeoff>>);

  rclcpp_action::GoalResponse handle_land_goal(
    const rclcpp_action::GoalUUID &, std::shared_ptr<const Land::Goal>);
  rclcpp_action::CancelResponse handle_land_cancel(
    const std::shared_ptr<rclcpp_action::ServerGoalHandle<Land>>);
  void handle_land_accepted(
    const std::shared_ptr<rclcpp_action::ServerGoalHandle<Land>>);

  rclcpp_action::GoalResponse handle_waypoint_goal(
    const rclcpp_action::GoalUUID &, std::shared_ptr<const GoToWaypoint::Goal>);
  rclcpp_action::CancelResponse handle_waypoint_cancel(
    const std::shared_ptr<rclcpp_action::ServerGoalHandle<GoToWaypoint>>);
  void handle_waypoint_accepted(
    const std::shared_ptr<rclcpp_action::ServerGoalHandle<GoToWaypoint>>);

  // ---- service clients ----
  rclcpp::Client<easyfly_msgs::srv::ArmMotors>::SharedPtr     cli_arm_;
  rclcpp::Client<easyfly_msgs::srv::SetFlightMode>::SharedPtr cli_mode_;

  // ---- 独立 callback group (client 与 action 回调分离，避免死锁) ----
  rclcpp::CallbackGroup::SharedPtr cli_cb_group_;
  rclcpp::CallbackGroup::SharedPtr ctl_cb_group_;   // control loop 专用

  // ---- helpers ----
  bool call_arm(bool arm);
  bool call_set_mode(uint8_t mode);
  double clamp(double v, double lo, double hi);

  // ---- subscriptions ----
  rclcpp::Subscription<easyfly_msgs::msg::UAVState>::SharedPtr sub_uav_state_;
  rclcpp::Subscription<mavros_msgs::msg::ExtendedState>::SharedPtr sub_landed_;

  // ---- publisher ----
  rclcpp::Publisher<easyfly_msgs::msg::UAVCommand>::SharedPtr pub_uav_cmd_;

  // ---- timer ----
  rclcpp::TimerBase::SharedPtr timer_ctl_;

  // ---- action servers ----
  rclcpp_action::Server<Takeoff>::SharedPtr      as_takeoff_;
  rclcpp_action::Server<Land>::SharedPtr         as_land_;
  rclcpp_action::Server<GoToWaypoint>::SharedPtr as_waypoint_;

  // ---- latest state ----
  easyfly_msgs::msg::UAVState uav_;
  bool state_received_{false};

  // ---- PID ----
  PID pid_x_, pid_y_, pid_z_, pid_yaw_;

  // ---- active action ----
  enum Action { NONE, TAKEOFF, LANDING, WAYPOINT, HOVER };
  Action active_{NONE};

  // hover 目标位置（takeoff/waypoint 完成后保持的位置）
  double hover_x_{0.0}, hover_y_{0.0}, hover_z_{0.0}, hover_yaw_{0.0};

  // takeoff state
  double takeoff_target_z_{0.0};
  double takeoff_speed_{1.0};
  double takeoff_start_x_{0.0}, takeoff_start_y_{0.0}, takeoff_start_z_{0.0};
  rclcpp::Time takeoff_start_time_;
  rclcpp::Time land_start_time_;
  rclcpp::Time landed_at_;            // 首次检测到触地的时间
  bool         landed_seen_{false};   // 已检测到过触地
  double land_target_x_{0.0}, land_target_y_{0.0}, land_target_z_{0.0};
  double land_start_z_{0.0};
  uint8_t landed_state_{0};
  bool   land_phase2_{false};   // 已切 AUTO.LAND 等待 disarm

  // waypoint state
  double wp_target_x_{0.0}, wp_target_y_{0.0}, wp_target_z_{0.0}, wp_target_yaw_{0.0};
  double wp_max_speed_{2.0};
  double wp_accept_radius_{0.5};
  double wp_start_dist_{0.0};

  // action goal handles
  std::shared_ptr<rclcpp_action::ServerGoalHandle<Takeoff>>      gh_takeoff_;
  std::shared_ptr<rclcpp_action::ServerGoalHandle<Land>>         gh_land_;
  std::shared_ptr<rclcpp_action::ServerGoalHandle<GoToWaypoint>> gh_waypoint_;

  // params
  double ctl_rate_{20.0};
  double land_timeout_{30.0};
};

}  // namespace easyfly_flight_control

#endif  // EASYFLY_FLIGHT_CONTROL_FLIGHT_CONTROLLER_HPP_
