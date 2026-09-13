// EasyFly M4: 多目标跟踪节点 (SORT)
//
// 数据流:
//   /detections (easyfly_msgs/DetectionInfoArray, M2 输出, 归一化 bbox)
//     → SORT (像素空间卡尔曼 + 匈牙利关联)
//     → /tracks (easyfly_msgs/TrackInfoArray, 稳定 track_id)
//     → /tracks_debug_image (叠加 track_id 的画框图像, 有订阅才发)
//
// 注意: 检测帧的图像尺寸未知 (消息只带归一化坐标), 由首帧 camera_info
// 或参数 image_width/image_height 获取 (默认 640x480, 与仿真一致)。
#include <map>
#include <memory>
#include <string>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_components/register_node_macro.hpp>
#include <ament_index_cpp/get_package_share_directory.hpp>
#include <yaml-cpp/yaml.h>
#include <opencv2/opencv.hpp>

#include <sensor_msgs/msg/image.hpp>
#include <easyfly_msgs/msg/detection_info_array.hpp>
#include <easyfly_msgs/msg/track_info_array.hpp>

#include "easyfly_multi_object_tracking/sort.hpp"

namespace easyfly_multi_object_tracking
{

class TrackingNode : public rclcpp::Node
{
public:
    explicit TrackingNode(const rclcpp::NodeOptions & options)
        : Node("easyfly_multi_object_tracking", options)
    {
        loadParams();

        sorter_ = std::make_unique<Sorter>(sort_params_);

        tracks_pub_ = create_publisher<easyfly_msgs::msg::TrackInfoArray>(
            params_.output_topic, 10);
        debug_pub_ = create_publisher<sensor_msgs::msg::Image>(
            params_.output_topic + "_debug_image", 10);
        if (params_.publish_debug_image) {
            image_sub_ = create_subscription<sensor_msgs::msg::Image>(
                params_.debug_image_topic, rclcpp::SensorDataQoS(),
                [this](sensor_msgs::msg::Image::ConstSharedPtr msg) { last_image_ = msg; });
        }

        det_sub_ = create_subscription<easyfly_msgs::msg::DetectionInfoArray>(
            params_.input_topic, 10,
            [this](easyfly_msgs::msg::DetectionInfoArray::ConstSharedPtr msg) {
                onDetections(msg);
            });

        RCLCPP_INFO(get_logger(),
                    "跟踪节点启动: %s → %s (iou=%.2f, max_lost=%d, min_hits=%d, 类别过滤=%s)",
                    params_.input_topic.c_str(), params_.output_topic.c_str(),
                    sort_params_.iou_threshold, sort_params_.max_lost_frames,
                    sort_params_.min_hits,
                    params_.target_classes.empty() ? "无(全部跟踪)"
                                                   : std::to_string(params_.target_classes.size()).c_str());
    }

private:
    struct NodeParams {
        std::string input_topic{"/detections"};
        std::string output_topic{"/tracks"};
        bool publish_debug_image{true};
        std::string debug_image_topic{"/detections_debug_image"};
        int image_width{640};
        int image_height{480};
        std::vector<std::string> target_classes;  // 空 = 全部
    };

    void loadParams()
    {
        declare_parameter<std::string>("config_file", "");
        std::string cfg = get_parameter("config_file").as_string();
        if (cfg.empty()) {
            cfg = ament_index_cpp::get_package_share_directory("easyfly_multi_object_tracking")
                  + "/config/tracking.yaml";
        }

        YAML::Node root = YAML::LoadFile(cfg);
        const auto & t = root["tracking"];

        params_.input_topic = t["input_topic"].as<std::string>("/detections");
        params_.output_topic = t["output_topic"].as<std::string>("/tracks");
        params_.publish_debug_image = t["publish_debug_image"].as<bool>(true);
        params_.debug_image_topic = t["debug_image_topic"].as<std::string>("/detections_debug_image");
        params_.image_width = t["image_width"].as<int>(640);
        params_.image_height = t["image_height"].as<int>(480);
        if (t["target_classes"])
            params_.target_classes = t["target_classes"].as<std::vector<std::string>>();

        sort_params_.iou_threshold = t["iou_threshold"].as<double>(0.3);
        sort_params_.max_lost_frames = t["max_lost_frames"].as<int>(30);
        sort_params_.min_hits = t["min_hits"].as<int>(3);
        sort_params_.max_tracks = t["max_tracks"].as<int>(100);
        sort_params_.dist_gate_scale = t["dist_gate_scale"].as<double>(1.5);  // Q19
    }

    bool classWanted(const std::string & name) const
    {
        if (params_.target_classes.empty()) return true;
        for (const auto & c : params_.target_classes)
            if (c == name) return true;
        return false;
    }

    void onDetections(const easyfly_msgs::msg::DetectionInfoArray::ConstSharedPtr & msg)
    {
        // 归一化 → 像素
        std::vector<DetectionInput> dets;
        dets.reserve(msg->detections.size());
        for (const auto & d : msg->detections) {
            if (!classWanted(d.class_name)) continue;
            DetectionInput di;
            di.box = BBox{
                (d.bbox_center_x - d.bbox_width / 2) * params_.image_width,
                (d.bbox_center_y - d.bbox_height / 2) * params_.image_height,
                (d.bbox_center_x + d.bbox_width / 2) * params_.image_width,
                (d.bbox_center_y + d.bbox_height / 2) * params_.image_height};
            di.confidence = d.confidence;
            di.class_name = d.class_name;
            // class_id: 用类别名映射 (SORT 内部只要求同类相等)
            di.class_id = classId(d.class_name);
            dets.push_back(di);
        }

        const auto tracks = sorter_->update(dets);

        // 发布 TrackInfoArray
        easyfly_msgs::msg::TrackInfoArray out;
        out.header = msg->header;
        out.tracks.reserve(tracks.size());
        for (const auto & t : tracks) {
            if (!t.confirmed && t.time_since_update > 0) continue;  // 未确认且未命中不发布
            easyfly_msgs::msg::TrackInfo ti;
            ti.header = msg->header;
            ti.track_id = t.track_id;
            ti.class_name = t.class_name;
            ti.confidence = t.confidence;
            // 滤波框 (归一化)
            ti.bbox_center_x = (t.box.x1 + t.box.x2) / 2 / params_.image_width;
            ti.bbox_center_y = (t.box.y1 + t.box.y2) / 2 / params_.image_height;
            ti.bbox_width = (t.box.x2 - t.box.x1) / params_.image_width;
            ti.bbox_height = (t.box.y2 - t.box.y1) / params_.image_height;
            // 3D 字段 (米) 暂填 0 — M5 pixel_to_3d 接入后扩展
            ti.velocity_x = t.vx;  // 像素/frame (沿用字段, 语义在注释中说明)
            ti.velocity_y = t.vy;
            ti.velocity_z = 0.0f;
            out.tracks.push_back(ti);
        }
        tracks_pub_->publish(out);

        // 调试图像: 在最近一帧检测调试图上叠加 track_id
        if (params_.publish_debug_image && last_image_ &&
            debug_pub_->get_subscription_count() > 0) {
            publishDebugImage(tracks, msg->header);
        }
    }

    void publishDebugImage(const std::vector<TrackOutput> & tracks,
                           const std_msgs::msg::Header & header)
    {
        // rgb8 → cv::Mat (仅画框)
        cv::Mat img(last_image_->height, last_image_->width, CV_8UC3,
                    const_cast<uint8_t *>(last_image_->data.data()), last_image_->step);
        for (const auto & t : tracks) {
            if (!t.confirmed) continue;
            const cv::Scalar color(0, 255, 255);  // 黄色 = track (区别于检测的绿色)
            cv::rectangle(img,
                          cv::Point(cvRound(t.box.x1), cvRound(t.box.y1)),
                          cv::Point(cvRound(t.box.x2), cvRound(t.box.y2)), color, 2);
            cv::putText(img, cv::format("#%d %s", t.track_id, t.class_name.c_str()),
                        cv::Point(cvRound(t.box.x1), cvRound(t.box.y1) - 4),
                        cv::FONT_HERSHEY_SIMPLEX, 0.6, color, 2);
        }
        // BGR→rgb8 发布
        cv::Mat rgb;
        cv::cvtColor(img, rgb, cv::COLOR_BGR2RGB);
        sensor_msgs::msg::Image msg;
        msg.header = header;
        msg.height = rgb.rows;
        msg.width = rgb.cols;
        msg.encoding = "rgb8";
        msg.is_bigendian = false;
        msg.step = rgb.cols * 3;
        msg.data.assign(rgb.data, rgb.data + rgb.total() * rgb.elemSize());
        debug_pub_->publish(msg);
    }

    int classId(const std::string & name)
    {
        auto it = class_ids_.find(name);
        if (it != class_ids_.end()) return it->second;
        const int id = static_cast<int>(class_ids_.size());
        class_ids_[name] = id;
        return id;
    }

    NodeParams params_;
    SortParams sort_params_;
    std::unique_ptr<Sorter> sorter_;
    std::map<std::string, int> class_ids_;

    rclcpp::Subscription<easyfly_msgs::msg::DetectionInfoArray>::SharedPtr det_sub_;
    rclcpp::Subscription<sensor_msgs::msg::Image>::SharedPtr image_sub_;
    sensor_msgs::msg::Image::ConstSharedPtr last_image_;
    rclcpp::Publisher<easyfly_msgs::msg::TrackInfoArray>::SharedPtr tracks_pub_;
    rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr debug_pub_;
};

}  // namespace easyfly_multi_object_tracking

RCLCPP_COMPONENTS_REGISTER_NODE(easyfly_multi_object_tracking::TrackingNode)
