// EasyFly P1: 点云滤波节点
//
// 数据流:
//   /livox/lidar (livox_ros_driver2/CustomMsg, livox_frame, 10Hz 20000点)
//     → 距离滤波 (盲区 0.3m / 远界) + 体素降采样 (filter_core.hpp, 可单测)
//     → [可选] TF 变换到 output_frame (默认 base_link, 与 EGO grid_map 的
//       "cloud 在 body 系" 假设对齐; 变换用静态外参链, 无时间依赖)
//     → /pointcloud_filtered (sensor_msgs/PointCloud2, x/y/z/intensity)
//
// 消费方: easyfly_semantic_map (M4.0 聚类/栅格)、EGO-Planner (M4.3 grid_map/cloud)。
#include <chrono>
#include <cstring>
#include <memory>
#include <string>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_components/register_node_macro.hpp>
#include <ament_index_cpp/get_package_share_directory.hpp>
#include <yaml-cpp/yaml.h>

#include <sensor_msgs/msg/point_cloud2.hpp>
#include <sensor_msgs/msg/point_field.hpp>
#include <livox_ros_driver2/msg/custom_msg.hpp>
#include <tf2_ros/buffer.h>
#include <tf2_ros/transform_listener.h>
#include <tf2_eigen/tf2_eigen.hpp>
#include <Eigen/Geometry>

#include "easyfly_pointcloud_filter/filter_core.hpp"

namespace easyfly_pointcloud_filter
{

class PointcloudFilterNode : public rclcpp::Node
{
public:
    explicit PointcloudFilterNode(const rclcpp::NodeOptions & options)
        : Node("easyfly_pointcloud_filter", options)
    {
        loadParams();

        tf_buffer_ = std::make_unique<tf2_ros::Buffer>(get_clock());
        tf_listener_ = std::make_unique<tf2_ros::TransformListener>(*tf_buffer_);

        pub_ = create_publisher<sensor_msgs::msg::PointCloud2>(
            params_.output_topic, 10);

        // livox 插件/驱动发布为默认 reliable QoS (depth 5)
        sub_ = create_subscription<livox_ros_driver2::msg::CustomMsg>(
            params_.input_topic, 10,
            [this](livox_ros_driver2::msg::CustomMsg::ConstSharedPtr msg) { onCloud(msg); });

        RCLCPP_INFO(get_logger(),
                    "点云滤波启动: %s → %s (范围 %.1f~%.1fm, 体素 %.2fm, 输出系: %s)",
                    params_.input_topic.c_str(), params_.output_topic.c_str(),
                    params_.range_min, params_.range_max, params_.voxel_size,
                    params_.output_frame.empty() ? "<源系>" : params_.output_frame.c_str());
    }

private:
    struct NodeParams {
        std::string input_topic{"/livox/lidar"};
        std::string output_topic{"/pointcloud_filtered"};
        float range_min{0.3f};
        float range_max{25.0f};
        float voxel_size{0.1f};
        std::string output_frame{"base_link"};   // 空 = 保持源系 (livox_frame)
    };

    void loadParams()
    {
        declare_parameter<std::string>("config_file", "");
        std::string cfg = get_parameter("config_file").as_string();
        if (cfg.empty()) {
            cfg = ament_index_cpp::get_package_share_directory("easyfly_pointcloud_filter")
                  + "/config/pointcloud_filter.yaml";
        }
        YAML::Node root = YAML::LoadFile(cfg);
        const auto & p = root["pointcloud_filter"];
        params_.input_topic = p["input_topic"].as<std::string>(params_.input_topic);
        params_.output_topic = p["output_topic"].as<std::string>(params_.output_topic);
        params_.range_min = p["range_min"].as<double>(params_.range_min);
        params_.range_max = p["range_max"].as<double>(params_.range_max);
        params_.voxel_size = p["voxel_size"].as<double>(params_.voxel_size);
        params_.output_frame = p["output_frame"].as<std::string>(params_.output_frame);
    }

    /// 与 pixel_to_3d 同款双路容错: 先按消息时间戳查, 静态链失败回退 latest
    bool lookupTransform(const std::string & target, const std::string & source,
                         const rclcpp::Time & stamp, Eigen::Isometry3d & out)
    {
        try {
            auto tf = tf_buffer_->lookupTransform(target, source, stamp,
                                                  rclcpp::Duration::from_seconds(0.05));
            out = tf2::transformToEigen(tf);
            return true;
        } catch (const tf2::TransformException &) {
            try {
                auto tf = tf_buffer_->lookupTransform(target, source, tf2::TimePointZero);
                out = tf2::transformToEigen(tf);
                return true;
            } catch (const tf2::TransformException & e2) {
                RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 5000,
                                     "TF %s←%s 不可用: %s", target.c_str(), source.c_str(), e2.what());
                return false;
            }
        }
    }

    void onCloud(const livox_ros_driver2::msg::CustomMsg::ConstSharedPtr & msg)
    {
        // CustomMsg → 点向量 + 距离滤波 + 体素降采样
        std::vector<Pt> pts;
        pts.reserve(msg->point_num);
        for (const auto & p : msg->points) {
            pts.push_back({p.x, p.y, p.z,
                           static_cast<float>(p.reflectivity)});
        }
        pts = filterCloud(pts, params_.range_min, params_.range_max, params_.voxel_size);

        // 可选 TF 变换到 output_frame
        std::string frame = msg->header.frame_id;
        if (!params_.output_frame.empty()) {
            Eigen::Isometry3d T;
            if (lookupTransform(params_.output_frame, msg->header.frame_id,
                                rclcpp::Time(msg->header.stamp), T)) {
                for (auto & p : pts) {
                    const Eigen::Vector3d v = T * Eigen::Vector3d(p.x, p.y, p.z);
                    p.x = static_cast<float>(v.x());
                    p.y = static_cast<float>(v.y());
                    p.z = static_cast<float>(v.z());
                }
                frame = params_.output_frame;
            } else {
                return;  // TF 未就绪 (如 launch 启动竞态), 丢本帧
            }
        }

        // → PointCloud2 (x,y,z,intensity, 各 FLOAT32, point_step=16)
        sensor_msgs::msg::PointCloud2 out;
        out.header.stamp = msg->header.stamp;
        out.header.frame_id = frame;
        out.height = 1;
        out.width = static_cast<uint32_t>(pts.size());
        out.is_dense = true;
        out.is_bigendian = false;
        out.point_step = 16;
        out.row_step = out.point_step * out.width;
        out.fields.resize(4);
        const char * names[4] = {"x", "y", "z", "intensity"};
        for (int i = 0; i < 4; ++i) {
            out.fields[i].name = names[i];
            out.fields[i].offset = static_cast<uint32_t>(4 * i);
            out.fields[i].datatype = sensor_msgs::msg::PointField::FLOAT32;
            out.fields[i].count = 1;
        }
        out.data.resize(out.row_step);
        auto * dst = out.data.data();
        for (const auto & p : pts) {
            std::memcpy(dst, &p.x, 4); dst += 4;
            std::memcpy(dst, &p.y, 4); dst += 4;
            std::memcpy(dst, &p.z, 4); dst += 4;
            std::memcpy(dst, &p.intensity, 4); dst += 4;
        }
        pub_->publish(out);
    }

    NodeParams params_;
    std::unique_ptr<tf2_ros::Buffer> tf_buffer_;
    std::unique_ptr<tf2_ros::TransformListener> tf_listener_;
    rclcpp::Subscription<livox_ros_driver2::msg::CustomMsg>::SharedPtr sub_;
    rclcpp::Publisher<sensor_msgs::msg::PointCloud2>::SharedPtr pub_;
};

}  // namespace easyfly_pointcloud_filter

RCLCPP_COMPONENTS_REGISTER_NODE(easyfly_pointcloud_filter::PointcloudFilterNode)
