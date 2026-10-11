// Copyright 2026 EasyFly Project
// Licensed under the Apache License, Version 2.0.
// You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
// Distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

#include <gtest/gtest.h>
#include <sdf/sdf.hh>
#include <gazebo_ros/node.hpp>
#include <rclcpp/rclcpp.hpp>

#include <memory>

#include "easyfly_gazebo_plugins/safe_camera.hpp"

namespace
{
class ExposedCamera : public gazebo_plugins::EasyFlyGazeboRosCamera
{
public:
  using gazebo_plugins::EasyFlyGazeboRosCamera::Load;
  using gazebo_plugins::EasyFlyGazeboRosCamera::GetRosNode;
};

TEST(CameraDuplicate, RejectsNullRosNodeBeforeAccessingSensorOrQos)
{
  rclcpp::init(0, nullptr);
  auto sdf = std::make_shared<sdf::SDF>();
  sdf::init(sdf);
  ASSERT_TRUE(
    sdf::readString(
      "<sdf version='1.6'><model name='fixture'><plugin name='camera_guard' "
      "filename='unused.so'><ros><namespace>/duplicate_test</namespace></ros>"
      "</plugin></model></sdf>", sdf));
  auto plugin = sdf->Root()->GetElement("model")->GetElement("plugin");
  auto original = gazebo_ros::Node::Get(plugin);
  ASSERT_NE(original, nullptr);
  {
    ExposedCamera camera;
    // An invalid sensor must never be inspected after duplicate Node::Get fails.
    camera.Load(nullptr, plugin);
    EXPECT_EQ(camera.GetRosNode(), nullptr);
    EXPECT_EQ(original->get_fully_qualified_name(), std::string("/duplicate_test/camera_guard"));
  }
  original.reset();
  // Registry removal on teardown must allow a later independent owner.
  auto replacement = gazebo_ros::Node::Get(plugin);
  EXPECT_NE(replacement, nullptr);
  replacement.reset();
  rclcpp::shutdown();
}
}  // namespace
