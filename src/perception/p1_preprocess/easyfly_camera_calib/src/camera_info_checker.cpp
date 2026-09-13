// EasyFly P1: 相机内参一致性校验
//
// 订阅仿真实机驱动的 /camera/color/camera_info, 与 sensors.yaml 中的标定内参对比:
//   偏差 > tolerance → WARN (外参/内参失配, 3D 投影会出错)
//   偏差 ≤ tolerance → INFO 一次性确认
// 用途: 修改 SDF 分辨率/FOV 或切换实机相机后, 立即发现 sensors.yaml 未同步。

#include <cmath>
#include <string>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_components/register_node_macro.hpp>
#include <ament_index_cpp/get_package_share_directory.hpp>
#include <sensor_msgs/msg/camera_info.hpp>
#include <yaml-cpp/yaml.h>

namespace easyfly_camera_calib
{

class CameraInfoChecker : public rclcpp::Node {
public:
    explicit CameraInfoChecker(const rclcpp::NodeOptions & options)
        : Node("camera_info_checker", options)
    {
        declare_parameter<std::string>("calib_file", "");
        declare_parameter<std::string>("camera_info_topic", "/camera/color/camera_info");
        declare_parameter<double>("tolerance", 1.0);  // 像素

        std::string calib_file = get_parameter("calib_file").as_string();
        if (calib_file.empty()) {
            calib_file = ament_index_cpp::get_package_share_directory("easyfly_camera_calib")
                         + "/config/sensors.yaml";
        }
        tolerance_ = get_parameter("tolerance").as_double();

        YAML::Node root;
        try {
            root = YAML::LoadFile(calib_file);
            const auto intr = root["sensors"]["camera"]["intrinsics"];
            if (!intr) throw std::runtime_error("缺少 camera.intrinsics");
            ref_.width  = intr["width"].as<int>();
            ref_.height = intr["height"].as<int>();
            ref_.fx = intr["fx"].as<double>();
            ref_.fy = intr["fy"].as<double>();
            ref_.cx = intr["cx"].as<double>();
            ref_.cy = intr["cy"].as<double>();
        } catch (const std::exception & e) {
            RCLCPP_FATAL(get_logger(), "加载标定内参失败: %s", e.what());
            throw;
        }

        sub_ = create_subscription<sensor_msgs::msg::CameraInfo>(
            get_parameter("camera_info_topic").as_string(), rclcpp::SensorDataQoS(),
            [this](sensor_msgs::msg::CameraInfo::ConstSharedPtr msg) { check(*msg); });
    }

private:
    void check(const sensor_msgs::msg::CameraInfo & msg)
    {
        if (checked_) return;

        const double fx = msg.k[0], fy = msg.k[4], cx = msg.k[2], cy = msg.k[5];
        auto diff = [this](double a, double b) {
            return std::fabs(a - b) > tolerance_;
        };

        if (msg.width != static_cast<uint32_t>(ref_.width) ||
            msg.height != static_cast<uint32_t>(ref_.height)) {
            RCLCPP_WARN(get_logger(),
                "内参失配: 分辨率 实际=%ux%u 标定=%dx%d — 请同步 sensors.yaml",
                msg.width, msg.height, ref_.width, ref_.height);
        } else if (diff(fx, ref_.fx) || diff(fy, ref_.fy) ||
                   diff(cx, ref_.cx) || diff(cy, ref_.cy)) {
            RCLCPP_WARN(get_logger(),
                "内参失配: 实际 fx=%.2f fy=%.2f cx=%.2f cy=%.2f | "
                "标定 fx=%.2f fy=%.2f cx=%.2f cy=%.2f — 请同步 sensors.yaml",
                fx, fy, cx, cy, ref_.fx, ref_.fy, ref_.cx, ref_.cy);
        } else {
            RCLCPP_INFO(get_logger(),
                "内参校验通过: %ux%u fx=%.2f fy=%.2f cx=%.2f cy=%.2f",
                msg.width, msg.height, fx, fy, cx, cy);
        }
        checked_ = true;
    }

    struct Reference { int width{}, height{}; double fx{}, fy{}, cx{}, cy{}; } ref_;
    double tolerance_{1.0};
    bool checked_{false};
    rclcpp::Subscription<sensor_msgs::msg::CameraInfo>::SharedPtr sub_;
};

}  // namespace easyfly_camera_calib

RCLCPP_COMPONENTS_REGISTER_NODE(easyfly_camera_calib::CameraInfoChecker)
