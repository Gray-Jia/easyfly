// EasyFly P2: 目标检测 ROS2 组件节点
//
// 数据流:
//   /camera/color/image_raw (rgb8)
//     → OnnxRuntime 推理 (CUDA EP 优先)
//     → /detections              (easyfly_msgs/DetectionInfoArray, 归一化 bbox)
//     → /detections_debug_image  (画框可视化, 可配置关闭)
//
// 设计:
//   - 图像 rgb8 → cv::Mat BGR 手动转换 (不依赖 cv_bridge)
//   - 推理在专用线程执行, 不阻塞 executor spin
//   - max_fps 节流: 丢帧策略 (推理中收到新帧直接替换 pending)
#include <atomic>
#include <chrono>
#include <memory>
#include <mutex>
#include <thread>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_components/register_node_macro.hpp>
#include <ament_index_cpp/get_package_share_directory.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <yaml-cpp/yaml.h>

#include <opencv2/opencv.hpp>

#include <easyfly_msgs/msg/detection_info_array.hpp>

#include "easyfly_object_detection/backend_factory.hpp"

namespace easyfly_object_detection
{

namespace
{
/// rgb8 sensor_msgs → BGR cv::Mat (逐字节交换 R/B)
cv::Mat rgb8_to_bgr_mat(const sensor_msgs::msg::Image & msg)
{
    cv::Mat rgb(msg.height, msg.width, CV_8UC3,
                const_cast<uint8_t *>(msg.data.data()), msg.step);
    cv::Mat bgr;
    cv::cvtColor(rgb, bgr, cv::COLOR_RGB2BGR);
    return bgr;
}

/// BGR cv::Mat → rgb8 sensor_msgs
sensor_msgs::msg::Image bgr_mat_to_rgb8(const cv::Mat & bgr, const std_msgs::msg::Header & header)
{
    cv::Mat rgb;
    cv::cvtColor(bgr, rgb, cv::COLOR_BGR2RGB);
    sensor_msgs::msg::Image msg;
    msg.header = header;
    msg.height = rgb.rows;
    msg.width = rgb.cols;
    msg.encoding = "rgb8";
    msg.is_bigendian = false;
    msg.step = rgb.cols * 3;
    msg.data.assign(rgb.data, rgb.data + rgb.total() * rgb.elemSize());
    return msg;
}
}  // namespace

class DetectionNode : public rclcpp::Node
{
public:
    explicit DetectionNode(const rclcpp::NodeOptions & options)
        : Node("easyfly_object_detection", options)
    {
        loadParams();

        // 后端初始化 + 预热 (阻塞 ~ 秒级, 放在构造函数保证就绪后才开始订阅)
        detector_ = createBackend(params_);
        detector_->warmUp();

        detections_pub_ = create_publisher<easyfly_msgs::msg::DetectionInfoArray>(
            params_.output_topic, 10);
        if (params_.publish_debug_image) {
            debug_pub_ = create_publisher<sensor_msgs::msg::Image>(
                params_.output_topic + "_debug_image", 10);
        }

        image_sub_ = create_subscription<sensor_msgs::msg::Image>(
            params_.input_topic, rclcpp::SensorDataQoS(),
            [this](sensor_msgs::msg::Image::ConstSharedPtr msg) {
                std::lock_guard<std::mutex> lk(pending_mtx_);
                pending_ = msg;               // 最新帧覆盖旧帧 (丢帧节流)
                pending_cv_.notify_one();
            });

        // 推理线程
        worker_ = std::thread([this] { workerLoop(); });

        RCLCPP_INFO(get_logger(),
                    "检测节点启动: %s → %s (%s, imgsz=%d, conf=%.2f)",
                    params_.input_topic.c_str(), params_.output_topic.c_str(),
                    params_.backend.c_str(), params_.imgsz, params_.conf_threshold);
    }

    ~DetectionNode() override
    {
        stop_ = true;
        {
            std::lock_guard<std::mutex> lk(pending_mtx_);
            pending_cv_.notify_all();
        }
        if (worker_.joinable()) worker_.join();
    }

private:
    void loadParams()
    {
        // config 文件路径 (launch 传入) 或默认包内 detection.yaml
        declare_parameter<std::string>("config_file", "");
        std::string cfg = get_parameter("config_file").as_string();
        if (cfg.empty()) {
            cfg = ament_index_cpp::get_package_share_directory("easyfly_object_detection")
                  + "/config/detection.yaml";
        }

        YAML::Node root = YAML::LoadFile(cfg);
        const auto & d = root["detection"];

        params_.backend = d["backend"].as<std::string>("onnx");
        params_.model_path = d["model_path"].as<std::string>();
        params_.imgsz = d["imgsz"].as<int>(640);
        params_.conf_threshold = d["conf_threshold"].as<double>(0.35);
        params_.nms_threshold = d["nms_threshold"].as<double>(0.45);
        params_.use_gpu = d["use_gpu"].as<bool>(true);
        params_.gpu_device_id = d["gpu_device_id"].as<int>(0);
        params_.max_detections = d["max_detections"].as<int>(100);
        params_.input_topic = d["input_topic"].as<std::string>("/camera/color/image_raw");
        params_.output_topic = d["output_topic"].as<std::string>("/detections");
        params_.publish_debug_image = d["publish_debug_image"].as<bool>(true);

        if (d["class_names"]) {
            params_.class_names = d["class_names"].as<std::vector<std::string>>();
        }
        if (params_.class_names.empty()) {
            RCLCPP_FATAL(get_logger(), "detection.yaml 缺少 class_names");
            throw std::runtime_error("class_names empty");
        }

        max_interval_ = std::chrono::duration<double>(
            1.0 / d["max_fps"].as<double>(30.0));
    }

    void workerLoop()
    {
        while (!stop_) {
            sensor_msgs::msg::Image::ConstSharedPtr frame;
            {
                std::unique_lock<std::mutex> lk(pending_mtx_);
                pending_cv_.wait(lk, [this] { return stop_ || pending_ != nullptr; });
                if (stop_) return;
                frame = pending_;
                pending_ = nullptr;
            }

            const auto t0 = std::chrono::steady_clock::now();

            cv::Mat bgr = rgb8_to_bgr_mat(*frame);
            std::vector<Detection> dets;
            detector_->detect(bgr, dets);

            // 发布 DetectionInfoArray (归一化)
            easyfly_msgs::msg::DetectionInfoArray msg;
            msg.header = frame->header;  // 保留原始时间戳, 供 M5 时空对齐
            msg.detections.reserve(dets.size());
            for (const auto & d : dets) {
                easyfly_msgs::msg::DetectionInfo info;
                info.header = frame->header;
                info.track_id = -1;  // M4 跟踪器填充
                info.class_name = d.class_name;
                info.confidence = d.confidence;
                // 归一化 (图像像素坐标)
                info.bbox_center_x = (d.x1 + d.x2) * 0.5f / bgr.cols;
                info.bbox_center_y = (d.y1 + d.y2) * 0.5f / bgr.rows;
                info.bbox_width = (d.x2 - d.x1) / bgr.cols;
                info.bbox_height = (d.y2 - d.y1) / bgr.rows;
                info.position_valid = false;  // M5 pixel_to_3d 填充
                msg.detections.push_back(info);
            }
            detections_pub_->publish(msg);

            // 调试图像
            if (params_.publish_debug_image && debug_pub_->get_subscription_count() > 0) {
                for (const auto & d : dets) {
                    cv::rectangle(bgr,
                                  cv::Point(cvRound(d.x1), cvRound(d.y1)),
                                  cv::Point(cvRound(d.x2), cvRound(d.y2)),
                                  cv::Scalar(0, 255, 0), 2);
                    cv::putText(bgr,
                                d.class_name + " " + cv::format("%.2f", d.confidence),
                                cv::Point(cvRound(d.x1), cvRound(d.y1) - 4),
                                cv::FONT_HERSHEY_SIMPLEX, 0.5, cv::Scalar(0, 255, 0), 1);
                }
                debug_pub_->publish(bgr_mat_to_rgb8(bgr, frame->header));
            }

            // 节流
            const auto elapsed = std::chrono::steady_clock::now() - t0;
            if (elapsed < max_interval_) {
                std::this_thread::sleep_for(max_interval_ - elapsed);
            }
        }
    }

    DetectorParams params_;
    std::unique_ptr<DetectorBase> detector_;

    rclcpp::Subscription<sensor_msgs::msg::Image>::SharedPtr image_sub_;
    rclcpp::Publisher<easyfly_msgs::msg::DetectionInfoArray>::SharedPtr detections_pub_;
    rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr debug_pub_;

    std::thread worker_;
    std::atomic<bool> stop_{false};
    std::mutex pending_mtx_;
    std::condition_variable pending_cv_;
    sensor_msgs::msg::Image::ConstSharedPtr pending_;
    std::chrono::duration<double> max_interval_{0};
};

}  // namespace easyfly_object_detection

RCLCPP_COMPONENTS_REGISTER_NODE(easyfly_object_detection::DetectionNode)
