#include "easyfly_mission_fsm/mission_fsm.hpp"

#include <fstream>
#include <sstream>
#include <chrono>

namespace easyfly_mission_fsm
{

using namespace std::placeholders;
using namespace std::chrono_literals;

// ================================================================
// Constructor
// ================================================================

MissionFSM::MissionFSM(const rclcpp::NodeOptions & options)
  : Node("mission_fsm", options)
{
  // ---- state sub ----
  sub_uav_state_ = create_subscription<easyfly_msgs::msg::UAVState>(
    "/uav_state", rclcpp::SensorDataQoS(),
    std::bind(&MissionFSM::cb_uav_state, this, _1));

  // ---- status pub ----
  pub_status_ = create_publisher<easyfly_msgs::msg::MissionStatus>("/mission_status", 10);

  // ---- action clients ----
  cli_takeoff_   = rclcpp_action::create_client<Takeoff>(this, "/takeoff");
  cli_land_      = rclcpp_action::create_client<Land>(this, "/land");
  cli_waypoint_  = rclcpp_action::create_client<GoToWaypoint>(this, "/goto_waypoint");

  // ---- action server ----
  as_mission_ = rclcpp_action::create_server<ExecuteMission>(
    this, "/execute_mission",
    std::bind(&MissionFSM::handle_mission_goal,   this, _1, _2),
    std::bind(&MissionFSM::handle_mission_cancel, this, _1),
    std::bind(&MissionFSM::handle_mission_accepted, this, _1));

  // ---- safety timer 1Hz ----
  timer_safety_ = create_wall_timer(1s, std::bind(&MissionFSM::safety_check, this));

  RCLCPP_INFO(get_logger(), "MissionFSM started — /execute_mission ready");
}

// ================================================================
// State callback
// ================================================================

void MissionFSM::cb_uav_state(const easyfly_msgs::msg::UAVState::SharedPtr msg)
{
  uav_ = *msg;
  state_received_ = true;
}

// ================================================================
// Safety — 1Hz
// ================================================================

void MissionFSM::safety_check()
{
  if (!state_received_ || !mission_active_) return;

  if (uav_.battery_remaining < 0.15) {
    RCLCPP_WARN(get_logger(), "Battery low (%.0f%%), triggering RTL",
      uav_.battery_remaining * 100);
    emergency_ = true;
    publish_status(easyfly_msgs::msg::MissionStatus::EMERGENCY,
      "emergency", -1, 0, 0.0f);
  }
}

// ================================================================
// Publish mission status
// ================================================================

void MissionFSM::publish_status(uint8_t phase, const std::string & name,
  int wp, int total, float prog)
{
  easyfly_msgs::msg::MissionStatus ms;
  ms.header.stamp = now();
  ms.mission_phase  = phase;
  ms.phase_name     = name;
  ms.current_waypoint = wp;
  ms.total_waypoints  = total;
  ms.progress       = prog;
  ms.mission_success = false;
  pub_status_->publish(ms);
}

// ================================================================
// Action server callbacks
// ================================================================

rclcpp_action::GoalResponse MissionFSM::handle_mission_goal(
  const rclcpp_action::GoalUUID &, std::shared_ptr<const ExecuteMission::Goal> goal)
{
  if (mission_active_) {
    return rclcpp_action::GoalResponse::REJECT;
  }
  if (goal->mission_file.empty()) {
    return rclcpp_action::GoalResponse::REJECT;
  }
  return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
}

rclcpp_action::CancelResponse MissionFSM::handle_mission_cancel(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<ExecuteMission>>)
{
  mission_active_ = false;
  emergency_ = true;
  return rclcpp_action::CancelResponse::ACCEPT;
}

void MissionFSM::handle_mission_accepted(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<ExecuteMission>> gh)
{
  auto goal = gh->get_goal();
  RCLCPP_INFO(get_logger(), "Mission accepted: %s", goal->mission_file.c_str());

  // run in a separate thread so we don't block the action callback
  std::thread([this, gh, goal]() {
    execute_mission(goal->mission_file, gh);
  }).detach();
}

// ================================================================
// YAML parse
// ================================================================

std::vector<MissionStep> MissionFSM::parse_mission(const std::string & path)
{
  std::vector<MissionStep> steps;
  std::ifstream file(path);
  if (!file.is_open()) {
    RCLCPP_ERROR(get_logger(), "Cannot open mission file: %s", path.c_str());
    return steps;
  }

  MissionStep s;
  std::string line;
  while (std::getline(file, line)) {
    // skip comments and empty lines
    if (line.empty() || line[0] == '#') continue;

    // step separator
    std::string trimmed = line;
    trimmed.erase(0, trimmed.find_first_not_of(" \t"));
    trimmed.erase(trimmed.find_last_not_of(" \t") + 1);
    if (trimmed == "---") {
      if (!s.type.empty()) steps.push_back(s);
      s = MissionStep{};
      continue;
    }

    // parse key=value or key:value
    auto eq = line.find('=');
    if (eq == std::string::npos) eq = line.find(':');
    if (eq == std::string::npos) continue;

    std::string key = line.substr(0, eq);
    std::string val = line.substr(eq + 1);

    // trim
    key.erase(0, key.find_first_not_of(" \t"));
    key.erase(key.find_last_not_of(" \t") + 1);
    val.erase(0, val.find_first_not_of(" \t"));
    val.erase(val.find_last_not_of(" \t") + 1);

    if (key == "type") {
      s.type = val;
    } else if (key == "altitude") {
      s.altitude = std::stod(val);
    } else if (key == "climb_speed") {
      s.climb_speed = std::stod(val);
    } else if (key == "x") {
      s.x = std::stod(val);
    } else if (key == "y") {
      s.y = std::stod(val);
    } else if (key == "z") {
      s.z = std::stod(val);
    } else if (key == "yaw") {
      s.yaw = std::stod(val);
    } else if (key == "max_speed") {
      s.max_speed = std::stod(val);
    } else if (key == "wait") {
      s.wait = std::stod(val);
    }
  }
  if (!s.type.empty()) steps.push_back(s);

  RCLCPP_INFO(get_logger(), "Parsed %d steps from %s", (int)steps.size(), path.c_str());
  return steps;
}

// ================================================================
// Mission execution (runs in separate thread)
// ================================================================

void MissionFSM::execute_mission(const std::string & mission_file,
  std::shared_ptr<rclcpp_action::ServerGoalHandle<ExecuteMission>> gh)
{
  mission_active_ = true;
  emergency_ = false;

  auto steps = parse_mission(mission_file);
  int total = static_cast<int>(steps.size());

  if (steps.empty()) {
    auto res = std::make_shared<ExecuteMission::Result>();
    res->success = false;
    res->message = "empty or invalid mission file";
    gh->abort(res);
    mission_active_ = false;
    return;
  }

  RCLCPP_INFO(get_logger(), "Executing mission with %d steps", total);

  for (int i = 0; i < total; ++i) {
    if (emergency_) {
      RCLCPP_WARN(get_logger(), "Emergency stop at step %d", i);
      auto res = std::make_shared<ExecuteMission::Result>();
      res->success = false;
      res->message = "emergency stop";
      gh->abort(res);
      mission_active_ = false;
      return;
    }

    bool ok = execute_step(steps[i], i, total, gh);
    if (!ok) {
      auto res = std::make_shared<ExecuteMission::Result>();
      res->success = false;
      res->message = "step " + std::to_string(i) + " failed: " + steps[i].type;
      gh->abort(res);
      mission_active_ = false;
      return;
    }
  }

  auto res = std::make_shared<ExecuteMission::Result>();
  res->success = true;
  res->message = "mission complete";
  gh->succeed(res);
  mission_active_ = false;
  RCLCPP_INFO(get_logger(), "Mission complete");
}

// ================================================================
// Execute single step
// ================================================================

bool MissionFSM::execute_step(const MissionStep & step, int idx, int total,
  std::shared_ptr<rclcpp_action::ServerGoalHandle<ExecuteMission>> gh)
{
  float prog = static_cast<float>(idx) / std::max(total, 1);

  if (step.type == "takeoff") {
    publish_status(easyfly_msgs::msg::MissionStatus::TAKEOFF, "takeoff", idx, total, prog);

    if (!cli_takeoff_->wait_for_action_server(5s)) {
      RCLCPP_ERROR(get_logger(), "Takeoff action server not available");
      return false;
    }

    auto goal = Takeoff::Goal();
    goal.target_altitude = step.altitude;
    goal.climb_speed = step.climb_speed;

    auto gh_future = cli_takeoff_->async_send_goal(goal);
    if (gh_future.wait_for(60s) != std::future_status::ready) { RCLCPP_ERROR(get_logger(), "Takeoff goal timeout"); return false; }

    auto goal_handle = gh_future.get();
    auto res_future = cli_takeoff_->async_get_result(goal_handle);
    if (res_future.wait_for(120s) != std::future_status::ready) { RCLCPP_ERROR(get_logger(), "Takeoff result timeout"); return false; }
    auto wrapped = res_future.get();
    RCLCPP_INFO(get_logger(), "Takeoff %s", wrapped.result->success ? "OK" : "FAIL");
    return wrapped.result->success;

  } else if (step.type == "waypoint") {
    publish_status(easyfly_msgs::msg::MissionStatus::WAYPOINT, "waypoint", idx, total, prog);

    if (!cli_waypoint_->wait_for_action_server(5s)) {
      RCLCPP_ERROR(get_logger(), "Waypoint action server not available");
      return false;
    }

    auto goal = GoToWaypoint::Goal();
    goal.target_x = step.x;
    goal.target_y = step.y;
    goal.target_z = step.z;
    goal.target_yaw = step.yaw;
    goal.max_speed = step.max_speed;
    goal.acceptance_radius = 0.5;

    auto gh_future = cli_waypoint_->async_send_goal(goal);
    if (gh_future.wait_for(60s) != std::future_status::ready) {
      RCLCPP_ERROR(get_logger(), "Waypoint goal timeout");
      return false;
    }

    auto goal_handle = gh_future.get();
    if (!goal_handle) {
      RCLCPP_ERROR(get_logger(), "Waypoint goal rejected");
      return false;
    }

    auto res_future = cli_waypoint_->async_get_result(goal_handle);
    if (res_future.wait_for(120s) != std::future_status::ready) {
      RCLCPP_ERROR(get_logger(), "Waypoint result timeout");
      return false;
    }
    auto wrapped = res_future.get();
    RCLCPP_INFO(get_logger(), "Waypoint result: success=%d code=%d",
      wrapped.result ? wrapped.result->success : -1,
      static_cast<int>(wrapped.code));
    RCLCPP_INFO(get_logger(), "Waypoint %s", wrapped.result->success ? "OK" : "FAIL");
    return wrapped.result->success;

  } else if (step.type == "land") {
    publish_status(easyfly_msgs::msg::MissionStatus::LAND, "land", idx, total, prog);

    if (!cli_land_->wait_for_action_server(5s)) {
      RCLCPP_ERROR(get_logger(), "Land action server not available");
      return false;
    }

    auto goal = Land::Goal();
    auto gh_future = cli_land_->async_send_goal(goal);
    if (gh_future.wait_for(60s) != std::future_status::ready) { RCLCPP_ERROR(get_logger(), "Land goal timeout"); return false; }

    auto goal_handle = gh_future.get();
    auto res_future = cli_land_->async_get_result(goal_handle);
    if (res_future.wait_for(120s) != std::future_status::ready) { RCLCPP_ERROR(get_logger(), "Land result timeout"); return false; }
    auto wrapped = res_future.get();
    RCLCPP_INFO(get_logger(), "Land %s", wrapped.result->success ? "OK" : "FAIL");
    return wrapped.result->success;

  } else if (step.type == "hover") {
    publish_status(easyfly_msgs::msg::MissionStatus::HOVER, "hover", idx, total, prog);
    RCLCPP_INFO(get_logger(), "Hover %.0fs", step.wait);
    std::this_thread::sleep_for(std::chrono::duration<double>(step.wait));
    return true;
  }

  RCLCPP_WARN(get_logger(), "Unknown step type: %s", step.type.c_str());
  return false;
}

}  // namespace easyfly_mission_fsm
