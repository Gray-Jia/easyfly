// Copyright 2026 EasyFly Project
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#pragma once
#include <cmath>
#include <opencv2/imgproc.hpp>
#include <opencv2/tracking.hpp>
namespace ef_single
{
inline bool roi(double x, double y, double w, double h)
{
  return std::isfinite(x) && std::isfinite(y) && std::isfinite(w) && std::isfinite(h) && x >= 0 &&
         y >= 0 && w > 0 && h > 0 && x + w <= 1 && y + h <= 1;
}
inline cv::Rect pixels(double x, double y, double w, double h, int width, int height)
{
  return {static_cast<int>(std::floor(x * width)), static_cast<int>(std::floor(y * height)),
    static_cast<int>(std::floor(w * width)),
    static_cast<int>(std::floor(h * height))};
}
}  // namespace ef_single
