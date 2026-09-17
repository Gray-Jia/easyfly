// EasyFly P2: OnnxRuntime 后端 (CUDA EP 优先, CPU EP 自动回退)
#ifndef EASYFLY_OBJECT_DETECTION_ONNX_BACKEND_HPP_
#define EASYFLY_OBJECT_DETECTION_ONNX_BACKEND_HPP_

#include <memory>

#include <onnxruntime_cxx_api.h>

#include "easyfly_object_detection/detector_base.hpp"
#include "easyfly_object_detection/letterbox.hpp"

namespace easyfly_object_detection
{

class OnnxBackend : public DetectorBase
{
public:
    explicit OnnxBackend(const DetectorParams & params);
    ~OnnxBackend() override = default;

    /// 实际生效的 EP 名 ("CUDAExecutionProvider" / "CPUExecutionProvider")
    std::string activeProvider() const override { return active_provider_; }

protected:
    void detectImpl(const cv::Mat & bgr_img, std::vector<Detection> & detections,
                    DetectionTiming * timing) override;
    void unletterboxImpl(Detection & d) override { unletterbox(d.x1, d.y1, d.x2, d.y2, last_lb_); }

private:
    void createSession(const char * log_tag);
    void parseOutput(const float * output, int num_preds, int num_classes,
                     std::vector<Detection> & detections);

    Ort::Env env_{nullptr};
    Ort::SessionOptions session_opts_{nullptr};
    std::unique_ptr<Ort::Session> session_;
    Ort::AllocatorWithDefaultOptions allocator_;
    std::string input_name_;
    std::vector<std::string> output_names_;

    // 预分配的推理缓冲
    std::vector<float> input_tensor_;        // 1*3*imgsz*imgsz
    std::vector<float> output_tensor_;       // 1*(4+nc)*num_preds
    LetterboxInfo last_lb_;
    std::string active_provider_;
    // 输出布局: num_classes_ 与 num_preds_ 从模型 shape 推断
    int num_classes_{0};
    int num_preds_{0};
};

}  // namespace easyfly_object_detection

#endif  // EASYFLY_OBJECT_DETECTION_ONNX_BACKEND_HPP_
