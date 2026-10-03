#include "easyfly_flight_control/flight_controller.hpp"
#include <cmath>
#include <chrono>
#include <thread>

namespace easyfly_flight_control
{
using namespace std::placeholders;
using namespace std::chrono_literals;

// 注: PID 实现已移除 (Q1) — 控制策略为 setpoint 生成 + PX4 OFFBOARD 内环闭环,
// 原 PID::update 从未被调用, 属死代码。

FlightController::FlightController(const rclcpp::NodeOptions & options)
  : Node("flight_controller", options)
{
  ctl_rate_ = declare_parameter("control_rate", 20.0);
  land_timeout_ = declare_parameter("land_timeout", 60.0);
  max_altitude_ = declare_parameter("max_altitude", 50.0);
  max_horizontal_speed_ = declare_parameter("max_horizontal_speed", 20.0);
  max_goal_distance_ = declare_parameter("max_goal_distance", 100.0);
  const double configured_traj_startup_grace = declare_parameter(
    "trajectory_startup_grace", kDefaultTrajectoryStartupGrace);
  traj_startup_grace_ = sanitizeTrajectoryStartupGrace(configured_traj_startup_grace);
  if (traj_startup_grace_ != configured_traj_startup_grace) {
    RCLCPP_WARN(
      get_logger(),
      "trajectory_startup_grace=%.3fs 无效或超出 [%.1f, %.1f]，回退安全默认 %.1fs",
      configured_traj_startup_grace, kMinTrajectoryStartupGrace,
      kMaxTrajectoryStartupGrace, kDefaultTrajectoryStartupGrace);
  }
  RCLCPP_INFO(
    get_logger(),
    "FollowTrajectory watchdog: startup grace=%.2fs, post-start stream timeout=%.2fs",
    traj_startup_grace_, traj_stream_timeout_);
  auto period = std::chrono::milliseconds(static_cast<int>(1000.0 / ctl_rate_));
  auto qos = rclcpp::QoS(10);

  // Q9 修复: 状态订阅独立回调组 — handle_*_accepted 中的阻塞调用
  // (call_arm/wait_mode_engaged 等) 若与订阅同组, 会饿死 /uav_state 更新,
  // 导致模式校验读到永久 stale 的旧模式 (实测: OFFBOARD 已切入仍判定失败)
  state_cb_group_ = create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
  rclcpp::SubscriptionOptions sub_opts;
  sub_opts.callback_group = state_cb_group_;
  sub_uav_state_ = create_subscription<easyfly_msgs::msg::UAVState>(
    "/uav_state", rclcpp::SensorDataQoS(),
    std::bind(&FlightController::cb_uav_state, this, _1),
    sub_opts);
  pub_uav_cmd_ = create_publisher<easyfly_msgs::msg::UAVCommand>("/uav_command", qos);

  // M4.3: EGO-Planner 轨迹流 (traj_server 100Hz); 独立回调组, 避免被 action 阻塞饿死
  sub_position_cmd_ = create_subscription<quadrotor_msgs::msg::PositionCommand>(
    "/position_cmd", rclcpp::SensorDataQoS(),
    std::bind(&FlightController::cb_position_cmd, this, _1),
    sub_opts);

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
  as_traj_ = rclcpp_action::create_server<FollowTrajectory>(this, "/follow_trajectory",
    std::bind(&FlightController::handle_traj_goal,   this, _1, _2),
    std::bind(&FlightController::handle_traj_cancel, this, _1),
    std::bind(&FlightController::handle_traj_accepted, this, _1));

  ctl_cb_group_ = create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
  timer_ctl_ = create_wall_timer(period, std::bind(&FlightController::control_loop, this), ctl_cb_group_);
  RCLCPP_INFO(get_logger(), "FlightController Start");
}

void FlightController::cb_uav_state(const easyfly_msgs::msg::UAVState::SharedPtr msg)
{
  if (!msg || !std::isfinite(msg->position_x) || !std::isfinite(msg->position_y) ||
      !std::isfinite(msg->position_z) || !std::isfinite(msg->yaw) ||
      !std::isfinite(msg->velocity_x) || !std::isfinite(msg->velocity_y) ||
      !std::isfinite(msg->velocity_z)) {
    RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 1000,
      "拒绝无效 /uav_state: 位姿或速度包含非有限值");
    return;
  }
  {  // Q9: 与 control_loop / 模式校验轮询的跨线程读写保护
    std::lock_guard<std::mutex> lk(state_mtx_);
    uav_ = *msg;
  }
  state_received_ = true;
}

// M4.3: EGO /position_cmd 快照 (TRAJECTORY 模式下由 control_loop 转发)
void FlightController::cb_position_cmd(
  const quadrotor_msgs::msg::PositionCommand::SharedPtr msg)
{
  // 仅接受 READY 轨迹 (ego traj_server 在无轨迹时不发布; 该判定是双保险)
  if (msg->trajectory_flag !=
      quadrotor_msgs::msg::PositionCommand::TRAJECTORY_STATUS_READY) {
    return;
  }
  if (msg->header.frame_id != "odom" ||
      !std::isfinite(msg->position.x) || !std::isfinite(msg->position.y) ||
      !std::isfinite(msg->position.z) || !std::isfinite(msg->velocity.x) ||
      !std::isfinite(msg->velocity.y) || !std::isfinite(msg->velocity.z) ||
      !std::isfinite(msg->yaw)) {
    RCLCPP_ERROR_THROTTLE(get_logger(), *get_clock(), 1000,
      "拒绝 /position_cmd: frame 必须为 odom 且控制值必须有限");
    return;
  }
  const rclcpp::Time msg_time(msg->header.stamp, get_clock()->get_clock_type());
  const auto receipt_time = now();
  const double age = (receipt_time - msg_time).seconds();
  if (msg_time.nanoseconds() == 0 || age < -0.2 || age > 1.0) {
    RCLCPP_ERROR_THROTTLE(get_logger(), *get_clock(), 1000,
      "拒绝 /position_cmd: 时间戳无效或过期 (age=%.3fs)", age);
    return;
  }

  std::lock_guard<std::recursive_mutex> state_lk(flight_mtx_);
  // goal response 到 accepted callback 之间仍处于 HOVER；这段窗口内的
  // 消息不能改变基线，否则同一条 N+1 会在真正进入 WAIT 后被当作旧帧。
  if (traj_goal_pending_) return;

  // 只有通过 active/time/ID 检查的候选才允许推进 seen 水位。没有 active
  // trajectory 时则是有意观测（用于下一次 goal 的 baseline），但不能把
  // WAIT 的旧帧、时间过期帧或 ACTIVE 的回退帧计入最大 ID。
  const bool waiting_for_first_frame = active_ == TRAJECTORY_WAIT;
  const uint32_t wait_id_watermark =
    std::max(traj_baseline_id_, traj_seen_max_id_);
  const bool advances_wait_watermark =
    !waiting_for_first_frame || msg->trajectory_id > wait_id_watermark;

  if (active_ != TRAJECTORY_WAIT && active_ != TRAJECTORY) {
    traj_seen_max_id_ = std::max(traj_seen_max_id_, msg->trajectory_id);
    return;
  }
  if (msg_time + rclcpp::Duration::from_seconds(0.02) < traj_accept_time_) return;
  if (waiting_for_first_frame) {
    // Re-check with the ROS clock while holding the state lock.  A frame may
    // have arrived before the deadline but wait behind control_loop; it must
    // not activate a trajectory after the bounded startup/deadline window.
    const auto wait_check_time = now();
    const double startup_gap = (wait_check_time - traj_accept_time_).seconds();
    const double action_deadline_seconds =
      (traj_deadline_ - traj_accept_time_).seconds();
    if (trajectoryStartupTimedOut(
        startup_gap, traj_startup_grace_, action_deadline_seconds)) {
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 1000,
        "拒绝过期首帧 /position_cmd: gap=%.2fs, action deadline=%.2fs",
        startup_gap, action_deadline_seconds);
      return;
    }
  }
  if (waiting_for_first_frame && !advances_wait_watermark) return;
  if (active_ == TRAJECTORY && msg->trajectory_id < traj_active_id_) return;
  traj_seen_max_id_ = std::max(traj_seen_max_id_, msg->trajectory_id);
  std::lock_guard<std::mutex> lk(traj_mtx_);
  latest_cmd_ = *msg;
  traj_cmd_time_ = receipt_time;
  traj_active_id_ = msg->trajectory_id;
  traj_cmd_received_.store(true);
  active_ = TRAJECTORY;
}

easyfly_msgs::msg::UAVState FlightController::get_uav() const
{
  std::lock_guard<std::mutex> lk(state_mtx_);
  return uav_;
}

void FlightController::control_loop()
{
  if (!state_received_) return;
  std::lock_guard<std::recursive_mutex> state_lk(flight_mtx_);
  const auto uav = get_uav();          // 快照, 本周期内一致

  // Q12: 实测周期 (替代固定 1/rate), 限幅防极端值 (调度抖动/时钟跳变)
  const auto t_now = now();
  double dt = 1.0 / ctl_rate_;
  if (last_ctl_time_.nanoseconds() > 0) {
    dt = std::clamp((t_now - last_ctl_time_).seconds(),
                    0.5 / ctl_rate_, 2.0 / ctl_rate_);
  }
  last_ctl_time_ = t_now;

  easyfly_msgs::msg::UAVCommand cmd;
  cmd.control_mode = easyfly_msgs::msg::UAVCommand::POSITION;
  stamp_command(cmd);

  // cancel callback 返回 ACCEPT 后，rcl_action 才会把 goal 从 EXECUTING
  // 转入 CANCELING。终态必须在这里观察到 is_canceling() 后设置，不能在
  // cancel callback 内同步调用 canceled()，否则会触发非法状态迁移并杀死节点。
  if ((active_ == TAKEOFF_PREPARING || active_ == TAKEOFF) &&
      gh_takeoff_ && gh_takeoff_->is_canceling()) {
    auto gh = gh_takeoff_;
    if (uav.armed) {
      enter_hover_at(
        safe_axis(uav.position_x, takeoff_start_x_),
        safe_axis(uav.position_y, takeoff_start_y_),
        safe_axis(uav.position_z, takeoff_ramp_z_), takeoff_start_yaw_);
    } else {
      active_ = NONE;
      action_reserved_ = false;
    }
    auto r = std::make_shared<Takeoff::Result>();
    r->success = false; r->message = "canceled";
    gh->canceled(r);
    gh_takeoff_.reset();
    return;
  }
  if (active_ == WAYPOINT && gh_waypoint_ && gh_waypoint_->is_canceling()) {
    auto gh = gh_waypoint_;
    enter_hover_at(
      safe_axis(uav.position_x, x_ramp_),
      safe_axis(uav.position_y, y_ramp_),
      safe_axis(uav.position_z, z_ramp_), wp_target_yaw_);
    auto r = std::make_shared<GoToWaypoint::Result>();
    r->success = false; r->message = "canceled";
    gh->canceled(r);
    gh_waypoint_.reset();
    return;
  }
  if ((active_ == TRAJECTORY_WAIT || active_ == TRAJECTORY) &&
      gh_traj_ && gh_traj_->is_canceling()) {
    auto gh = gh_traj_;
    bool have_cmd;
    quadrotor_msgs::msg::PositionCommand c;
    {
      std::lock_guard<std::mutex> lk(traj_mtx_);
      have_cmd = traj_cmd_received_.load();
      c = latest_cmd_;
    }
    if (have_cmd) {
      enter_hover_at(
        safe_axis(uav.position_x, c.position.x),
        safe_axis(uav.position_y, c.position.y),
        safe_axis(uav.position_z, c.position.z), c.yaw);
    } else {
      enter_hover_at(uav.position_x, uav.position_y, uav.position_z, uav.yaw);
    }
    auto r = std::make_shared<FollowTrajectory::Result>();
    r->success = false; r->message = "canceled";
    gh->canceled(r);
    gh_traj_.reset();
    return;
  }
  if (active_ == LAND_CANCELING) {
    // cancel callback 正在恢复 OFFBOARD；整个事务期间持续供给悬停 setpoint。
    cmd.position_x = hover_x_; cmd.position_y = hover_y_;
    cmd.position_z = hover_z_; cmd.yaw = hover_yaw_;
    pub_uav_cmd_->publish(cmd);
    if (gh_land_ && gh_land_->is_canceling()) {
      auto gh = gh_land_;
      active_ = HOVER;
      action_reserved_ = false;
      auto r = std::make_shared<Land::Result>();
      r->success = false; r->message = "canceled";
      gh->canceled(r);
      gh_land_.reset();
    }
    return;
  }

  // ---- 外部接管检测 (TAKEOFF/WAYPOINT/HOVER 通用; LANDING 除外—那是我们自己切的 AUTO.LAND) ----
  // 场景: mission_fsm 低电量 RTL / 地面站手动切 RTL(6)/AUTO.LAND(7) / PX4 failsafe。
  // 缺陷修复: 原检测仅在 HOVER 分支 — RTL 发生在航点/起飞中时, 节点会卡在该状态
  // 直到 deadline 超时 (误导性日志 + 期间无法接受新 goal)。现在任何主动状态都检测。
  // 1.5s 去抖: 模式反馈链 (PX4→mavros→bridge→uav_state) 有 ~1s 延迟,
  // 取消降落等主动切回 OFFBOARD 的场景, 窗口期内 mode 仍读旧值, 不能误判接管
  const bool takeover_candidate =
    (active_ == TAKEOFF_PREPARING || active_ == TAKEOFF || active_ == WAYPOINT ||
     active_ == HOVER || active_ == TRAJECTORY_WAIT || active_ == TRAJECTORY) &&
    (uav.flight_mode == 6 || uav.flight_mode == 7);
  // LAND_PREPARING 是 AUTO.LAND 请求/确认事务；mode=7 在此阶段是预期状态，
  // 不能被通用 takeover 分支当作外部接管清掉 reservation。若此时转成 RTL，
  // 则仍按外部接管中止该事务。
  const bool land_preparing_takeover = active_ == LAND_PREPARING && uav.flight_mode == 6;
  if (takeover_candidate || land_preparing_takeover) {
      if (takeover_since_.nanoseconds() == 0) {
        takeover_since_ = now();
      } else if ((now() - takeover_since_).seconds() > 1.5) {
        RCLCPP_WARN(get_logger(),
          "检测到外部模式接管 (mode=%d, RTL/AUTO.LAND), 中止当前动作, 停止 setpoint",
          static_cast<int>(uav.flight_mode));
        // 终止当前 goal (如还在)
        try {
          if ((active_ == TAKEOFF_PREPARING || active_ == TAKEOFF) && gh_takeoff_) {
            finish_takeoff_goal(gh_takeoff_, "external takeover (RTL/AUTO.LAND)");
          } else if (active_ == WAYPOINT && gh_waypoint_) {
            finish_waypoint_goal(gh_waypoint_, "external takeover (RTL/AUTO.LAND)");
          } else if ((active_ == TRAJECTORY_WAIT || active_ == TRAJECTORY) && gh_traj_) {
            finish_traj_goal(gh_traj_, "takeover");
          } else if (active_ == LAND_PREPARING && gh_land_) {
            finish_land_goal(gh_land_, "external takeover (RTL)", false);
          }
        } catch (const std::exception &) {}
        if (active_ != LAND_PREPARING && active_ != LANDING) {
          active_ = NONE;
          action_reserved_ = false;
        }
        takeover_since_ = rclcpp::Time(0, 0, now().get_clock_type());
      }
  } else {
    // AUTO.LAND confirmation is an expected mode transition, so it must not
    // accumulate a takeover debounce window.
    takeover_since_ = rclcpp::Time(0, 0, now().get_clock_type());
  }
  if (active_ == LAND_PREPARING) {
    // AUTO.LAND 请求/确认期间仍保持锁存的 hover setpoint，直到 accepted
    // callback 确认 PX4 已进入 LANDING。这样模式服务阻塞或确认延迟时，
    // OFFBOARD 数据流不会中断，也不会用实时反馈覆盖发起降落前的悬停点。
    cmd.position_x = hover_x_; cmd.position_y = hover_y_;
    cmd.position_z = hover_z_; cmd.yaw = hover_yaw_;
    pub_uav_cmd_->publish(cmd);
    return;
  }
  if (active_ == NONE || active_ == LANDING) {
    // 接管/降落中: 不再发布 OFFBOARD setpoint
    if (active_ == LANDING && gh_land_) {
      auto fb = std::make_shared<Land::Feedback>();
      fb->current_altitude = uav.position_z; gh_land_->publish_feedback(fb);
      const double t = (now() - land_start_time_).seconds();
      if (!uav.armed) {
        auto r = std::make_shared<Land::Result>(); r->success = true;
        r->message = "landed"; gh_land_->succeed(r); gh_land_.reset();
        // 注: 不做模式清理 — PX4 降落后自行停留/回退模式 (OFFBOARD 等),
        // 任何残留模式的再解锁由 takeoff 的 "先建流后解锁" 流程统一处理
        active_ = NONE;
        action_reserved_ = false;
      } else if (t > land_timeout_) {
        // Q6: 超时处理 — 只允许已落地(z<0.3)时 disarm;
        // 空中强制 disarm = 电机停转 = 自由落体, 严禁!
        if (uav.position_z < 0.3) {
          call_arm(false);
          auto r = std::make_shared<Land::Result>(); r->success = true;
          r->message = "landed (timeout, on ground)"; gh_land_->succeed(r); gh_land_.reset();
        } else {
          RCLCPP_ERROR(get_logger(),
            "Land timeout 但仍在空中 (z=%.2f) — 不 disarm, 交由 PX4 AUTO.LAND 继续降落",
            uav.position_z);
          auto r = std::make_shared<Land::Result>();
          r->success = false; r->message = "land timeout (still airborne, AUTO.LAND continues)";
          gh_land_->abort(r); gh_land_.reset();
        }
        active_ = NONE;
        action_reserved_ = false;
      }
    }
    return;
  }

  if (active_ == TAKEOFF_PREPARING) {
    // 切 OFFBOARD / arm 确认前只维持地面当前位置，不开始爬升计时。
    cmd.position_x = takeoff_start_x_; cmd.position_y = takeoff_start_y_;
    cmd.position_z = takeoff_start_z_; cmd.yaw = takeoff_start_yaw_;
    pub_uav_cmd_->publish(cmd);
  } else if (active_ == TAKEOFF) {
    const double t = (now() - takeoff_start_time_).seconds();
    const double tz = std::min(takeoff_start_z_ + t * takeoff_speed_, takeoff_target_z_);
    takeoff_ramp_z_ = tz;              // Q4/Q5: 记录渐近高度供取消/超时悬停用
    cmd.position_x = takeoff_start_x_; cmd.position_y = takeoff_start_y_;
    cmd.position_z = tz;
    cmd.yaw = takeoff_start_yaw_;      // Q7: 锁存值, 不取反馈 (防姿态毛刺)
    pub_uav_cmd_->publish(cmd);
    if (gh_takeoff_ && std::abs(takeoff_target_z_ - uav.position_z) < 0.5) {
      auto r = std::make_shared<Takeoff::Result>(); r->success = true;
      gh_takeoff_->succeed(r); gh_takeoff_.reset();
      hover_x_ = takeoff_start_x_; hover_y_ = takeoff_start_y_;
      hover_z_ = takeoff_target_z_; hover_yaw_ = takeoff_start_yaw_;
      x_ramp_ = takeoff_start_x_; y_ramp_ = takeoff_start_y_; z_ramp_ = takeoff_target_z_;
      active_ = HOVER;
      action_reserved_ = false;
    } else if (gh_takeoff_ && now() > takeoff_deadline_) {
      // Q5: 超时保护 — 之前会永远 pending, 卡死后续所有 goal
      RCLCPP_ERROR(get_logger(), "Takeoff timeout (z=%.2f / target %.2f), abort + 就地悬停",
        uav.position_z, takeoff_target_z_);
      auto r = std::make_shared<Takeoff::Result>();
      r->success = false; r->message = "takeoff timeout";
      gh_takeoff_->abort(r); gh_takeoff_.reset();
      enter_hover_at(takeoff_start_x_, takeoff_start_y_, takeoff_ramp_z_, takeoff_start_yaw_);
    }
  } else if (active_ == WAYPOINT) {
    const double ex = wp_target_x_ - uav.position_x, ey = wp_target_y_ - uav.position_y;
    const double ez = wp_target_z_ - uav.position_z;
    double dist = std::sqrt(ex*ex + ey*ey + ez*ez);
    // 全轴目标渐近式: setpoint 从起点直线渐近目标, 不依赖 local_position 反馈
    // (M6 踩坑: mavros local_position 偶发大幅毛刺如 z=-10, 增量跟随式控制
    //  cmd=feedback+Δ 会把毛刺写进 setpoint 造成正反馈发散)
    double dirx = wp_target_x_ - wp_start_x_, diry = wp_target_y_ - wp_start_y_;
    double L = std::sqrt(dirx*dirx + diry*diry);
    if (L > 1e-6) { dirx /= L; diry /= L; } else { dirx = 1; diry = 0; }
    double step = wp_max_speed_ * dt;
    double prog = std::hypot(x_ramp_ - wp_start_x_, y_ramp_ - wp_start_y_);
    double new_prog = std::min(prog + step, L);
    x_ramp_ = wp_start_x_ + dirx * new_prog;
    y_ramp_ = wp_start_y_ + diry * new_prog;
    z_ramp_ += std::clamp(wp_target_z_ - z_ramp_, -step, step);
    cmd.position_x = x_ramp_;
    cmd.position_y = y_ramp_;
    cmd.position_z = z_ramp_;
    cmd.yaw = wp_target_yaw_;
    // 距离仅用于完成判定 (基于真实反馈, 但毛刺只影响判定不影响 setpoint)
    pub_uav_cmd_->publish(cmd);

    // Q16: 完成判定去抖 — 双条件同时满足:
    //   ① ramp 已走完 (setpoint 已停在目标点: 水平到位 && z 到位)
    //   ② 连续 5 帧 (0.25s) 反馈在验收半径内 (单帧毛刺尖峰被滤除)
    const bool ramp_done =
      (new_prog >= L - 1e-6) && std::abs(z_ramp_ - wp_target_z_) < 1e-6;
    if (dist < wp_accept_radius_) ++wp_in_radius_frames_;
    else                          wp_in_radius_frames_ = 0;

    if (gh_waypoint_ && ramp_done && wp_in_radius_frames_ >= 5) {
      auto r = std::make_shared<GoToWaypoint::Result>(); r->success = true;
      gh_waypoint_->succeed(r); gh_waypoint_.reset();
      hover_x_ = wp_target_x_; hover_y_ = wp_target_y_;
      hover_z_ = wp_target_z_; hover_yaw_ = wp_target_yaw_;
      active_ = HOVER;
      action_reserved_ = false;
    } else if (gh_waypoint_ && now() > wp_deadline_) {
      // Q5: 超时保护 — abort + 就地悬停 (当前位置优先, 毛刺守卫同 Q4)
      RCLCPP_ERROR(get_logger(), "Waypoint timeout (dist=%.2f), abort + 就地悬停", dist);
      auto r = std::make_shared<GoToWaypoint::Result>();
      r->success = false; r->message = "waypoint timeout";
      gh_waypoint_->abort(r); gh_waypoint_.reset();
      enter_hover_at(
        safe_axis(uav.position_x, x_ramp_),
        safe_axis(uav.position_y, y_ramp_),
        safe_axis(uav.position_z, z_ramp_),
        wp_target_yaw_);
    }
  } else if (active_ == HOVER) {
    // 接管检测已上移至函数开头 (TAKEOFF/WAYPOINT/HOVER 通用)
    if (uav.armed) {
      cmd.position_x = hover_x_; cmd.position_y = hover_y_;
      cmd.position_z = hover_z_; cmd.yaw = hover_yaw_;
      pub_uav_cmd_->publish(cmd);
    }
  } else if (active_ == TRAJECTORY_WAIT) {
    // 等首帧期间保持进入轨迹前的悬停点，绝不读取默认 PositionCommand。
    cmd.position_x = hover_x_; cmd.position_y = hover_y_;
    cmd.position_z = hover_z_; cmd.yaw = hover_yaw_;
    pub_uav_cmd_->publish(cmd);
    const auto wait_now = now();
    const double gap = (wait_now - traj_accept_time_).seconds();
    const double action_deadline_seconds =
      (traj_deadline_ - traj_accept_time_).seconds();
    const double action_remaining = (traj_deadline_ - wait_now).seconds();
    if (trajectoryStartupTimedOut(
        gap, traj_startup_grace_, action_deadline_seconds)) {
      const bool action_deadline_elapsed =
        !std::isfinite(action_remaining) || action_remaining <= 0.0;
      RCLCPP_ERROR(
        get_logger(),
        "FollowTrajectory 首帧超时: gap=%.2fs, startup grace=%.2fs, "
        "action remaining=%.2fs (%s; 首帧后流断门仍为 %.2fs)",
        gap, traj_startup_grace_, action_remaining,
        action_deadline_elapsed ? "action deadline" : "startup grace",
        traj_stream_timeout_);
      if (gh_traj_) {
        auto r = std::make_shared<FollowTrajectory::Result>();
        r->success = false;
        r->message = action_deadline_elapsed ?
          "trajectory_timeout_before_start" : "trajectory_start_timeout";
        gh_traj_->abort(r); gh_traj_.reset();
      }
      action_reserved_ = false;
      active_ = HOVER;
    }
  } else if (active_ == TRAJECTORY) {
    // ---- M4.3: 转发 EGO /position_cmd (位置+速度前馈+yaw) ----
    bool have_cmd;
    quadrotor_msgs::msg::PositionCommand c;
    rclcpp::Time t_cmd;
    {
      std::lock_guard<std::mutex> lk(traj_mtx_);
      have_cmd = traj_cmd_received_.load();
      c = latest_cmd_;
      t_cmd = traj_cmd_time_;
    }
    const auto trajectory_now = now();
    const double action_gap = (trajectory_now - traj_accept_time_).seconds();
    const double action_deadline_seconds =
      (traj_deadline_ - traj_accept_time_).seconds();
    // The command must be checked before any TRAJECTORY setpoint is
    // published.  This closes the boundary race where a late callback
    // activates the state just after the action deadline.
    if (trajectoryDeadlineExpired(action_gap, action_deadline_seconds)) {
      RCLCPP_ERROR(
        get_logger(),
        "FollowTrajectory action deadline reached before publish "
        "(gap=%.2fs, deadline=%.2fs) → 就地悬停 + abort",
        action_gap, action_deadline_seconds);
      if (gh_traj_) {
        auto r = std::make_shared<FollowTrajectory::Result>();
        r->success = false; r->message = "timeout";
        gh_traj_->abort(r); gh_traj_.reset();
      }
      if (have_cmd) {
        enter_hover_at(
          safe_axis(uav.position_x, c.position.x),
          safe_axis(uav.position_y, c.position.y),
          safe_axis(uav.position_z, c.position.z),
          c.yaw);
      } else {
        enter_hover_at(uav.position_x, uav.position_y, uav.position_z, uav.yaw);
      }
      return;
    }

    // 流断判定: 已流过 → >=traj_stream_timeout_ 无新帧; 从未流过 → >=起始宽限
    const double gap = have_cmd ? (trajectory_now - t_cmd).seconds()
                                : action_gap;
    const bool stream_lost = trajectoryStreamLost(
      have_cmd, gap, traj_startup_grace_, traj_stream_timeout_);
    if (stream_lost) {
      RCLCPP_ERROR(get_logger(),
        "FollowTrajectory 流断 (%.2fs 无 /position_cmd) → 就地悬停 + abort", gap);
      if (gh_traj_) {
        auto r = std::make_shared<FollowTrajectory::Result>();
        r->success = false; r->message = "stream_lost";
        gh_traj_->abort(r); gh_traj_.reset();
      }
      if (have_cmd) {
        // 悬停于最后指令点 (反馈毛刺守卫)
        enter_hover_at(
          safe_axis(uav.position_x, c.position.x),
          safe_axis(uav.position_y, c.position.y),
          safe_axis(uav.position_z, c.position.z),
          c.yaw);
      } else {
        enter_hover_at(uav.position_x, uav.position_y, uav.position_z, uav.yaw);
      }
      return;
    }

    if (gh_traj_) {
      // 转发为 TRAJECTORY 指令 (ENU 直传; 换轴由 mavros 在 setpoint_raw 内完成)
      cmd.control_mode = easyfly_msgs::msg::UAVCommand::TRAJECTORY;
      cmd.position_x = c.position.x;
      cmd.position_y = c.position.y;
      cmd.position_z = c.position.z;
      cmd.velocity_x = c.velocity.x;
      cmd.velocity_y = c.velocity.y;
      cmd.velocity_z = c.velocity.z;
      cmd.yaw        = c.yaw;
      pub_uav_cmd_->publish(cmd);

      const double dx = traj_target_x_ - uav.position_x;
      const double dy = traj_target_y_ - uav.position_y;
      const double dz = traj_target_z_ - uav.position_z;
      const double dist = std::sqrt(dx * dx + dy * dy + dz * dz);

      auto fb = std::make_shared<FollowTrajectory::Feedback>();
      fb->distance_remaining = dist;
      fb->stream_active = true;
      gh_traj_->publish_feedback(fb);

      // Keep the action boundary fail-safe even if the control tick crossed
      // it while publishing the last valid command.
      if (trajectoryDeadlineExpired(
          (now() - traj_accept_time_).seconds(), action_deadline_seconds)) {
        RCLCPP_ERROR(get_logger(),
          "FollowTrajectory 超时 (dist=%.2f), abort + 就地悬停", dist);
        auto r = std::make_shared<FollowTrajectory::Result>();
        r->success = false; r->message = "timeout";
        gh_traj_->abort(r); gh_traj_.reset();
        enter_hover_at(
          safe_axis(uav.position_x, c.position.x),
          safe_axis(uav.position_y, c.position.y),
          safe_axis(uav.position_z, c.position.z),
          c.yaw);
        return;
      }

      if (dist < traj_accept_radius_) ++traj_in_radius_frames_;
      else                            traj_in_radius_frames_ = 0;

      if (traj_in_radius_frames_ >= 5) {
        RCLCPP_INFO(get_logger(), "FollowTrajectory 到达终点 (dist=%.2f)", dist);
        auto r = std::make_shared<FollowTrajectory::Result>();
        r->success = true; r->message = "arrived";
        gh_traj_->succeed(r); gh_traj_.reset();
        hover_x_ = traj_target_x_; hover_y_ = traj_target_y_;
        hover_z_ = traj_target_z_; hover_yaw_ = c.yaw;
        x_ramp_ = traj_target_x_; y_ramp_ = traj_target_y_; z_ramp_ = traj_target_z_;
        active_ = HOVER;
        action_reserved_ = false;
      }
    }
  }
}

rclcpp_action::GoalResponse FlightController::handle_takeoff_goal(
  const rclcpp_action::GoalUUID &, std::shared_ptr<const Takeoff::Goal> g)
{
  if (!std::isfinite(g->target_altitude) || !std::isfinite(g->climb_speed) ||
      g->target_altitude <= 0.0 || g->target_altitude > max_altitude_ ||
      g->climb_speed < 0.0 || g->climb_speed > max_horizontal_speed_) {
    return rclcpp_action::GoalResponse::REJECT;
  }
  const auto uav = get_uav();
  std::lock_guard<std::recursive_mutex> lk(flight_mtx_);
  if (active_ != NONE || action_reserved_ || !flight_state_ready(uav) || uav.armed) {
    return rclcpp_action::GoalResponse::REJECT;
  }
  action_reserved_ = true;
  return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
}

rclcpp_action::CancelResponse FlightController::handle_takeoff_cancel(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<Takeoff>> gh)
{
  std::lock_guard<std::recursive_mutex> lk(flight_mtx_);
  if (!gh_takeoff_ || gh_takeoff_ != gh) return rclcpp_action::CancelResponse::REJECT;
  return rclcpp_action::CancelResponse::ACCEPT;
}

void FlightController::handle_takeoff_accepted(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<Takeoff>> gh)
{
  auto g = gh->get_goal();
  const auto uav = get_uav();
  bool started = false;
  {
    std::lock_guard<std::recursive_mutex> lk(flight_mtx_);
    if (action_reserved_ && active_ == NONE && (!gh_takeoff_ || gh_takeoff_ == gh)) {
      takeoff_target_z_=g->target_altitude;
      takeoff_speed_=(g->climb_speed>0)?g->climb_speed:1.0;
      takeoff_start_x_=uav.position_x; takeoff_start_y_=uav.position_y;
      takeoff_start_z_=uav.position_z; takeoff_start_yaw_=uav.yaw;
      takeoff_ramp_z_=uav.position_z;
      gh_takeoff_=gh;
      active_=TAKEOFF_PREPARING;
      started = true;
    }
  }
  if (!started) {
    finish_takeoff_goal(gh, "takeoff transaction was superseded");
    return;
  }

  // ---- "先建流, 后解锁" 流程 (修复降落后无法再次起飞) ----
  // 背景: PX4 降落后停留在 OFFBOARD 模式 (或 AUTO.LAND 残留), 而
  // ① OFFBOARD 模式 arm 要求 offboard_control_mode 数据新鲜 (offboardCheck);
  // ② POSCTL 等手动模式 arm 要求遥控器 (SITL 无 RC);
  // ③ AUTO.LOITER (SITL 开机默认) 可直接 arm。
  // 统一解法: 先发初始 setpoint 建流 → 切 OFFBOARD → 等流被 PX4 处理注册
  // (offboard_control_mode.position 置位需要至少一个 setpoint 被处理) →
  // arm (带重试) → 校验模式。
  easyfly_msgs::msg::UAVCommand ic; ic.control_mode=easyfly_msgs::msg::UAVCommand::POSITION;
  stamp_command(ic);
  ic.position_x=uav.position_x; ic.position_y=uav.position_y;
  ic.position_z=uav.position_z; ic.yaw=takeoff_start_yaw_;
  pub_uav_cmd_->publish(ic);
  std::this_thread::sleep_for(std::chrono::milliseconds(500));  // 建流

  const auto still_current = [this, &gh]() {
    std::lock_guard<std::recursive_mutex> lk(flight_mtx_);
    return action_reserved_ && gh_takeoff_ == gh && active_ == TAKEOFF_PREPARING;
  };
  const auto abort_preparing = [this, &gh](const std::string & message) {
    finish_takeoff_goal(gh, message);
  };
  if (!still_current()) {
    finish_takeoff_goal(gh, "takeoff transaction interrupted");
    return;
  }

  if (uav.flight_mode != 3) {            // 非 OFFBOARD (LOITER/AUTO.LAND 残留等) → 切入
    if (!call_set_mode(3)) {
      abort_preparing("cannot switch to OFFBOARD (setpoint stream active?)");
      return;
    }
    // 切入后 PX4 需处理至少一个 setpoint 才置位 offboard_control_mode,
    // 立即 arm 会被拒 (实测 16ms 间隔必拒) — 等待注册
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
  }
  if (!still_current()) {
    finish_takeoff_goal(gh, "takeoff transaction interrupted");
    return;
  }
  // arm 重试 ×5 间隔 2s (总窗口 10s) — 兜底两类瞬态拒绝:
  // ① 切 OFFBOARD 后 setpoint 未被处理注册 (offboardCheck data_is_recent)
  // ② EKF/GPS 收敛边缘 ("ekf2 missing data" → Ready for takeoff 之间的窗口)
  bool armed = false;
  for (int i = 0; i < 5 && !armed; ++i) {
    if (!still_current()) {
      finish_takeoff_goal(gh, "takeoff transaction interrupted");
      return;
    }
    armed = call_arm(true);
    if (!armed) std::this_thread::sleep_for(std::chrono::milliseconds(2000));
  }
  if (!armed) {
    RCLCPP_ERROR(get_logger(), "arm 失败 (已重试 5 次/10s, OFFBOARD 流活跃; 检查 EKF/GPS 是否收敛)");
    abort_preparing("arm failed (retried 10s, OFFBOARD stream active)");
    return;
  }
  if (!still_current()) {
    const auto state = get_uav();
    if (state.armed && state.position_z < 0.3) call_arm(false);
    finish_takeoff_goal(gh, "takeoff transaction interrupted");
    return;
  }
  // Q9: 校验 PX4 真正切入 OFFBOARD (mode_sent 只代表命令已发出)
  if (!wait_mode_engaged(3, 3.0)) {
    RCLCPP_ERROR(get_logger(), "OFFBOARD 未确认切入 (当前模式=%d), 起飞中止并上锁",
      static_cast<int>(get_uav().flight_mode));
    call_arm(false);  // 地面上锁安全
    abort_preparing("OFFBOARD not engaged");
    return;
  }
  std::lock_guard<std::recursive_mutex> lk(flight_mtx_);
  if (!still_current()) {
    finish_takeoff_goal(gh, "takeoff transaction interrupted");
    return;
  }
  takeoff_start_time_=now();
  takeoff_deadline_ = now() + rclcpp::Duration::from_seconds(
    std::max(1.0, takeoff_target_z_ - takeoff_start_z_) / takeoff_speed_ * 3.0 + 10.0);
  active_=TAKEOFF;
}

rclcpp_action::GoalResponse FlightController::handle_land_goal(
  const rclcpp_action::GoalUUID &, std::shared_ptr<const Land::Goal> g)
{
  if (!std::isfinite(g->landing_speed) || g->landing_speed != 0.0) {
    RCLCPP_WARN(get_logger(), "拒绝 Land: PX4 AUTO.LAND 暂不支持 landing_speed，必须为 0");
    return rclcpp_action::GoalResponse::REJECT;
  }
  const auto uav = get_uav();
  std::lock_guard<std::recursive_mutex> lk(flight_mtx_);
  if (active_ != HOVER || action_reserved_ || !flight_state_ready(uav) || !uav.armed) {
    return rclcpp_action::GoalResponse::REJECT;
  }
  action_reserved_ = true;
  return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
}

rclcpp_action::CancelResponse FlightController::handle_land_cancel(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<Land>> gh)
{
  // Q3: 恢复悬停 — PX4 正处于 AUTO.LAND:
  //   1. 先发布悬停 setpoint 恢复数据流 (OFFBOARD 要求 >2Hz setpoint 才允许切入,
  //      降落期间 control_loop 不发指令, bridge 已超时停流)
  //   2. 再切 OFFBOARD, 之后 control_loop 的 HOVER 分支接管
  // 悬停点用 land 发起前的 hover_* (即当时我们自己的 setpoint, 无毛刺风险)
  // Serialize this whole recovery transaction with the AUTO.LAND request and
  // confirmation.  The lock is intentionally acquired before flight_mtx_ and
  // is held across blocking service/mode confirmation calls, while
  // flight_mtx_ is only held for short state snapshots/transitions below.
  std::unique_lock<std::mutex> transaction_lk(land_transaction_mtx_);
  {
    std::lock_guard<std::recursive_mutex> lk(flight_mtx_);
    // A cancel request is only valid after AUTO.LAND has been confirmed.  In
    // LAND_PREPARING the accepted callback owns the mode transaction; waiting
    // for transaction_lk above lets it finish, after which this check sees
    // either LANDING (continue recovery) or HOVER (reject safely).
    if (!gh_land_ || gh_land_ != gh || active_ != LANDING) {
      return rclcpp_action::CancelResponse::REJECT;
    }
    active_ = LAND_CANCELING;
  }
  // 先让 control_loop 连续建立一小段 OFFBOARD setpoint 流，再请求退出 AUTO.LAND。
  std::this_thread::sleep_for(std::chrono::milliseconds(500));
  if (!call_set_mode(3) || !wait_mode_engaged(3, 3.0)) {
    RCLCPP_ERROR(get_logger(),
      "取消降落: 切回 OFFBOARD 失败, PX4 将继续 AUTO.LAND 降落!");
    std::lock_guard<std::recursive_mutex> lk(flight_mtx_);
    if (gh_land_ == gh && active_ == LAND_CANCELING) {
      active_ = LANDING;
    }
    return rclcpp_action::CancelResponse::REJECT;
  }
  std::lock_guard<std::recursive_mutex> lk(flight_mtx_);
  if (!gh_land_ || gh_land_ != gh || active_ != LAND_CANCELING) {
    return rclcpp_action::CancelResponse::REJECT;
  }
  return rclcpp_action::CancelResponse::ACCEPT;
}

void FlightController::handle_land_accepted(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<Land>> gh)
{
  // Serialize the complete AUTO.LAND mode transaction with cancellation.
  // Do not retain flight_mtx_ while call_set_mode()/wait_mode_engaged() block;
  // control_loop must continue publishing the LAND_PREPARING hover setpoint.
  std::unique_lock<std::mutex> transaction_lk(land_transaction_mtx_);
  bool started = false;
  {
    std::lock_guard<std::recursive_mutex> lk(flight_mtx_);
    // 先登记 handle 并进入准备态，再执行可能阻塞的 mode service；这样
    // cancel/takeover 在 AUTO.LAND 确认窗口内也能找到并收尾该 goal。
    if (action_reserved_ && active_ == HOVER && (!gh_land_ || gh_land_ == gh)) {
      gh_land_ = gh;
      active_ = LAND_PREPARING;
      started = true;
    }
  }
  if (!started) {
    finish_land_goal(gh, "land transaction was superseded", true);
    return;
  }

  if (!call_set_mode(7) || !wait_mode_engaged(7, 3.0)) {
    RCLCPP_ERROR(get_logger(), "AUTO.LAND 切换未确认，保持 OFFBOARD 悬停并中止 Land");
    finish_land_goal(gh, "AUTO.LAND not engaged", true);
    return;
  }
  bool still_preparing = false;
  {
    std::lock_guard<std::recursive_mutex> lk(flight_mtx_);
    if (gh_land_ == gh && action_reserved_ && active_ == LAND_PREPARING) {
      active_ = LANDING;
      land_start_time_ = now();
      still_preparing = true;
    }
  }
  if (!still_preparing) {
    // 例如 cancel 已把事务切入 LAND_CANCELING，或 takeover 已清理它。
    // cancel 路径仍需持有该 goal，等待 cancel callback 返回 ACCEPT 后由
    // control_loop 调用 canceled()；此处若提前 finish 会在 goal 仍处于
    // EXECUTING 时走 abort()，把一次取消报告成中止。
    {
      std::lock_guard<std::recursive_mutex> lk(flight_mtx_);
      if (gh_land_ == gh && active_ == LAND_CANCELING) {
        return;
      }
    }
    // 其他中断路径不能让 accepted callback 裸返回留下一个永远 pending 的 goal。
    finish_land_goal(gh, "land transaction interrupted", true);
  }
}

rclcpp_action::GoalResponse FlightController::handle_waypoint_goal(
  const rclcpp_action::GoalUUID &, std::shared_ptr<const GoToWaypoint::Goal> g)
{
  const bool yaw_ok = std::isfinite(g->target_yaw) || std::isnan(g->target_yaw);
  if (!std::isfinite(g->target_x) || !std::isfinite(g->target_y) ||
      !std::isfinite(g->target_z) || !yaw_ok || !std::isfinite(g->max_speed) ||
      !std::isfinite(g->acceptance_radius) || g->target_z < 0.0 ||
      g->target_z > max_altitude_ || g->max_speed < 0.0 ||
      g->max_speed > max_horizontal_speed_ || g->acceptance_radius < 0.0) {
    return rclcpp_action::GoalResponse::REJECT;
  }
  const auto uav = get_uav();
  const double distance = std::hypot(
    g->target_x - uav.position_x, g->target_y - uav.position_y);
  if (!std::isfinite(max_goal_distance_) || max_goal_distance_ <= 0.0 ||
      !std::isfinite(distance) || distance > max_goal_distance_) {
    RCLCPP_WARN(get_logger(),
      "拒绝 GoToWaypoint: 目标水平距离 %.2fm 超出上限 %.2fm",
      distance, max_goal_distance_);
    return rclcpp_action::GoalResponse::REJECT;
  }
  std::lock_guard<std::recursive_mutex> lk(flight_mtx_);
  if (active_ != HOVER || action_reserved_ || !flight_state_ready(uav) || !uav.armed) {
    return rclcpp_action::GoalResponse::REJECT;
  }
  action_reserved_=true;
  return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
}

rclcpp_action::CancelResponse FlightController::handle_waypoint_cancel(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<GoToWaypoint>> gh)
{
  std::lock_guard<std::recursive_mutex> lk(flight_mtx_);
  if (!gh_waypoint_ || gh_waypoint_ != gh) return rclcpp_action::CancelResponse::REJECT;
  return rclcpp_action::CancelResponse::ACCEPT;
}

void FlightController::handle_waypoint_accepted(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<GoToWaypoint>> gh)
{
  auto g=gh->get_goal();
  const auto uav = get_uav();
  bool started = false;
  {
    std::lock_guard<std::recursive_mutex> lk(flight_mtx_);
    if (action_reserved_ && active_ == HOVER &&
        (!gh_waypoint_ || gh_waypoint_ == gh)) {
      wp_target_x_=g->target_x; wp_target_y_=g->target_y; wp_target_z_=g->target_z;
      wp_target_yaw_=std::isfinite(g->target_yaw)?g->target_yaw:uav.yaw;
      wp_max_speed_=(g->max_speed>0)?g->max_speed:2.0;
      wp_accept_radius_=(g->acceptance_radius>0)?g->acceptance_radius:0.5;
      double dx=wp_target_x_-uav.position_x, dy=wp_target_y_-uav.position_y,
        dz=wp_target_z_-uav.position_z;
      wp_start_dist_=std::sqrt(dx*dx+dy*dy+dz*dz);
      wp_start_x_ = uav.position_x; wp_start_y_ = uav.position_y;
      x_ramp_ = uav.position_x; y_ramp_ = uav.position_y; z_ramp_ = uav.position_z;
      wp_in_radius_frames_ = 0;            // Q16: 完成判定去抖计数清零
      // Q5: 超时 = 名义飞行时间 × 3 + 15s 余量
      wp_deadline_ = now() + rclcpp::Duration::from_seconds(
        wp_start_dist_ / std::max(wp_max_speed_, 0.1) * 3.0 + 15.0);
      gh_waypoint_=gh; active_=WAYPOINT;
      started = true;
    }
  }
  if (!started) {
    finish_waypoint_goal(gh, "waypoint transaction was superseded");
  }
}

// ================================================================
// M4.3: /follow_trajectory action (EGO-Planner 轨迹跟随)
// ================================================================

rclcpp_action::GoalResponse FlightController::handle_traj_goal(
  const rclcpp_action::GoalUUID &, std::shared_ptr<const FollowTrajectory::Goal> g)
{
  if (!std::isfinite(g->target_x) || !std::isfinite(g->target_y) ||
      !std::isfinite(g->target_z) || !std::isfinite(g->acceptance_radius) ||
      !std::isfinite(g->timeout) || g->target_z < 0.0 ||
      g->target_z > max_altitude_ || g->acceptance_radius < 0.0 || g->timeout < 0.0) {
    return rclcpp_action::GoalResponse::REJECT;
  }
  // 仅 HOVER 可进入 (与既有单动作槽互斥); 需已 arm
  const auto uav = get_uav();
  const double distance = std::hypot(
    g->target_x - uav.position_x, g->target_y - uav.position_y);
  if (!std::isfinite(max_goal_distance_) || max_goal_distance_ <= 0.0 ||
      !std::isfinite(distance) || distance > max_goal_distance_) {
    RCLCPP_WARN(get_logger(),
      "拒绝 FollowTrajectory: 目标水平距离 %.2fm 超出上限 %.2fm",
      distance, max_goal_distance_);
    return rclcpp_action::GoalResponse::REJECT;
  }
  std::lock_guard<std::recursive_mutex> lk(flight_mtx_);
  if (active_ != HOVER || action_reserved_ || !uav.armed || !flight_state_ready(uav)) {
    return rclcpp_action::GoalResponse::REJECT;
  }
  // 与单动作槽 reservation 在同一把锁下锁存，确保 goal 之后到达的
  // PositionCommand 必须使用更高的 trajectory_id 才能启动新轨迹。
  traj_baseline_id_ = traj_seen_max_id_;
  traj_goal_pending_ = true;
  action_reserved_=true;
  return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
}

rclcpp_action::CancelResponse FlightController::handle_traj_cancel(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<FollowTrajectory>> gh)
{
  std::lock_guard<std::recursive_mutex> state_lk(flight_mtx_);
  if (!gh_traj_ || gh_traj_ != gh) return rclcpp_action::CancelResponse::REJECT;
  return rclcpp_action::CancelResponse::ACCEPT;
}

void FlightController::handle_traj_accepted(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<FollowTrajectory>> gh)
{
  auto g = gh->get_goal();
  bool started = false;
  double timeout = 120.0;
  {
    std::lock_guard<std::recursive_mutex> state_lk(flight_mtx_);
    if (action_reserved_ && active_ == HOVER && (!gh_traj_ || gh_traj_ == gh)) {
      traj_target_x_ = g->target_x;
      traj_target_y_ = g->target_y;
      traj_target_z_ = g->target_z;
      traj_accept_radius_ = (g->acceptance_radius > 0) ? g->acceptance_radius : 0.8;
      timeout = (g->timeout > 0) ? g->timeout : 120.0;

      {
        std::lock_guard<std::mutex> lk(traj_mtx_);
        traj_cmd_received_.store(false);           // 起始等首帧 (startup grace)
        traj_cmd_time_ = rclcpp::Time(0, 0, now().get_clock_type());
      }
      traj_accept_time_ = now();
      traj_deadline_ = now() + rclcpp::Duration::from_seconds(timeout);
      traj_in_radius_frames_ = 0;
      traj_active_id_ = 0;
      gh_traj_ = gh;
      traj_goal_pending_ = false;
      active_ = TRAJECTORY_WAIT;
      started = true;
    }
  }
  if (!started) {
    {
      std::lock_guard<std::recursive_mutex> state_lk(flight_mtx_);
      // 若 response/accepted 期间发生外部接管，释放本次 pending reservation，
      // 避免后续 goal 永久被 action_reserved_ 卡住。
      if (traj_goal_pending_) {
        traj_goal_pending_ = false;
        action_reserved_ = false;
      }
    }
    finish_traj_goal(gh, "trajectory transaction was superseded");
    return;
  }
  RCLCPP_INFO(get_logger(),
    "FollowTrajectory 开始: 终点 (%.2f, %.2f, %.2f) r=%.2f timeout=%.0fs",
    traj_target_x_, traj_target_y_, traj_target_z_, traj_accept_radius_, timeout);
}

void FlightController::enter_hover_at(double x, double y, double z, double yaw)
{
  std::lock_guard<std::recursive_mutex> lk(flight_mtx_);
  hover_x_ = x; hover_y_ = y; hover_z_ = z; hover_yaw_ = yaw;
  // 立即发布一条 setpoint: 恢复/保持 OFFBOARD 数据流 (bridge 1s 无指令即停流)
  easyfly_msgs::msg::UAVCommand cmd;
  cmd.control_mode = easyfly_msgs::msg::UAVCommand::POSITION;
  stamp_command(cmd);
  cmd.position_x = x; cmd.position_y = y; cmd.position_z = z; cmd.yaw = yaw;
  pub_uav_cmd_->publish(cmd);
  active_ = HOVER;
  action_reserved_ = false;
}

void FlightController::finish_takeoff_goal(
  std::shared_ptr<rclcpp_action::ServerGoalHandle<Takeoff>> gh,
  const std::string & message)
{
  if (!gh) return;
  {
    std::lock_guard<std::recursive_mutex> lk(flight_mtx_);
    if (gh_takeoff_ == gh ||
        (!gh_takeoff_ && (active_ == TAKEOFF_PREPARING || active_ == TAKEOFF))) {
      gh_takeoff_.reset();
      active_ = NONE;
      action_reserved_ = false;
    }
  }
  auto result = std::make_shared<Takeoff::Result>();
  result->success = false;
  result->message = message;
  try {
    if (gh->is_canceling()) gh->canceled(result);
    else gh->abort(result);
  } catch (const std::exception & e) {
    RCLCPP_WARN(get_logger(), "结束 Takeoff goal 异常: %s", e.what());
  }
}

void FlightController::finish_land_goal(
  std::shared_ptr<rclcpp_action::ServerGoalHandle<Land>> gh,
  const std::string & message, bool keep_hover)
{
  if (!gh) return;
  {
    std::lock_guard<std::recursive_mutex> lk(flight_mtx_);
    if (gh_land_ == gh ||
        (!gh_land_ && (active_ == LAND_PREPARING || active_ == LANDING ||
                       active_ == LAND_CANCELING))) {
      gh_land_.reset();
      active_ = keep_hover ? HOVER : NONE;
      action_reserved_ = false;
    }
  }
  auto result = std::make_shared<Land::Result>();
  result->success = false;
  result->message = message;
  try {
    if (gh->is_canceling()) gh->canceled(result);
    else gh->abort(result);
  } catch (const std::exception & e) {
    RCLCPP_WARN(get_logger(), "结束 Land goal 异常: %s", e.what());
  }
}

void FlightController::finish_waypoint_goal(
  std::shared_ptr<rclcpp_action::ServerGoalHandle<GoToWaypoint>> gh,
  const std::string & message)
{
  if (!gh) return;
  {
    std::lock_guard<std::recursive_mutex> lk(flight_mtx_);
    if (gh_waypoint_ == gh || (!gh_waypoint_ && active_ == WAYPOINT)) {
      gh_waypoint_.reset();
      active_ = HOVER;
      action_reserved_ = false;
    }
  }
  auto result = std::make_shared<GoToWaypoint::Result>();
  result->success = false;
  result->message = message;
  try {
    if (gh->is_canceling()) gh->canceled(result);
    else gh->abort(result);
  } catch (const std::exception & e) {
    RCLCPP_WARN(get_logger(), "结束 GoToWaypoint goal 异常: %s", e.what());
  }
}

void FlightController::finish_traj_goal(
  std::shared_ptr<rclcpp_action::ServerGoalHandle<FollowTrajectory>> gh,
  const std::string & message)
{
  if (!gh) return;
  {
    std::lock_guard<std::recursive_mutex> lk(flight_mtx_);
    if (gh_traj_ == gh ||
        (!gh_traj_ && (active_ == TRAJECTORY_WAIT || active_ == TRAJECTORY))) {
      gh_traj_.reset();
      active_ = HOVER;
      action_reserved_ = false;
    }
  }
  auto result = std::make_shared<FollowTrajectory::Result>();
  result->success = false;
  result->message = message;
  try {
    if (gh->is_canceling()) gh->canceled(result);
    else gh->abort(result);
  } catch (const std::exception & e) {
    RCLCPP_WARN(get_logger(), "结束 FollowTrajectory goal 异常: %s", e.what());
  }
}

void FlightController::stamp_command(easyfly_msgs::msg::UAVCommand & cmd)
{
  cmd.header.stamp = now();
  cmd.header.frame_id = "odom";
}

bool FlightController::flight_state_ready(
  const easyfly_msgs::msg::UAVState & uav) const
{
  return state_received_ && uav.connected && uav.pose_valid && uav.attitude_valid &&
    std::isfinite(uav.position_x) && std::isfinite(uav.position_y) &&
    std::isfinite(uav.position_z) && std::isfinite(uav.yaw);
}

// Q4: 反馈值毛刺守卫 — 与渐近值偏差 <3m (正常飞行中飞机紧跟 ramp) 才采信,
// 否则视为反馈尖峰 (M6 实测 local_position z=-10 毛刺), 回退无毛刺的 ramp 值
double FlightController::safe_axis(double fb, double ramp)
{
  return (std::isfinite(fb) && std::abs(fb - ramp) < 3.0) ? fb : ramp;
}

bool FlightController::wait_mode_engaged(uint8_t mode, double timeout_s)
{
  const auto t0 = now();
  while ((now() - t0).seconds() < timeout_s) {
    if (get_uav().flight_mode == mode) return true;
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
  }
  return get_uav().flight_mode == mode;
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
