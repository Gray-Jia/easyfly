// EasyFly P2: 目标检测公共数据结构
#ifndef EASYFLY_OBJECT_DETECTION_TYPES_HPP_
#define EASYFLY_OBJECT_DETECTION_TYPES_HPP_

#include <string>
#include <vector>

namespace easyfly_object_detection
{

/// 检测结果 (原图像素坐标, xyxy)
struct Detection {
    float x1{0}, y1{0}, x2{0}, y2{0};   // 像素坐标
    float confidence{0};                 // 置信度
    int class_id{-1};                    // 类别 id
    std::string class_name;              // 类别名
};

/// 检测器参数 (全部来自 config/detection.yaml)
struct DetectorParams {
    // 模型
    std::string backend{"onnx"};             // onnx | tensorrt(预留)
    std::string model_path;                  // ONNX 文件绝对路径
    std::vector<std::string> class_names;    // 类别表 (顺序必须与训练 data.yaml 一致!)
    int imgsz{640};                          // 模型输入边长
    // 阈值
    double conf_threshold{0.35};
    double nms_threshold{0.45};
    // 运行
    bool use_gpu{true};                      // CUDA EP 失败时自动回退 CPU
    int gpu_device_id{0};
    int max_detections{100};
    // 节点
    std::string input_topic{"/camera/color/image_raw"};
    std::string output_topic{"/detections"};
    bool publish_debug_image{true};
};

}  // namespace easyfly_object_detection

#endif  // EASYFLY_OBJECT_DETECTION_TYPES_HPP_
