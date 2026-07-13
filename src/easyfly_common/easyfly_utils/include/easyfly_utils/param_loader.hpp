#ifndef EASYFLY_UTILS_PARAM_LOADER_HPP_
#define EASYFLY_UTILS_PARAM_LOADER_HPP_

#include <string>
#include <map>
#include <fstream>
#include <iostream>

namespace easyfly_utils {

class ParamLoader {
public:
  bool load(const std::string& path) {
    // 简化实现: 读取 key=value 格式文件
    std::ifstream file(path);
    if (!file.is_open()) return false;
    std::string line;
    while (std::getline(file, line)) {
      auto pos = line.find('=');
      if (pos != std::string::npos) {
        params_[line.substr(0, pos)] = line.substr(pos + 1);
      }
    }
    return true;
  }

  std::string get(const std::string& key, const std::string& def = "") const {
    auto it = params_.find(key);
    return (it != params_.end()) ? it->second : def;
  }

private:
  std::map<std::string, std::string> params_;
};

}  // namespace easyfly_utils
#endif  // EASYFLY_UTILS_PARAM_LOADER_HPP_
