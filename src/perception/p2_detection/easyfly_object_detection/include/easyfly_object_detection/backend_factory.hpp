// EasyFly P2: 检测后端运行时工厂
// 配置 params.backend 决定实例化哪个后端 (区别于 SpireCV 编译宏, 换后端不重编译)
#ifndef EASYFLY_OBJECT_DETECTION_BACKEND_FACTORY_HPP_
#define EASYFLY_OBJECT_DETECTION_BACKEND_FACTORY_HPP_

#include <memory>
#include <stdexcept>
#include <string>

#include "easyfly_object_detection/detector_base.hpp"
#include "easyfly_object_detection/onnx_backend.hpp"

namespace easyfly_object_detection
{

inline std::unique_ptr<DetectorBase> createBackend(const DetectorParams & params)
{
    if (params.backend == "onnx") {
        return std::make_unique<OnnxBackend>(params);
    }
    if (params.backend == "tensorrt") {
        // TensorRT 后端预留位 (对应 src/cuda/), 接入时在此分支实例化
        throw std::runtime_error(
            "backend 'tensorrt' 尚未实现 — 当前可用: onnx (留此接口供后续扩展)");
    }
    if (params.backend == "openvino") {
        // OpenVINO 后端预留位 (对应 src/intel/)
        throw std::runtime_error(
            "backend 'openvino' 尚未实现 — 当前可用: onnx (留此接口供后续扩展)");
    }
    throw std::runtime_error("未知 backend: " + params.backend + " (可用: onnx)");
}

}  // namespace easyfly_object_detection

#endif  // EASYFLY_OBJECT_DETECTION_BACKEND_FACTORY_HPP_
