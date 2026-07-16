#ifndef EASYFLY_MAVLINK_BRIDGE_MAVLINK_BRIDGE_HPP_
#define EASYFLY_MAVLINK_BRIDGE_MAVLINK_BRIDGE_HPP_

#include <rclcpp/rclcpp.hpp>

#include <easyfly_msgs/msg/uav_state.hpp>
#include <easyfly_msgs/msg/uav_command.hpp>
#include <easyfly_msgs/msg/gimbal_state.hpp>
#include <easyfly_msgs/msg/mission_status.hpp>

#include <geometry_msgs/msg/pose_stamped.hpp>
#include <geometry_msgs/msg/twist_stamped.hpp>
#include <geometry_msgs/msg/vector3_stamped.hpp>
#include <mavros_msgs/msg/state.hpp>
#include <mavros_msgs/msg/altitude.hpp>
#include <mavros_msgs/msg/rc_in.hpp>
#include <mavros_msgs/msg/attitude_target.hpp>
#include <mavros_msgs/srv/command_bool.hpp>
#include <mavros_msgs/srv/set_mode.hpp>
#include <sensor_msgs/msg/battery_state.hpp>
#include <sensor_msgs/msg/imu.hpp>
#include <sensor_msgs/msg/nav_sat_fix.hpp>
#include <easyfly_msgs/srv/arm_motors.hpp>
#include <easyfly_msgs/srv/set_flight_mode.hpp>

namespace easyfly_mavlink_bridge
{

/**
 * @brief MAVLink ↔ easyfly_msgs 桥接节点
 *
 * decoder: 订阅 mavros2 topic → 聚合发布 /uav_state、/mission_status
 * encoder: 订阅 /uav_command → 翻译为 mavros2 setpoint + 20Hz 持续发布
 * services: /arm_motors、/set_flight_mode → 封装 mavros2 服务调用
 */
class MavlinkBridge : public rclcpp::Node
{
public:
  explicit MavlinkBridge(const rclcpp::NodeOptions & options = rclcpp::NodeOptions());

private:
  // ---- decoder callbacks ----
  void cb_state(const mavros_msgs::msg::State::SharedPtr msg);
  void cb_local_pose(const geometry_msgs::msg::PoseStamped::SharedPtr msg);
  void cb_local_velocity(const geometry_msgs::msg::TwistStamped::SharedPtr msg);
  void cb_imu(const sensor_msgs::msg::Imu::SharedPtr msg);
  void cb_altitude(const mavros_msgs::msg::Altitude::SharedPtr msg);
  void cb_global_position(const sensor_msgs::msg::NavSatFix::SharedPtr msg);
  void cb_battery(const sensor_msgs::msg::BatteryState::SharedPtr msg);
  void cb_rc_in(const mavros_msgs::msg::RCIn::SharedPtr msg);

  void publish_state();

  // ---- encoder ----
  void cb_uav_command(const easyfly_msgs::msg::UAVCommand::SharedPtr msg);
  void publish_setpoint();

  // ---- service handlers ----
  void cb_arm_motors(
    const std::shared_ptr<easyfly_msgs::srv::ArmMotors::Request>  req,
    std::shared_ptr<easyfly_msgs::srv::ArmMotors::Response>       res);
  void cb_set_flight_mode(
    const std::shared_ptr<easyfly_msgs::srv::SetFlightMode::Request>  req,
    std::shared_ptr<easyfly_msgs::srv::SetFlightMode::Response>       res);

  // ---- 静态转换工具 ----
  static double quat_to_yaw(double x, double y, double z, double w);

  // ---- 订阅者 ----
  rclcpp::Subscription<mavros_msgs::msg::State>::SharedPtr            sub_state_;
  rclcpp::Subscription<geometry_msgs::msg::PoseStamped>::SharedPtr    sub_local_pose_;
  rclcpp::Subscription<geometry_msgs::msg::TwistStamped>::SharedPtr   sub_local_vel_;
  rclcpp::Subscription<sensor_msgs::msg::Imu>::SharedPtr              sub_imu_;
  rclcpp::Subscription<mavros_msgs::msg::Altitude>::SharedPtr         sub_altitude_;
  rclcpp::Subscription<sensor_msgs::msg::NavSatFix>::SharedPtr        sub_global_pos_;
  rclcpp::Subscription<sensor_msgs::msg::BatteryState>::SharedPtr     sub_battery_;
  rclcpp::Subscription<mavros_msgs::msg::RCIn>::SharedPtr             sub_rc_in_;
  rclcpp::Subscription<easyfly_msgs::msg::UAVCommand>::SharedPtr      sub_uav_command_;

  // ---- 发布者 ----
  rclcpp::Publisher<easyfly_msgs::msg::UAVState>::SharedPtr      pub_uav_state_;
  rclcpp::Publisher<easyfly_msgs::msg::MissionStatus>::SharedPtr pub_mission_status_;
  rclcpp::Publisher<geometry_msgs::msg::PoseStamped>::SharedPtr  pub_setpoint_pos_;
  rclcpp::Publisher<geometry_msgs::msg::Twist>::SharedPtr        pub_setpoint_vel_;
  rclcpp::Publisher<mavros_msgs::msg::AttitudeTarget>::SharedPtr pub_setpoint_att_;

  // ---- 服务端 ----
  rclcpp::Service<easyfly_msgs::srv::ArmMotors>::SharedPtr      srv_arm_;
  rclcpp::Service<easyfly_msgs::srv::SetFlightMode>::SharedPtr  srv_mode_;

  // ---- mavros 客户端 (预创建，避免每次回调重建) ----
  rclcpp::Client<mavros_msgs::srv::CommandBool>::SharedPtr client_arming_;
  rclcpp::Client<mavros_msgs::srv::SetMode>::SharedPtr     client_set_mode_;

  // ---- 独立 callback group (service 与 client 分离，避免死锁) ----
  rclcpp::CallbackGroup::SharedPtr srv_cb_group_;

  // ---- 定时器 ----
  rclcpp::TimerBase::SharedPtr timer_state_;
  rclcpp::TimerBase::SharedPtr timer_setpoint_;

  // ---- 聚合缓存 ----
  easyfly_msgs::msg::UAVState uav_;

  // ---- encoder 缓存 ----
  easyfly_msgs::msg::UAVCommand last_cmd_;
  rclcpp::Time last_cmd_time_;
  bool     cmd_received_    {false};
  double   setpoint_timeout_{1.0};   // 超时秒数，超时后停止发 setpoint (via param)

  // 标志位
  bool rcvd_armed_        {false};
  bool rcvd_pose_         {false};
  bool rcvd_vel_          {false};
  bool rcvd_imu_          {false};
  bool rcvd_alt_          {false};
  bool rcvd_gps_          {false};
  bool rcvd_bat_          {false};
  bool rcvd_rc_           {false};
};

}  // namespace easyfly_mavlink_bridge

#endif  // EASYFLY_MAVLINK_BRIDGE_MAVLINK_BRIDGE_HPP_
