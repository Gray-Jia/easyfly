// Copyright 2026 EasyFly Project
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
// http://www.apache.org/licenses/LICENSE-2.0
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#include <iostream>
#include <opencv2/imgcodecs.hpp>
#include "tag_core.hpp"

int main(int argc, char ** argv)
{
  if (argc != 7) {return 2;}
  const double size = std::stod(argv[3]), error = std::stod(argv[4]), margin = std::stod(argv[5]);
  auto parameters = std::string(argv[6]) == "production" ? ef_tag::detector_parameters() :
    cv::aruco::DetectorParameters::create();
  auto image = cv::imread(argv[1], cv::IMREAD_COLOR);
  if (image.empty()) {return 3;}
  cv::cvtColor(image, image, cv::COLOR_BGR2GRAY);
  std::vector<int> ids;
  std::vector<std::vector<cv::Point2f>> corners;
  cv::aruco::detectMarkers(
    image, cv::aruco::getPredefinedDictionary(
      cv::aruco::DICT_APRILTAG_36h11), corners, ids, parameters);
  cv::FileStorage calibration(argv[2], cv::FileStorage::READ);
  std::vector<double> values, distortion;
  calibration["K"] >> values;
  calibration["D"] >> distortion;
  if (values.size() != 9) {return 4;}
  cv::Mat K = cv::Mat(3, 3, CV_64F, values.data()).clone();
  cv::Mat D(distortion, true);
  cv::FileStorage out("",
    cv::FileStorage::WRITE | cv::FileStorage::MEMORY | cv::FileStorage::FORMAT_JSON);
  out << "ids" << ids << "corner_refinement" << parameters->cornerRefinementMethod << "tags" << "[";
  for (size_t i = 0; i < ids.size(); ++i) {
    if (ids[i] != 7) {continue;}
    auto pose = ef_tag::estimate(corners[i], K, D, size, error, margin);
    out << "{" << "id" << ids[i] << "valid" << static_cast<int>(pose.valid) << "reason" <<
      pose.reason << "error" << pose.error;
    if (pose.valid) {
      out << "selected_translation" << "[" << pose.t[0] << pose.t[1] << pose.t[2] << "]";
      out << "selected_quaternion" << "[" << pose.q[0] << pose.q[1] << pose.q[2] << pose.q[3] <<
        "]";
    }
    out << "corners" << "[";
    for (auto p : corners[i]) {
      out << "[" << p.x << p.y << "]";
    }
    out << "]" << "candidates" << "[";
    std::vector<cv::Point3f> object{{static_cast<float>(-size / 2), static_cast<float>(size / 2),
      0},
      {static_cast<float>(size / 2), static_cast<float>(size / 2), 0},
      {static_cast<float>(size / 2), static_cast<float>(-size / 2), 0},
      {static_cast<float>(-size / 2), static_cast<float>(-size / 2), 0}};
    std::vector<cv::Mat> rotations, translations;
    cv::solvePnPGeneric(
      object, corners[i], K, D, rotations, translations, false,
      cv::SOLVEPNP_IPPE_SQUARE);
    for (size_t j = 0; j < rotations.size(); ++j) {
      if (!cv::checkRange(rotations[j]) || !cv::checkRange(translations[j])) {continue;}
      cv::Mat R;
      cv::Rodrigues(rotations[j], R);
      std::vector<cv::Point2f> projected;
      cv::projectPoints(object, rotations[j], translations[j], K, D, projected);
      double squared = 0;
      for (size_t k = 0; k < 4; ++k) {
        squared += std::pow(cv::norm(projected[k] - corners[i][k]), 2);
      }
      auto q = ef_tag::quaternion(R);
      out << "{" << "index" << static_cast<int>(j) << "rms_px" << std::sqrt(squared / 4) <<
        "translation" << "[";
      for (int k = 0; k < 3; ++k) {
        out << translations[j].at<double>(k);
      }
      out << "]" << "quaternion" << "[";
      for (int k = 0; k < 4; ++k) {
        out << q[k];
      }
      out << "]" << "corner_depths" << "[";
      for (auto p : object) {
        out << R.at<double>(2, 0) * p.x + R.at<double>(2, 1) * p.y + translations[j].at<double>(2);
      }
      out << "]" << "optical_plane_tilt_rad" <<
        std::acos(std::min(1., std::abs(R.at<double>(2, 2)))) << "}";
    }
    out << "]" << "}";
  }
  out << "]";
  std::cout << out.releaseAndGetString() << std::endl;
}
