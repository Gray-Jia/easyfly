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

#include <fstream>
#include <opencv2/aruco.hpp>
#include <opencv2/calib3d.hpp>
#include <opencv2/imgproc.hpp>
int main(int argc, char ** argv)
{
  if (argc != 2) {
    return 2;
  }
  cv::Mat marker;

  cv::aruco::drawMarker(
    cv::aruco::getPredefinedDictionary(
      cv::aruco::DICT_APRILTAG_36h11), 7, 160, marker);

  std::vector<cv::Point3f> object{{-.1, .1, 0}, {.1, .1, 0}, {.1, -.1, 0}, {-.1, -.1, 0}};

  cv::Mat K = (cv::Mat_<double>(3, 3) << 600, 0, 320, 0, 600, 240, 0, 0, 1);

  std::vector<cv::Point2f> corners;

  cv::projectPoints(object, cv::Vec3d(2.7, .2, .1), cv::Vec3d(0, 0, 1), K, cv::Mat(), corners);

  std::vector<cv::Point2f> source{{0, 0}, {159, 0}, {159, 159}, {0, 159}};

  cv::Mat image;
  cv::warpPerspective(
    marker, image, cv::getPerspectiveTransform(
      source,
      corners),
    cv::Size(640, 480), cv::INTER_NEAREST, cv::BORDER_CONSTANT, cv::Scalar(255));

  std::ofstream output(argv[1], std::ios::binary);
  output.write(
    reinterpret_cast<char *>(image.data),
    640 * 480);
  return output ? 0 : 1;
}
