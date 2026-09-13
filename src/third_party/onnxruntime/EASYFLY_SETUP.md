# EasyFly 集成说明（本目录不入 git）

本目录存放 onnxruntime C++ SDK，因 `lib/libonnxruntime_providers_cuda.so` 单文件 352MB
超过 GitHub 100MB 限制，整个目录被 .gitignore 排除，首次克隆后需手动放置。
easyfly_object_detection 运行时依赖（CMake RPATH $ORIGIN，部署自包含）。

## 当前版本

- onnxruntime **1.23.2** linux-x64 **GPU** (CUDA EP)
- 结构: `include/onnxruntime/...` + `lib/libonnxruntime*.so` (+ LICENSE 等上游文件)

## 获取

```bash
cd src/third_party/onnxruntime
wget https://github.com/microsoft/onnxruntime/releases/download/v1.23.2/onnxruntime-linux-x64-gpu-1.23.2.tgz
tar xzf onnxruntime-linux-x64-gpu-1.23.2.tgz --strip-components=1
```

注意:
- CUDA EP 需与本机 CUDA/cuDNN 匹配；不匹配时检测节点自动回退 CPU EP（可用，慢 ~10 倍）。
- YOLO11n 模型文件在 `easyfly_ws/models/yolo11n.onnx`（models/ 已入库）。
- ONNX 模型导出要求: opset 12, IR version ≤ 10（onnxruntime 1.23 支持上限，见 schedule.md M2）。
