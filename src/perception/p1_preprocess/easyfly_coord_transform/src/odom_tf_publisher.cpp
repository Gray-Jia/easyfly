// EasyFly P1: 里程计 TF 发布器
//
// 职责:
//   订阅 /uav_state (easyfly_mavlink_bridge 聚合, 来自 mavros local_position/pose,
//   姿态与位置均为 ENU 系, 机体 FLU), 发布:
//     TF  odom → base_link   (50 Hz, TF 树的动态主干)
//     话题 /odom             (nav_msgs/Odometry, 供 FAST-LIO 对照/规划层使用)
//
//   TF 树全景 (M1 完成后):
//     odom ── base_link ── camera_link ── camera_color_optical_frame
//           │                        └── camera_depth_optical_frame
//           └── livox_frame          (静态部分由 easyfly_camera_calib 发布)
//   map 坐标系将在 M3 (FAST-LIO) 接入后提供 map→odom。

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_components/register_node_macro.hpp>
#include <tf2_ros/transform_broadcaster.h>
#include <geometry_msgs/msg/transform_stamped.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <easyfly_msgs/msg/uav_state.hpp>

namespace easyfly_coord_transform
{

class OdomTfPublisher : public rclcpp::Node {
public:
    explicit OdomTfPublisher(const rclcpp::NodeOptions & options)
        : Node("odom_tf_publisher", options)
    {
        declare_parameter<std::string>("uav_state_topic", "/uav_state");
        declare_parameter<std::string>("odom_frame", "odom");
        declare_parameter<std::string>("base_frame", "base_link");
        declare_parameter<double>("publish_rate", 50.0);

        const std::string odom_frame = get_parameter("odom_frame").as_string();
        const std::string base_frame = get_parameter("base_frame").as_string();
        const double rate = get_parameter("publish_rate").as_double();

        tf_broadcaster_ = std::make_shared<tf2_ros::TransformBroadcaster>(this);
        odom_pub_ = create_publisher<nav_msgs::msg::Odometry>("/odom", 10);

        state_sub_ = create_subscription<easyfly_msgs::msg::UAVState>(
            get_parameter("uav_state_topic").as_string(), 10,
            [this](easyfly_msgs::msg::UAVState::ConstSharedPtr msg) {
                latest_ = msg;
                got_state_ = true;
            });

        timer_ = create_wall_timer(
            std::chrono::duration<double>(1.0 / rate),
            [this, odom_frame, base_frame]() { publish(odom_frame, base_frame); });

        RCLCPP_INFO(get_logger(), "odom_tf_publisher 启动: %s → %s @ %.0f Hz",
                    odom_frame.c_str(), base_frame.c_str(), rate);
    }

private:
    void publish(const std::string & odom_frame, const std::string & base_frame)
    {
        if (!got_state_) return;
        const auto & s = *latest_;

        // rpy (ZYX) → 四元数; /uav_state 姿态由 mavros ENU 四元数分解而来
        const double cr = std::cos(s.roll * 0.5),  sr = std::sin(s.roll * 0.5);
        const double cp = std::cos(s.pitch * 0.5), sp = std::sin(s.pitch * 0.5);
        const double cy = std::cos(s.yaw * 0.5),   sy = std::sin(s.yaw * 0.5);

        geometry_msgs::msg::TransformStamped tf;
        tf.header.stamp = s.header.stamp;
        tf.header.frame_id = odom_frame;
        tf.child_frame_id = base_frame;
        tf.transform.translation.x = s.position_x;
        tf.transform.translation.y = s.position_y;
        tf.transform.translation.z = s.position_z;
        tf.transform.rotation.x = sr * cp * cy - cr * sp * sy;
        tf.transform.rotation.y = cr * sp * cy + sr * cp * sy;
        tf.transform.rotation.z = cr * cp * sy - sr * sp * cy;
        tf.transform.rotation.w = cr * cp * cy + sr * sp * sy;
        tf_broadcaster_->sendTransform(tf);

        nav_msgs::msg::Odometry odom;
        odom.header = tf.header;
        odom.child_frame_id = base_frame;
        odom.pose.pose.position.x = s.position_x;
        odom.pose.pose.position.y = s.position_y;
        odom.pose.pose.position.z = s.position_z;
        odom.pose.pose.orientation = tf.transform.rotation;

        // Odometry 惯例: twist 在 child_frame (base_link/FLU) 系
        // /uav_state 速度为 ENU 系 → v_body = R(world→body) · v_world
        // R (body→world) = Rz(yaw)·Ry(pitch)·Rx(roll); v_body = Rᵀ·v_world
        const double r00 = cy * cp, r10 = sy * cp, r20 = -sp;
        const double r01 = cy * sp * sr - sy * cr, r11 = sy * sp * sr + cy * cr, r21 = cp * sr;
        const double r02 = cy * sp * cr + sy * sr, r12 = sy * sp * cr - cy * sr, r22 = cp * cr;
        odom.twist.twist.linear.x = r00 * s.velocity_x + r10 * s.velocity_y + r20 * s.velocity_z;
        odom.twist.twist.linear.y = r01 * s.velocity_x + r11 * s.velocity_y + r21 * s.velocity_z;
        odom.twist.twist.linear.z = r02 * s.velocity_x + r12 * s.velocity_y + r22 * s.velocity_z;
        odom.twist.twist.angular.x = s.rollspeed;
        odom.twist.twist.angular.y = s.pitchspeed;
        odom.twist.twist.angular.z = s.yawspeed;
        odom_pub_->publish(odom);
    }

    easyfly_msgs::msg::UAVState::ConstSharedPtr latest_;
    bool got_state_{false};

    std::shared_ptr<tf2_ros::TransformBroadcaster> tf_broadcaster_;
    rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr odom_pub_;
    rclcpp::Subscription<easyfly_msgs::msg::UAVState>::SharedPtr state_sub_;
    rclcpp::TimerBase::SharedPtr timer_;
};

}  // namespace easyfly_coord_transform

RCLCPP_COMPONENTS_REGISTER_NODE(easyfly_coord_transform::OdomTfPublisher)
