#ifndef EASYFLY_FLIGHT_CONTROL_FLIGHT_CONTROLLER_HPP_
#define EASYFLY_FLIGHT_CONTROL_FLIGHT_CONTROLLER_HPP_

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>

#include <atomic>
#include <mutex>

#include <easyfly_msgs/msg/uav_state.hpp>
#include <easyfly_msgs/msg/uav_command.hpp>
#include <easyfly_msgs/action/takeoff.hpp>
#include <easyfly_msgs/action/land.hpp>
#include <easyfly_msgs/action/go_to_waypoint.hpp>
#include <easyfly_msgs/action/follow_trajectory.hpp>
#include <easyfly_msgs/srv/arm_motors.hpp>
#include <easyfly_msgs/srv/set_flight_mode.hpp>
#include <quadrotor_msgs/msg/position_command.hpp>

#include "easyfly_flight_control/trajectory_startup_timeout.hpp"

namespace easyfly_flight_control
{

// 注: 原 PID 结构已移除 (Q1) — 本节点的实际控制策略为
// "setpoint 生成 + PX4 OFFBOARD 内环闭环", PID 从未被调用, 属死代码。
// 若阶段四需要速度/姿态外环, 请重新设计并参数化。

class FlightController : public rclcpp::Node
{
  friend class NavigationSessionTestPeer;
public:
  using Takeoff      = easyfly_msgs::action::Takeoff;
  using Land         = easyfly_msgs::action::Land;
  using GoToWaypoint = easyfly_msgs::action::GoToWaypoint;
  using FollowTrajectory = easyfly_msgs::action::FollowTrajectory;

  explicit FlightController(const rclcpp::NodeOptions & options = rclcpp::NodeOptions());

private:
  // ---- state callback ----
  void cb_uav_state(const easyfly_msgs::msg::UAVState::SharedPtr msg);
  // M4.3: EGO-Planner 轨迹指令回调
  void cb_position_cmd(const quadrotor_msgs::msg::PositionCommand::SharedPtr msg);

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

  // ---- M4.3: /follow_trajectory action ----
  rclcpp_action::GoalResponse handle_traj_goal(
    const rclcpp_action::GoalUUID &, std::shared_ptr<const FollowTrajectory::Goal>);
  rclcpp_action::CancelResponse handle_traj_cancel(
    const std::shared_ptr<rclcpp_action::ServerGoalHandle<FollowTrajectory>>);
  void handle_traj_accepted(
    const std::shared_ptr<rclcpp_action::ServerGoalHandle<FollowTrajectory>>);

  // ---- service clients ----
  rclcpp::Client<easyfly_msgs::srv::ArmMotors>::SharedPtr     cli_arm_;
  rclcpp::Client<easyfly_msgs::srv::SetFlightMode>::SharedPtr cli_mode_;

  // ---- 独立 callback group (client 与 action 回调分离，避免死锁) ----
  rclcpp::CallbackGroup::SharedPtr cli_cb_group_;
  rclcpp::CallbackGroup::SharedPtr ctl_cb_group_;   // control loop 专用
  rclcpp::CallbackGroup::SharedPtr state_cb_group_; // /uav_state 订阅专用 (Q9)

  // ---- helpers ----
  bool call_arm(bool arm);
  bool call_set_mode(uint8_t mode);
  double clamp(double v, double lo, double hi);
  // Q9: 等待 PX4 实际进入指定模式 (轮询 /uav_state.flight_mode)
  bool wait_mode_engaged(uint8_t mode, double timeout_s);
  // Q9: uav_ 快照 (线程安全读取)
  easyfly_msgs::msg::UAVState get_uav() const;
  // Q4: 用渐近状态刷新悬停目标并立即发布 setpoint (恢复 OFFBOARD 数据流)
  void enter_hover_at(double x, double y, double z, double yaw);
  // Q4: 反馈值毛刺守卫 (偏差>3m 回退 ramp 值)
  static double safe_axis(double fb, double ramp);
  void stamp_command(easyfly_msgs::msg::UAVCommand & cmd);
  bool flight_state_ready(const easyfly_msgs::msg::UAVState & uav) const;
  // Accepted goal 的所有失败/竞态退出统一经这些 helper 收尾，确保 reservation
  // 与 goal handle 不会在 action 已接受后悬挂。
  void finish_takeoff_goal(
    std::shared_ptr<rclcpp_action::ServerGoalHandle<Takeoff>> gh,
    const std::string & message);
  void finish_land_goal(
    std::shared_ptr<rclcpp_action::ServerGoalHandle<Land>> gh,
    const std::string & message, bool keep_hover);
  void finish_waypoint_goal(
    std::shared_ptr<rclcpp_action::ServerGoalHandle<GoToWaypoint>> gh,
    const std::string & message);
  void finish_traj_goal(
    std::shared_ptr<rclcpp_action::ServerGoalHandle<FollowTrajectory>> gh,
    const std::string & message);

  // ---- subscriptions ----
  rclcpp::Subscription<easyfly_msgs::msg::UAVState>::SharedPtr sub_uav_state_;
  // M4.3: EGO-Planner 输出流 (quadrotor_msgs/PositionCommand, ~100Hz)
  rclcpp::Subscription<quadrotor_msgs::msg::PositionCommand>::SharedPtr sub_position_cmd_;

  // ---- publisher ----
  rclcpp::Publisher<easyfly_msgs::msg::UAVCommand>::SharedPtr pub_uav_cmd_;

  // ---- timer ----
  rclcpp::TimerBase::SharedPtr timer_ctl_;

  // ---- action servers ----
  rclcpp_action::Server<Takeoff>::SharedPtr      as_takeoff_;
  rclcpp_action::Server<Land>::SharedPtr         as_land_;
  rclcpp_action::Server<GoToWaypoint>::SharedPtr as_waypoint_;
  rclcpp_action::Server<FollowTrajectory>::SharedPtr as_traj_;

  // ---- latest state (Q9: 多线程读写保护) ----
  easyfly_msgs::msg::UAVState uav_;
  mutable std::mutex state_mtx_;
  std::atomic<bool> state_received_{false};

  // ---- waypoint 目标渐近状态 (抗反馈毛刺, 自维护无毛刺插值) ----
  double x_ramp_{0.0}, y_ramp_{0.0}, z_ramp_{0.0};
  double wp_start_x_{0.0}, wp_start_y_{0.0};         // waypoint 起点
  int    wp_in_radius_frames_{0};                    // Q16: 连续在验收半径内的帧数 (去抖)
  rclcpp::Time last_ctl_time_;                       // Q12: 上一控制周期时刻 (实测 dt)

  // ---- active action ----
  enum Action {
    NONE, TAKEOFF_PREPARING, TAKEOFF, LAND_PREPARING, LANDING, LAND_CANCELING,
    WAYPOINT, HOVER,
    TRAJECTORY_WAIT, TRAJECTORY
  };
  // MultiThreadedExecutor 下，全部飞行状态、GoalHandle 和目标参数由此锁保护。
  mutable std::recursive_mutex flight_mtx_;
  // Land 的 PX4 mode service/确认事务必须串行执行；持有此锁时不得持有
  // flight_mtx_，避免阻塞模式调用阻塞 control_loop 或状态迁移。
  mutable std::mutex land_transaction_mtx_;
  Action active_{NONE};
  bool action_reserved_{false};       // goal callback 原子预留，关闭跨 Action 双接受窗口
  rclcpp::Time takeover_since_;        // Q2 配套: 外部接管检测去抖起始时刻

  // hover 目标位置（takeoff/waypoint 完成后保持的位置）
  double hover_x_{0.0}, hover_y_{0.0}, hover_z_{0.0}, hover_yaw_{0.0};

  // takeoff state
  double takeoff_target_z_{0.0};
  double takeoff_speed_{1.0};
  double takeoff_start_x_{0.0}, takeoff_start_y_{0.0}, takeoff_start_z_{0.0};
  double takeoff_start_yaw_{0.0};    // Q7: 起飞时锁存 yaw, 全程不取反馈 (防姿态毛刺)
  double takeoff_ramp_z_{0.0};       // Q4/Q5: 起飞渐近高度 (取消/超时时悬停用)
  rclcpp::Time takeoff_start_time_;
  rclcpp::Time takeoff_deadline_;    // Q5: 起飞超时保护
  rclcpp::Time land_start_time_;

  // waypoint state
  double wp_target_x_{0.0}, wp_target_y_{0.0}, wp_target_z_{0.0}, wp_target_yaw_{0.0};
  double wp_max_speed_{2.0};
  double wp_accept_radius_{0.5};
  double wp_start_dist_{0.0};
  rclcpp::Time wp_deadline_;         // Q5: 航点超时保护

  // action goal handles
  std::shared_ptr<rclcpp_action::ServerGoalHandle<Takeoff>>      gh_takeoff_;
  std::shared_ptr<rclcpp_action::ServerGoalHandle<Land>>         gh_land_;
  std::shared_ptr<rclcpp_action::ServerGoalHandle<GoToWaypoint>> gh_waypoint_;
  std::shared_ptr<rclcpp_action::ServerGoalHandle<FollowTrajectory>> gh_traj_;

  // ---- M4.3: /follow_trajectory 状态 ----
  // 最近一条 EGO /position_cmd 快照 (跨线程读: 回调组独立)
  quadrotor_msgs::msg::PositionCommand latest_cmd_;
  rclcpp::Time traj_cmd_time_;                       // 最近收到轨迹指令时刻 (0=未收到)
  mutable std::mutex traj_mtx_;                      // latest_cmd_/traj_cmd_time_ 保护
  std::atomic<bool> traj_cmd_received_{false};
  double traj_target_x_{0.0}, traj_target_y_{0.0}, traj_target_z_{0.0};
  double traj_accept_radius_{0.8};
  double traj_stream_timeout_{kTrajectoryStreamTimeout};  // 首帧后流断判定 [s]
  double traj_startup_grace_{kDefaultTrajectoryStartupGrace};
  // 首帧前等待 EGO 有界重试；独立于 traj_stream_timeout_ 和 action deadline。
  int    traj_in_radius_frames_{0};                  // 到达判定去抖
  rclcpp::Time traj_accept_time_;
  rclcpp::Time traj_deadline_;
  // PositionCommand 的单调 ID 水位。它由 flight_mtx_ 保护，并且即使当前
  // 没有 FollowTrajectory 也会从合格消息中更新，用于绑定下一次 goal。
  uint32_t traj_seen_max_id_{0};
  // 新 goal 在 goal callback 中与 action_reserved_ 一起原子锁存的 ID 水位。
  uint32_t traj_baseline_id_{0};
  // goal response 已返回但 accepted callback 尚未完成时，阻止消息把
  // response/accepted 窗口内的 ID 提前提交到 seen 水位。
  bool traj_goal_pending_{false};
  std::string traj_session_id_;
  uint32_t traj_active_id_{0};

  // params
  double ctl_rate_{20.0};
  double land_timeout_{30.0};
  double max_altitude_{50.0};
  double max_horizontal_speed_{20.0};
  double max_goal_distance_{100.0};
};

}  // namespace easyfly_flight_control

#endif  // EASYFLY_FLIGHT_CONTROL_FLIGHT_CONTROLLER_HPP_
