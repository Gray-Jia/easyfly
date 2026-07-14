#include "easyfly_mavlink_bridge/mavlink_bridge.hpp"

#include <cmath>

namespace easyfly_mavlink_bridge
{

using namespace std::placeholders;

// ---- 四元数 → yaw (绕 Z 轴旋转) ----
double MavlinkBridge::quat_to_yaw(double x, double y, double z, double w)
{
  double siny_cosp = 2.0 * (w * z + x * y);
  double cosy_cosp = 1.0 - 2.0 * (y * y + z * z);
  return std::atan2(siny_cosp, cosy_cosp);
}

// ================================================================
// 构造
// ================================================================

MavlinkBridge::MavlinkBridge(const rclcpp::NodeOptions & options)
  : Node("mavlink_bridge", options)
{
  auto sensor_qos = rclcpp::SensorDataQoS();
  auto default_qos = rclcpp::QoS(10);

  // ---- decoder 订阅 ----
  sub_state_ = create_subscription<mavros_msgs::msg::State>(
    "/mavros/state", default_qos,
    std::bind(&MavlinkBridge::cb_state, this, _1));

  sub_local_pose_ = create_subscription<geometry_msgs::msg::PoseStamped>(
    "/mavros/local_position/pose", sensor_qos,
    std::bind(&MavlinkBridge::cb_local_pose, this, _1));

  sub_local_vel_ = create_subscription<geometry_msgs::msg::TwistStamped>(
    "/mavros/local_position/velocity_local", sensor_qos,
    std::bind(&MavlinkBridge::cb_local_velocity, this, _1));

  sub_imu_ = create_subscription<sensor_msgs::msg::Imu>(
    "/mavros/imu/data", sensor_qos,
    std::bind(&MavlinkBridge::cb_imu, this, _1));

  sub_altitude_ = create_subscription<mavros_msgs::msg::Altitude>(
    "/mavros/altitude", sensor_qos,
    std::bind(&MavlinkBridge::cb_altitude, this, _1));

  sub_global_pos_ = create_subscription<sensor_msgs::msg::NavSatFix>(
    "/mavros/global_position/global", sensor_qos,
    std::bind(&MavlinkBridge::cb_global_position, this, _1));

  sub_battery_ = create_subscription<sensor_msgs::msg::BatteryState>(
    "/mavros/battery", sensor_qos,
    std::bind(&MavlinkBridge::cb_battery, this, _1));

  sub_rc_in_ = create_subscription<mavros_msgs::msg::RCIn>(
    "/mavros/rc/in", default_qos,
    std::bind(&MavlinkBridge::cb_rc_in, this, _1));

  // ---- encoder 订阅 ----
  sub_uav_command_ = create_subscription<easyfly_msgs::msg::UAVCommand>(
    "/uav_command", default_qos,
    std::bind(&MavlinkBridge::cb_uav_command, this, _1));

  // ---- 发布者 ----
  pub_uav_state_ = create_publisher<easyfly_msgs::msg::UAVState>(
    "/uav_state", default_qos);

  pub_mission_status_ = create_publisher<easyfly_msgs::msg::MissionStatus>(
    "/mission_status", default_qos);

  // ---- 20Hz 定时发布 ----
  timer_ = create_wall_timer(
    std::chrono::milliseconds(50),
    std::bind(&MavlinkBridge::publish_state, this));

  // ---- 初始化缓存 ----
  uav_.header.frame_id = "map";
  uav_.armed   = false;
  uav_.flight_mode = 0;
  uav_.flight_mode_name = "";

  RCLCPP_INFO(get_logger(), "MavlinkBridge started — 20Hz /uav_state, /mission_status");
}

// ================================================================
// decoder callbacks
// ================================================================

void MavlinkBridge::cb_state(const mavros_msgs::msg::State::SharedPtr msg)
{
  uav_.armed            = msg->armed;
  uav_.flight_mode_name = msg->mode;

  // 字符串模式名 → 枚举值（PX4 常用模式）
  if      (msg->mode == "MANUAL")     uav_.flight_mode = 0;
  else if (msg->mode == "ALTCTL")     uav_.flight_mode = 1;
  else if (msg->mode == "POSCTL")     uav_.flight_mode = 2;
  else if (msg->mode == "OFFBOARD")   uav_.flight_mode = 3;
  else if (msg->mode == "STABILIZED") uav_.flight_mode = 4;
  else if (msg->mode == "ACRO")       uav_.flight_mode = 5;
  else if (msg->mode == "RTL")        uav_.flight_mode = 6;
  else if (msg->mode == "LAND")       uav_.flight_mode = 7;
  // PX4 SITL 启动后默认进入 AUTO.LOITER
  else if (msg->mode == "AUTO.LOITER") uav_.flight_mode = 2;   // 等同于 POSCTL
  else if (msg->mode == "AUTO.TAKEOFF") uav_.flight_mode = 1;  // 等同于 ALTCTL
  else if (msg->mode == "AUTO.LAND")    uav_.flight_mode = 7;  // 等同于 LAND
  else if (msg->mode == "AUTO.RTL")     uav_.flight_mode = 6;  // 等同于 RTL
  else                                uav_.flight_mode = 99;

  rcvd_armed_ = true;
}

void MavlinkBridge::cb_local_pose(const geometry_msgs::msg::PoseStamped::SharedPtr msg)
{
  uav_.position_x = msg->pose.position.x;
  uav_.position_y = msg->pose.position.y;
  uav_.position_z = msg->pose.position.z;
  rcvd_pose_ = true;
}

void MavlinkBridge::cb_local_velocity(const geometry_msgs::msg::TwistStamped::SharedPtr msg)
{
  uav_.velocity_x = msg->twist.linear.x;
  uav_.velocity_y = msg->twist.linear.y;
  uav_.velocity_z = msg->twist.linear.z;
  rcvd_vel_ = true;
}

void MavlinkBridge::cb_imu(const sensor_msgs::msg::Imu::SharedPtr msg)
{
  double qx = msg->orientation.x;
  double qy = msg->orientation.y;
  double qz = msg->orientation.z;
  double qw = msg->orientation.w;

  // 四元数 → 欧拉角 (roll, pitch, yaw 简化版)
  double sinr_cosp = 2.0 * (qw * qx + qy * qz);
  double cosr_cosp = 1.0 - 2.0 * (qx * qx + qy * qy);
  uav_.roll = std::atan2(sinr_cosp, cosr_cosp);

  double sinp = 2.0 * (qw * qy - qz * qx);
  if (std::abs(sinp) >= 1.0)
    uav_.pitch = std::copysign(M_PI / 2.0, sinp);
  else
    uav_.pitch = std::asin(sinp);

  uav_.yaw = quat_to_yaw(qx, qy, qz, qw);

  // 角速度
  uav_.rollspeed  = msg->angular_velocity.x;
  uav_.pitchspeed = msg->angular_velocity.y;
  uav_.yawspeed   = msg->angular_velocity.z;

  rcvd_imu_ = true;
}

void MavlinkBridge::cb_altitude(const mavros_msgs::msg::Altitude::SharedPtr msg)
{
  uav_.altitude          = msg->amsl;
  uav_.relative_altitude = msg->relative;
  rcvd_alt_ = true;
}

void MavlinkBridge::cb_global_position(const sensor_msgs::msg::NavSatFix::SharedPtr msg)
{
  uav_.latitude  = msg->latitude;
  uav_.longitude = msg->longitude;
  uav_.eph       = static_cast<double>(msg->position_covariance[0]);
  uav_.epv       = static_cast<double>(msg->position_covariance[8]);
  rcvd_gps_ = true;
}

void MavlinkBridge::cb_battery(const sensor_msgs::msg::BatteryState::SharedPtr msg)
{
  uav_.battery_voltage   = msg->voltage;
  uav_.battery_remaining = msg->percentage;
  rcvd_bat_ = true;
}

void MavlinkBridge::cb_rc_in(const mavros_msgs::msg::RCIn::SharedPtr msg)
{
  // 只要收到 RC 数据就认为遥控器连接
  uav_.rc_connected = !msg->channels.empty();
  rcvd_rc_ = true;
}

// ================================================================
// 定时发布
// ================================================================

void MavlinkBridge::publish_state()
{
  uav_.header.stamp = now();
  pub_uav_state_->publish(uav_);

  // /mission_status: 阶段一只发布 mission_phase=IDLE
  easyfly_msgs::msg::MissionStatus ms;
  ms.header.stamp    = uav_.header.stamp;
  ms.mission_phase    = easyfly_msgs::msg::MissionStatus::IDLE;
  ms.phase_name       = "idle";
  ms.current_waypoint = -1;
  ms.total_waypoints  = 0;
  ms.progress         = 0.0f;
  ms.estimated_time_remaining = 0.0f;
  ms.mission_success  = false;
  ms.message          = "";
  pub_mission_status_->publish(ms);
}

// ================================================================
// encoder: 阶段一只做日志
// ================================================================

void MavlinkBridge::cb_uav_command(const easyfly_msgs::msg::UAVCommand::SharedPtr msg)
{
  RCLCPP_INFO_STREAM(get_logger(),
    "Received /uav_command mode=" << static_cast<int>(msg->control_mode)
    << " pos=(" << msg->position_x << "," << msg->position_y << "," << msg->position_z << ")"
    << " yaw=" << msg->yaw);
  // TODO(阶段二): 翻译为 mavros2 setpoint 并下发
}

}  // namespace easyfly_mavlink_bridge
