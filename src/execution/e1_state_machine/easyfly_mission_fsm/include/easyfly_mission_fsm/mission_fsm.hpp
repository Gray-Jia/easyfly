#ifndef EASYFLY_MISSION_FSM_MISSION_FSM_HPP_
#define EASYFLY_MISSION_FSM_MISSION_FSM_HPP_

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>

#include <easyfly_msgs/msg/uav_state.hpp>
#include <easyfly_msgs/msg/mission_status.hpp>
#include <easyfly_msgs/action/takeoff.hpp>
#include <easyfly_msgs/action/land.hpp>
#include <easyfly_msgs/action/go_to_waypoint.hpp>
#include <easyfly_msgs/action/execute_mission.hpp>

#include <string>
#include <vector>

namespace easyfly_mission_fsm
{

struct MissionStep
{
  std::string type;        // "takeoff", "waypoint", "land", "hover"
  double altitude{0.0};    // for takeoff target_altitude
  double climb_speed{1.0};
  double x{0.0}, y{0.0}, z{0.0};  // for waypoint
  double yaw{0.0};
  double max_speed{2.0};
  double wait{0.0};        // hover wait time (s)
};

class MissionFSM : public rclcpp::Node
{
public:
  using Takeoff        = easyfly_msgs::action::Takeoff;
  using Land           = easyfly_msgs::action::Land;
  using GoToWaypoint   = easyfly_msgs::action::GoToWaypoint;
  using ExecuteMission = easyfly_msgs::action::ExecuteMission;

  explicit MissionFSM(const rclcpp::NodeOptions & options = rclcpp::NodeOptions());

private:
  // ---- action server ----
  rclcpp_action::Server<ExecuteMission>::SharedPtr as_mission_;

  rclcpp_action::GoalResponse handle_mission_goal(
    const rclcpp_action::GoalUUID &, std::shared_ptr<const ExecuteMission::Goal>);
  rclcpp_action::CancelResponse handle_mission_cancel(
    const std::shared_ptr<rclcpp_action::ServerGoalHandle<ExecuteMission>>);
  void handle_mission_accepted(
    const std::shared_ptr<rclcpp_action::ServerGoalHandle<ExecuteMission>>);

  // ---- action clients ----
  rclcpp_action::Client<Takeoff>::SharedPtr      cli_takeoff_;
  rclcpp_action::Client<Land>::SharedPtr         cli_land_;
  rclcpp_action::Client<GoToWaypoint>::SharedPtr cli_waypoint_;

  // ---- state ----
  void cb_uav_state(const easyfly_msgs::msg::UAVState::SharedPtr msg);

  // ---- mission execution ----
  void execute_mission(const std::string & mission_file,
    std::shared_ptr<rclcpp_action::ServerGoalHandle<ExecuteMission>> gh);
  bool execute_step(const MissionStep & step, int step_idx, int total,
    std::shared_ptr<rclcpp_action::ServerGoalHandle<ExecuteMission>> gh);

  // ---- safety ----
  void safety_check();

  // ---- helpers ----
  std::vector<MissionStep> parse_mission(const std::string & path);
  void publish_status(uint8_t phase, const std::string & name, int wp, int total, float prog);

  // ---- subs ----
  rclcpp::Subscription<easyfly_msgs::msg::UAVState>::SharedPtr sub_uav_state_;

  // ---- pub ----
  rclcpp::Publisher<easyfly_msgs::msg::MissionStatus>::SharedPtr pub_status_;

  // ---- timer ----
  rclcpp::TimerBase::SharedPtr timer_safety_;

  // ---- latest state ----
  easyfly_msgs::msg::UAVState uav_;
  bool state_received_{false};

  // ---- mission state ----
  bool mission_active_{false};
  bool emergency_{false};
};

}  // namespace easyfly_mission_fsm

#endif  // EASYFLY_MISSION_FSM_MISSION_FSM_HPP_
