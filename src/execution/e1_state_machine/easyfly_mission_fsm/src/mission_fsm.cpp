#include "easyfly_mission_fsm/mission_fsm.hpp"

#include <cctype>
#include <cmath>
#include <fstream>
#include <limits>
#include <sstream>
#include <thread>
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

  // ---- Q2: 低电量 RTL 模式切换客户端 (mavlink_bridge 提供) ----
  cli_set_mode_  = create_client<easyfly_msgs::srv::SetFlightMode>("/set_flight_mode");

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

  if (uav_.battery_remaining < 0.15 && !rtl_triggered_) {
    rtl_triggered_ = true;             // 一次性触发, 防止每秒重复
    emergency_     = true;             // 任务线程在步骤边界/轮询点退出
    RCLCPP_ERROR(get_logger(),
      "Battery low (%.0f%%) → 中止任务%s",
      uav_.battery_remaining * 100,
      (uav_.armed && uav_.position_z > 0.3) ? " + 触发 PX4 RTL" : " (在地面, 不需 RTL)");

    // 空中: 交给 PX4 的 RTL (最高可靠路径, 不依赖自家软件链)
    if (uav_.armed && uav_.position_z > 0.3) {
      trigger_rtl();
    }
    // 取消正在执行的子 action (起飞/航点/降落), 让任务线程尽快退出
    cancel_current_step();

    publish_status(easyfly_msgs::msg::MissionStatus::EMERGENCY,
      "emergency_rtl", -1, 0, 0.0f);
  }
}

// ================================================================
// Q2: 请求 mavlink_bridge 将 PX4 切到 RTL (模式 6)
// 异步发送, 不阻塞 1Hz safety timer
// ================================================================

void MissionFSM::trigger_rtl()
{
  if (!cli_set_mode_->wait_for_service(2s)) {
    RCLCPP_ERROR(get_logger(), "/set_flight_mode 服务不可用, RTL 请求失败!");
    return;
  }
  auto req = std::make_shared<easyfly_msgs::srv::SetFlightMode::Request>();
  req->flight_mode = 6;  // RTL
  cli_set_mode_->async_send_request(req);
  RCLCPP_WARN(get_logger(), "已请求 PX4 进入 RTL");
}

// ================================================================
// Q10: 取消当前正在执行的子 action
// ================================================================

void MissionFSM::cancel_current_step()
{
  std::lock_guard<std::mutex> lk(step_mtx_);
  try {
    if (cur_takeoff_gh_) cli_takeoff_->async_cancel_goal(cur_takeoff_gh_);
    if (cur_land_gh_)    cli_land_->async_cancel_goal(cur_land_gh_);
    if (cur_wp_gh_)      cli_waypoint_->async_cancel_goal(cur_wp_gh_);
  } catch (const std::exception & e) {
    RCLCPP_WARN(get_logger(), "取消子 action 异常: %s", e.what());
  }
  cur_takeoff_gh_.reset();
  cur_land_gh_.reset();
  cur_wp_gh_.reset();
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
  // Q10: 立即打断当前步骤 (轮询点退出 + 取消子 action), 由任务线程收尾
  cancel_requested_ = true;
  emergency_        = true;
  cancel_current_step();
  return rclcpp_action::CancelResponse::ACCEPT;
}

void MissionFSM::handle_mission_accepted(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<ExecuteMission>> gh)
{
  auto goal = gh->get_goal();
  RCLCPP_INFO(get_logger(), "Mission accepted: %s", goal->mission_file.c_str());

  // run in a separate thread so we don't block the action callback
  // Q8: 顶层 try/catch — detached thread 中未捕获异常会 std::terminate 杀死整个进程
  std::thread([this, gh, goal]() {
    try {
      execute_mission(goal->mission_file, gh);
    } catch (const std::exception & e) {
      RCLCPP_ERROR(get_logger(), "任务执行异常: %s", e.what());
      try {
        auto res = std::make_shared<ExecuteMission::Result>();
        res->success = false;
        res->message = std::string("internal error: ") + e.what();
        gh->abort(res);
      } catch (...) {}
      mission_active_ = false;
    }
  }).detach();
}

// ================================================================
// YAML parse
// ================================================================

// ================================================================
// Q8: 数值解析保护 — std::stod 遇非数字会抛异常, 此前在 detached
// thread 中未捕获 → std::terminate → 整个 mission_fsm 进程崩溃。
// 非法值返回 NaN, 由调用方判定文件无效并 abort mission。
// ================================================================

double MissionFSM::safe_stod(const std::string & val, const std::string & line)
{
  try {
    size_t pos = 0;
    const double v = std::stod(val, &pos);
    // Q8 加强: std::stod 只解析前缀 ("2.5米"→2.5 不报错!),
    // 必须验证整个字符串被消费, 拒绝任何尾随垃圾
    while (pos < val.size() && std::isspace(static_cast<unsigned char>(val[pos]))) ++pos;
    if (pos != val.size()) {
      RCLCPP_ERROR(get_logger(),
        "任务文件数值含非法字符: '%s' (行: \"%s\")", val.c_str(), line.c_str());
      return std::numeric_limits<double>::quiet_NaN();
    }
    return v;
  } catch (const std::exception &) {
    RCLCPP_ERROR(get_logger(),
      "任务文件数值非法: '%s' (行: \"%s\")", val.c_str(), line.c_str());
    return std::numeric_limits<double>::quiet_NaN();
  }
}

std::vector<MissionStep> MissionFSM::parse_mission(const std::string & path)
{
  std::vector<MissionStep> steps;
  std::ifstream file(path);
  if (!file.is_open()) {
    RCLCPP_ERROR(get_logger(), "Cannot open mission file: %s", path.c_str());
    return steps;
  }

  MissionStep s;
  bool parse_ok = true;
  std::string line;
  int line_no = 0;
  while (std::getline(file, line)) {
    ++line_no;
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
      s.altitude = safe_stod(val, line);
    } else if (key == "climb_speed") {
      s.climb_speed = safe_stod(val, line);
    } else if (key == "x") {
      s.x = safe_stod(val, line);
    } else if (key == "y") {
      s.y = safe_stod(val, line);
    } else if (key == "z") {
      s.z = safe_stod(val, line);
    } else if (key == "yaw") {
      s.yaw = safe_stod(val, line);
    } else if (key == "max_speed") {
      s.max_speed = safe_stod(val, line);
    } else if (key == "wait") {
      s.wait = safe_stod(val, line);
    }
    // Q8: 数值字段有 NaN → 文件无效, 丢弃全部 (防半截任务上天)
    if (std::isnan(s.altitude) || std::isnan(s.climb_speed) || std::isnan(s.x) ||
        std::isnan(s.y) || std::isnan(s.z) || std::isnan(s.yaw) ||
        std::isnan(s.max_speed) || std::isnan(s.wait))
    {
      parse_ok = false;
      break;
    }
  }
  if (parse_ok && !s.type.empty()) steps.push_back(s);

  if (!parse_ok) {
    RCLCPP_ERROR(get_logger(), "Mission file %s 含非法数值 (第 %d 行附近), 拒绝执行", path.c_str(), line_no);
    steps.clear();
    return steps;
  }
  RCLCPP_INFO(get_logger(), "Parsed %d steps from %s", (int)steps.size(), path.c_str());
  return steps;
}

// ================================================================
// Mission execution (runs in separate thread)
// ================================================================

void MissionFSM::execute_mission(const std::string & mission_file,
  std::shared_ptr<rclcpp_action::ServerGoalHandle<ExecuteMission>> gh)
{
  mission_active_    = true;
  emergency_         = false;
  cancel_requested_  = false;
  rtl_triggered_     = false;
  steps_completed_   = 0;

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
    // 步骤边界检查: 用户取消 / 低电量中止
    if (cancel_requested_ || emergency_) break;

    bool ok = execute_step(steps[i], i, total, gh);
    if (!ok) break;
  }

  // ---- 终态统一处理 ----
  auto res = std::make_shared<ExecuteMission::Result>();
  res->success = false;
  try {
    if (cancel_requested_) {
      res->message = "mission cancelled";
      gh->canceled(res);
      RCLCPP_WARN(get_logger(), "Mission cancelled");
    } else if (emergency_) {
      res->message = "emergency stop (low battery RTL)";
      gh->abort(res);
      RCLCPP_WARN(get_logger(), "Mission aborted: emergency");
    } else if (steps_completed_ == total) {
      res->success = true;
      res->message = "mission complete";
      gh->succeed(res);
      RCLCPP_INFO(get_logger(), "Mission complete");
    } else {
      res->message = "step " + std::to_string(steps_completed_) + " failed";
      gh->abort(res);
      RCLCPP_ERROR(get_logger(), "Mission aborted: %s", res->message.c_str());
    }
  } catch (const std::exception & e) {
    // goal 已被客户端放弃等情况 — 只记日志
    RCLCPP_WARN(get_logger(), "设置终态异常(客户端已断开?): %s", e.what());
  }
  mission_active_ = false;
}

// ================================================================
// Execute single step
// ================================================================

bool MissionFSM::execute_step(const MissionStep & step, int idx, int total,
  std::shared_ptr<rclcpp_action::ServerGoalHandle<ExecuteMission>> gh)
{
  float prog = static_cast<float>(idx) / std::max(total, 1);

  // Q10: 轮询等待 future — 期间响应取消/紧急中止 (原 wait_for(120s) 完全不可打断)
  // 返回: 0=ready, 1=timeout, 2=interrupted
  auto poll = [this](auto & fut, std::chrono::steady_clock::duration timeout) -> int {
    const auto t0 = std::chrono::steady_clock::now();
    while (true) {
      if (cancel_requested_ || emergency_) return 2;
      if (fut.wait_for(std::chrono::milliseconds(200)) == std::future_status::ready) return 0;
      if (std::chrono::steady_clock::now() - t0 > timeout) return 1;
    }
  };
  (void)gh;

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
    int st = poll(gh_future, 60s);
    if (st == 2) {
      // 缺陷B修复: 取消落在 goal 接受窗口内时, 子 goal 可能已被接受,
      // 补一次取消 (否则任务中止后飞机会继续执行该步骤)
      if (gh_future.wait_for(1s) == std::future_status::ready) {
        auto gh2 = gh_future.get();
        if (gh2) cli_takeoff_->async_cancel_goal(gh2);
      }
      return false;
    }
    if (st == 1) { RCLCPP_ERROR(get_logger(), "Takeoff goal timeout"); return false; }

    auto goal_handle = gh_future.get();
    // 缺陷C修复: goal 被拒 (如悬停状态发起飞) 时 handle 为空, 必须显式报错
    // (原代码直接 async_get_result(nullptr) 抛晦涩异常 "Goal handle is not known...")
    if (!goal_handle) {
      RCLCPP_ERROR(get_logger(),
        "Takeoff goal 被拒 (flight_control 要求 NONE 状态才可起飞; 当前是否在悬停?)");
      return false;
    }
    { std::lock_guard<std::mutex> lk(step_mtx_); cur_takeoff_gh_ = goal_handle; }

    auto res_future = cli_takeoff_->async_get_result(goal_handle);
    st = poll(res_future, 120s);
    { std::lock_guard<std::mutex> lk(step_mtx_); cur_takeoff_gh_.reset(); }
    if (st == 2) return false;
    if (st == 1) { RCLCPP_ERROR(get_logger(), "Takeoff result timeout"); return false; }

    auto wrapped = res_future.get();
    RCLCPP_INFO(get_logger(), "Takeoff %s", wrapped.result->success ? "OK" : "FAIL");
    if (wrapped.result->success) steps_completed_ = idx + 1;
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
    int st = poll(gh_future, 60s);
    if (st == 2) {
      // 缺陷B修复: 同 takeoff — 取消窗口内已接受的 goal 补取消
      if (gh_future.wait_for(1s) == std::future_status::ready) {
        auto gh2 = gh_future.get();
        if (gh2) cli_waypoint_->async_cancel_goal(gh2);
      }
      return false;
    }
    if (st == 1) { RCLCPP_ERROR(get_logger(), "Waypoint goal timeout"); return false; }

    auto goal_handle = gh_future.get();
    if (!goal_handle) {
      RCLCPP_ERROR(get_logger(), "Waypoint goal rejected");
      return false;
    }
    { std::lock_guard<std::mutex> lk(step_mtx_); cur_wp_gh_ = goal_handle; }

    auto res_future = cli_waypoint_->async_get_result(goal_handle);
    st = poll(res_future, 120s);
    { std::lock_guard<std::mutex> lk(step_mtx_); cur_wp_gh_.reset(); }
    if (st == 2) return false;
    if (st == 1) { RCLCPP_ERROR(get_logger(), "Waypoint result timeout"); return false; }

    auto wrapped = res_future.get();
    RCLCPP_INFO(get_logger(), "Waypoint result: success=%d code=%d",
      wrapped.result ? wrapped.result->success : -1,
      static_cast<int>(wrapped.code));
    RCLCPP_INFO(get_logger(), "Waypoint %s", wrapped.result->success ? "OK" : "FAIL");
    if (wrapped.result->success) steps_completed_ = idx + 1;
    return wrapped.result->success;

  } else if (step.type == "land") {
    publish_status(easyfly_msgs::msg::MissionStatus::LAND, "land", idx, total, prog);

    if (!cli_land_->wait_for_action_server(5s)) {
      RCLCPP_ERROR(get_logger(), "Land action server not available");
      return false;
    }

    auto goal = Land::Goal();
    auto gh_future = cli_land_->async_send_goal(goal);
    int st = poll(gh_future, 60s);
    if (st == 2) {
      // 缺陷B修复: 同 takeoff — 取消窗口内已接受的 goal 补取消
      if (gh_future.wait_for(1s) == std::future_status::ready) {
        auto gh2 = gh_future.get();
        if (gh2) cli_land_->async_cancel_goal(gh2);
      }
      return false;
    }
    if (st == 1) { RCLCPP_ERROR(get_logger(), "Land goal timeout"); return false; }

    auto goal_handle = gh_future.get();
    if (!goal_handle) {   // 缺陷C: 同 takeoff — 判空防晦涩异常
      RCLCPP_ERROR(get_logger(), "Land goal 被拒 (要求 HOVER 状态)");
      return false;
    }
    { std::lock_guard<std::mutex> lk(step_mtx_); cur_land_gh_ = goal_handle; }

    auto res_future = cli_land_->async_get_result(goal_handle);
    st = poll(res_future, 90s);
    { std::lock_guard<std::mutex> lk(step_mtx_); cur_land_gh_.reset(); }
    if (st == 2) return false;
    if (st == 1) { RCLCPP_ERROR(get_logger(), "Land result timeout"); return false; }

    auto wrapped = res_future.get();
    RCLCPP_INFO(get_logger(), "Land %s", wrapped.result->success ? "OK" : "FAIL");
    if (wrapped.result->success) steps_completed_ = idx + 1;
    return wrapped.result->success;

  } else if (step.type == "hover") {
    publish_status(easyfly_msgs::msg::MissionStatus::HOVER, "hover", idx, total, prog);
    RCLCPP_INFO(get_logger(), "Hover %.0fs", step.wait);
    // Q10: 可中断等待 (原 sleep_for 整段阻塞, 取消最长卡 wait 秒)
    const auto t0 = std::chrono::steady_clock::now();
    while (std::chrono::steady_clock::now() - t0 < std::chrono::duration<double>(step.wait)) {
      if (cancel_requested_ || emergency_) return false;
      std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    steps_completed_ = idx + 1;
    return true;
  }

  RCLCPP_WARN(get_logger(), "Unknown step type: %s", step.type.c_str());
  return false;
}

}  // namespace easyfly_mission_fsm
