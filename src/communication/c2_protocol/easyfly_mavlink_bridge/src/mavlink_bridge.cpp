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

  // ---- 参数 ----
  double publish_rate = declare_parameter("publish_rate", 20.0);
  setpoint_timeout_   = declare_parameter("setpoint_timeout", 1.0);

  auto period_ms = std::chrono::milliseconds(static_cast<int>(1000.0 / publish_rate));

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

  // ---- encoder 发布者 (到 mavros2 setpoint topics) ----
  pub_setpoint_pos_ = create_publisher<geometry_msgs::msg::PoseStamped>(
    "/mavros/setpoint_position/local", default_qos);

  pub_setpoint_vel_ = create_publisher<geometry_msgs::msg::Twist>(
    "/mavros/setpoint_velocity/cmd_vel_unstamped", default_qos);

  pub_setpoint_att_ = create_publisher<mavros_msgs::msg::AttitudeTarget>(
    "/mavros/setpoint_raw/attitude", default_qos);

  // ---- 服务端 (封装 mavros2 服务) ----
  srv_arm_ = create_service<easyfly_msgs::srv::ArmMotors>(
    "/arm_motors",
    std::bind(&MavlinkBridge::cb_arm_motors, this, _1, _2));

  srv_mode_ = create_service<easyfly_msgs::srv::SetFlightMode>(
    "/set_flight_mode",
    std::bind(&MavlinkBridge::cb_set_flight_mode, this, _1, _2));

  // ---- mavros 客户端（预创建，避免每次回调内新建） ----
  client_arming_    = create_client<mavros_msgs::srv::CommandBool>("/mavros/cmd/arming");
  client_set_mode_  = create_client<mavros_msgs::srv::SetMode>("/mavros/set_mode");

  // ---- 定时器 ----
  timer_state_ = create_wall_timer(
    period_ms,
    std::bind(&MavlinkBridge::publish_state, this));

  timer_setpoint_ = create_wall_timer(
    period_ms,
    std::bind(&MavlinkBridge::publish_setpoint, this));

  // ---- 初始化缓存 ----
  uav_.header.frame_id = "map";
  uav_.armed   = false;
  uav_.flight_mode = 0;
  uav_.flight_mode_name = "";

  last_cmd_time_ = now();

  RCLCPP_INFO(get_logger(),
    "MavlinkBridge started — %gHz /uav_state, encoder, /arm_motors, /set_flight_mode",
    publish_rate);
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
// encoder: UAVCommand → mavros2 setpoint
// ================================================================

void MavlinkBridge::cb_uav_command(const easyfly_msgs::msg::UAVCommand::SharedPtr msg)
{
  last_cmd_      = *msg;
  last_cmd_time_ = now();
  cmd_received_  = true;

  RCLCPP_DEBUG_STREAM(get_logger(),
    "/uav_command mode=" << static_cast<int>(msg->control_mode)
    << " pos=(" << msg->position_x << "," << msg->position_y << "," << msg->position_z << ")"
    << " yaw=" << msg->yaw);
}

void MavlinkBridge::publish_setpoint()
{
  // 超时保护：超过 setpoint_timeout_ 秒无新指令则停止发布
  auto elapsed = (now() - last_cmd_time_).seconds();
  if (!cmd_received_ || elapsed > setpoint_timeout_) {
    return;  // 不发 setpoint，PX4 会在 OFFBOARD 模式下自动切回 POSITION
  }

  switch (last_cmd_.control_mode) {
    case easyfly_msgs::msg::UAVCommand::POSITION: {
      geometry_msgs::msg::PoseStamped pose;
      pose.header.stamp    = now();
      pose.header.frame_id = "map";
      pose.pose.position.x = last_cmd_.position_x;
      pose.pose.position.y = last_cmd_.position_y;
      pose.pose.position.z = last_cmd_.position_z;

      // yaw → 四元数
      double half_yaw = last_cmd_.yaw * 0.5;
      pose.pose.orientation.z = std::sin(half_yaw);
      pose.pose.orientation.w = std::cos(half_yaw);

      pub_setpoint_pos_->publish(pose);
      break;
    }
    case easyfly_msgs::msg::UAVCommand::VELOCITY: {
      geometry_msgs::msg::Twist vel;
      vel.linear.x  = last_cmd_.velocity_x;
      vel.linear.y  = last_cmd_.velocity_y;
      vel.linear.z  = last_cmd_.velocity_z;
      vel.angular.z = last_cmd_.yaw_rate;

      pub_setpoint_vel_->publish(vel);
      break;
    }
    case easyfly_msgs::msg::UAVCommand::ATTITUDE:
    case easyfly_msgs::msg::UAVCommand::ATTITUDE_THRUST: {
      mavros_msgs::msg::AttitudeTarget att;
      att.header.stamp = now();

      // roll/pitch/yaw → 四元数
      double half_r = last_cmd_.roll  * 0.5;
      double half_p = last_cmd_.pitch * 0.5;
      double half_y = last_cmd_.yaw_att * 0.5;

      double cr = std::cos(half_r), sr = std::sin(half_r);
      double cp = std::cos(half_p), sp = std::sin(half_p);
      double cy = std::cos(half_y), sy = std::sin(half_y);

      att.orientation.w = cr * cp * cy + sr * sp * sy;
      att.orientation.x = sr * cp * cy - cr * sp * sy;
      att.orientation.y = cr * sp * cy + sr * cp * sy;
      att.orientation.z = cr * cp * sy - sr * sp * cy;

      att.thrust      = static_cast<float>(last_cmd_.thrust);
      att.type_mask   = 0b111;  // 忽略角速率，使用姿态+推力
      att.body_rate.x = 0.0f;
      att.body_rate.y = 0.0f;
      att.body_rate.z = 0.0f;

      pub_setpoint_att_->publish(att);
      break;
    }
    case easyfly_msgs::msg::UAVCommand::ANGULAR_RATE: {
      mavros_msgs::msg::AttitudeTarget att;
      att.header.stamp = now();

      att.body_rate.x = static_cast<float>(last_cmd_.roll_rate);
      att.body_rate.y = static_cast<float>(last_cmd_.pitch_rate);
      att.body_rate.z = static_cast<float>(last_cmd_.yaw_rate_cmd);
      att.thrust      = static_cast<float>(last_cmd_.thrust);
      att.type_mask   = 0b10000111;  // 忽略姿态+推力 (bit0 使用角速率)

      pub_setpoint_att_->publish(att);
      break;
    }
    default:
      RCLCPP_WARN_STREAM(get_logger(),
        "Unknown control_mode=" << static_cast<int>(last_cmd_.control_mode));
      break;
  }
}

// ================================================================
// service handlers: arm / set_mode (封装 mavros2 服务调用)
// ================================================================

void MavlinkBridge::cb_arm_motors(
  const std::shared_ptr<easyfly_msgs::srv::ArmMotors::Request>  req,
  std::shared_ptr<easyfly_msgs::srv::ArmMotors::Response>       res)
{
  RCLCPP_INFO(get_logger(), "cb_arm_motors CALLED arm=%d", req->arm);

  if (!client_arming_->wait_for_service(std::chrono::seconds(3))) {
    res->success = false;
    res->message = "mavros /cmd/arming unavailable";
    return;
  }

  auto mav_req = std::make_shared<mavros_msgs::srv::CommandBool::Request>();
  mav_req->value = req->arm;

  auto future = client_arming_->async_send_request(mav_req);

  auto ret = rclcpp::spin_until_future_complete(
    this->get_node_base_interface(), future, std::chrono::seconds(3));

  if (ret != rclcpp::FutureReturnCode::SUCCESS) {
    res->success = false;
    res->message = "arm/disarm request timed out";
    return;
  }

  auto mav_res = future.get();
  res->success = mav_res->success;
  res->message = req->arm ? "armed" : "disarmed";
  RCLCPP_INFO(get_logger(), "Arm=%s → success=%d", req->arm?"true":"false", mav_res->success);
}

void MavlinkBridge::cb_set_flight_mode(
  const std::shared_ptr<easyfly_msgs::srv::SetFlightMode::Request>  req,
  std::shared_ptr<easyfly_msgs::srv::SetFlightMode::Response>       res)
{
  if (!client_set_mode_->wait_for_service(std::chrono::seconds(3))) {
    res->success = false;
    res->message = "mavros /set_mode unavailable";
    return;
  }

  auto mav_req = std::make_shared<mavros_msgs::srv::SetMode::Request>();

  switch (req->flight_mode) {
    case 0:  mav_req->custom_mode = "MANUAL";     break;
    case 1:  mav_req->custom_mode = "ALTCTL";     break;
    case 2:  mav_req->custom_mode = "POSCTL";     break;
    case 3:  mav_req->custom_mode = "OFFBOARD";   break;
    case 4:  mav_req->custom_mode = "STABILIZED"; break;
    case 5:  mav_req->custom_mode = "ACRO";       break;
    case 6:  mav_req->custom_mode = "RTL";        break;
    case 7:  mav_req->custom_mode = "LAND";       break;
    default:
      res->success = false;
      res->message = "unknown flight_mode=" + std::to_string(req->flight_mode);
      return;
  }

  auto future = client_set_mode_->async_send_request(mav_req);

  auto ret = rclcpp::spin_until_future_complete(
    this->get_node_base_interface(), future, std::chrono::seconds(3));

  if (ret != rclcpp::FutureReturnCode::SUCCESS) {
    res->success = false;
    res->message = "set_mode request timed out";
    return;
  }

  auto mav_res = future.get();
  res->success = mav_res->mode_sent;
  res->message = "mode=" + mav_req->custom_mode;
  RCLCPP_INFO(get_logger(), "SetMode → %s (success=%d)",
    mav_req->custom_mode.c_str(), mav_res->mode_sent);

  if (req->flight_mode == 3) {
    last_cmd_time_ = now();
  }
}

}  // namespace easyfly_mavlink_bridge
