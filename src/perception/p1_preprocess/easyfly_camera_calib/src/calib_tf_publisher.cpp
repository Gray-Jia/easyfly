// EasyFly P1: 标定结果 → 静态 TF 发布器
//
// 职责:
//   加载 config/sensors.yaml 中的传感器安装外参, 发布静态 TF:
//     base_link → camera_link → camera_color_optical_frame
//                                → camera_depth_optical_frame
//     base_link → livox_frame
//   TF 树中的动态部分 (odom→base_link) 由 easyfly_coord_transform 负责。
//
// 外参是标定结果的所有者: 修改传感器安装位置只需改 sensors.yaml + 重启本节点。

#include <chrono>
#include <string>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_components/register_node_macro.hpp>
#include <ament_index_cpp/get_package_share_directory.hpp>
#include <tf2_ros/static_transform_broadcaster.h>
#include <geometry_msgs/msg/transform_stamped.hpp>
#include <yaml-cpp/yaml.h>

namespace easyfly_camera_calib
{

struct Mount {
    std::string parent;
    std::string child;
    std::vector<double> translation;   // [x, y, z] m
    std::vector<double> rotation_rpy;  // [roll, pitch, yaw] rad
};

class CalibTfPublisher : public rclcpp::Node {
public:
    explicit CalibTfPublisher(const rclcpp::NodeOptions & options)
        : Node("calib_tf_publisher", options)
    {
        tf_broadcaster_ = std::make_shared<tf2_ros::StaticTransformBroadcaster>(this);

        declare_parameter<std::string>("calib_file", "");

        std::string calib_file = get_parameter("calib_file").as_string();
        if (calib_file.empty()) {
            // 默认取包内 config/sensors.yaml
            calib_file = ament_index_cpp::get_package_share_directory("easyfly_camera_calib")
                         + "/config/sensors.yaml";
        }

        loadAndPublish(calib_file);
    }

private:
    void loadAndPublish(const std::string & file)
    {
        YAML::Node root;
        try {
            root = YAML::LoadFile(file);
        } catch (const YAML::Exception & e) {
            RCLCPP_FATAL(get_logger(), "无法加载标定文件 %s: %s", file.c_str(), e.what());
            throw;
        }

        const auto sensors = root["sensors"];
        if (!sensors) {
            RCLCPP_FATAL(get_logger(), "标定文件缺少 'sensors' 节: %s", file.c_str());
            throw std::runtime_error("bad calib file");
        }

        std::vector<geometry_msgs::msg::TransformStamped> static_tfs;

        // ---- 相机安装位姿 + 光学系 ----
        const auto camera = sensors["camera"];
        if (camera) {
            auto mount = parseMount(camera["mount"]);
            static_tfs.push_back(makeTransform(mount));

            auto optical = camera["optical"];
            if (optical) {
                std::vector<double> t = parseVec(optical["translation"], 3);
                std::vector<double> r = parseVec(optical["rotation_rpy"], 3);
                for (const std::string & frame :
                     {optical["color_frame"].as<std::string>(),
                      optical["depth_frame"].as<std::string>()}) {
                    Mount m{mount.child, frame, t, r};
                    static_tfs.push_back(makeTransform(m));
                }
            }
            RCLCPP_INFO(get_logger(), "相机外参: %s → %s (+optical)",
                        mount.parent.c_str(), mount.child.c_str());
        }

        // ---- 雷达安装位姿 ----
        const auto lidar = sensors["lidar"];
        if (lidar && lidar["mount"]) {
            auto mount = parseMount(lidar["mount"]);
            static_tfs.push_back(makeTransform(mount));
            RCLCPP_INFO(get_logger(), "雷达外参: %s → %s",
                        mount.parent.c_str(), mount.child.c_str());
        }

        if (static_tfs.empty()) {
            RCLCPP_WARN(get_logger(), "标定文件中未找到任何外参定义");
            return;
        }

        tf_broadcaster_->sendTransform(static_tfs);
        RCLCPP_INFO(get_logger(), "已发布 %zu 条静态 TF", static_tfs.size());
    }

    Mount parseMount(const YAML::Node & node) const
    {
        if (!node || !node["parent"] || !node["child"]) {
            throw std::runtime_error("mount 节点缺少 parent/child");
        }
        return Mount{
            node["parent"].as<std::string>(),
            node["child"].as<std::string>(),
            parseVec(node["translation"], 3),
            parseVec(node["rotation_rpy"], 3)};
    }

    static std::vector<double> parseVec(const YAML::Node & node, size_t n)
    {
        std::vector<double> v;
        if (!node || !node.IsSequence()) {
            throw std::runtime_error("缺少数组字段");
        }
        for (const auto & item : node) v.push_back(item.as<double>());
        if (v.size() != n) {
            throw std::runtime_error("数组长度不符, 期望 " + std::to_string(n));
        }
        return v;
    }

    static geometry_msgs::msg::TransformStamped makeTransform(const Mount & m)
    {
        geometry_msgs::msg::TransformStamped tf;
        tf.header.frame_id = m.parent;
        tf.child_frame_id = m.child;
        tf.transform.translation.x = m.translation[0];
        tf.transform.translation.y = m.translation[1];
        tf.transform.translation.z = m.translation[2];

        // rpy → 四元数 (ZYX 惯例)
        const double cr = std::cos(m.rotation_rpy[0] * 0.5);
        const double sr = std::sin(m.rotation_rpy[0] * 0.5);
        const double cp = std::cos(m.rotation_rpy[1] * 0.5);
        const double sp = std::sin(m.rotation_rpy[1] * 0.5);
        const double cy = std::cos(m.rotation_rpy[2] * 0.5);
        const double sy = std::sin(m.rotation_rpy[2] * 0.5);
        tf.transform.rotation.x = sr * cp * cy - cr * sp * sy;
        tf.transform.rotation.y = cr * sp * cy + sr * cp * sy;
        tf.transform.rotation.z = cr * cp * sy - sr * sp * cy;
        tf.transform.rotation.w = cr * cp * cy + sr * sp * sy;
        return tf;
    }

    std::shared_ptr<tf2_ros::StaticTransformBroadcaster> tf_broadcaster_;
};

}  // namespace easyfly_camera_calib

RCLCPP_COMPONENTS_REGISTER_NODE(easyfly_camera_calib::CalibTfPublisher)
