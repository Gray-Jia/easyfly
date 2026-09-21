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
//
// EasyFly P4: 障碍表征节点 (semantic_map, M4.0)
//
// 数据流:
//   /pointcloud_filtered (PointCloud2, base_link 系, 来自 easyfly_pointcloud_filter)
//     → TF 变换到 world 系 (odom) → 滑动窗口累积
//     → 地面候选: RANSAC 拟合水平主平面 + 可信平面跟踪 (SACMODEL_PERPENDICULAR_PLANE,
//       通过时间一致性、车辆相对高度与平滑更新拒绝退化平面; 写死世界高度裁剪带
//       已实测失效, 地面漏点会把聚类链成跨场景巨簇)
//     → PCL 欧式聚类 → 每簇轴对齐包围盒
//     → /obstacles        (easyfly_msgs/ObstacleInfoArray, world 系)
//     → /get_obstacles    (srv: 按距机体水平距离查询)
//     → /occupancy_grid   (nav_msgs/OccupancyGrid, 2D 投影 + 膨胀 + 持久化
//       衰减 — 聚类逐帧闪烁会使规划器拿到缺障碍的稀疏帧, 实测近乎撞人;
//       占据格保留 ~6 帧才释放, 规划/EGO 消费稳定)
//     → /obstacle_markers (RViz 立方体可视化)
//
// M4.0 边界: obstacle_id 为帧内索引 (跨帧稳定 ID 需要障碍跟踪, 待消费方
// 出现需求后做); is_dynamic 恒 false, velocity 恒 0; type 恒 "unknown"
// (语义类别由检测融合补充, 阶段四不做)。
//
// 时间累积: MID-360 非重复扫描单帧 2 万点铺满 360°, 远目标 (20m 行人) 单帧
// 仅 ~6 点, 无法成簇 — 滑动窗口合并最近 K 帧世界系点云 (各自经 TF 运动补偿)
// 后聚类, 远目标点数 ×K。无人机移动时窗口内新旧帧位置差表现为目标拖尾,
// 由消费方 (全局规划) 的膨胀半径吸收; 跟踪类精细需求应订阅帧内结果。
#include <yaml-cpp/yaml.h>
#include <tf2_ros/buffer.h>
#include <tf2_ros/transform_listener.h>
#include <Eigen/Geometry>
#include <pcl/point_cloud.h>
#include <pcl/point_types.h>
#include <pcl/conversions.h>
#include <pcl_conversions/pcl_conversions.h>
#include <pcl/common/transforms.h>
#include <pcl/segmentation/extract_clusters.h>
#include <pcl/segmentation/sac_segmentation.h>
#include <pcl/search/kdtree.h>

#include <array>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <deque>
#include <limits>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include <std_msgs/msg/header.hpp>

#include <tf2_eigen/tf2_eigen.hpp>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_components/register_node_macro.hpp>
#include <ament_index_cpp/get_package_share_directory.hpp>

#include <sensor_msgs/msg/point_cloud2.hpp>
#include <nav_msgs/msg/occupancy_grid.hpp>
#include <visualization_msgs/msg/marker_array.hpp>
#include <easyfly_msgs/msg/obstacle_info_array.hpp>
#include <easyfly_msgs/msg/uav_state.hpp>
#include <easyfly_msgs/srv/get_obstacles.hpp>

#include "easyfly_semantic_map/ground_plane_tracker.hpp"
#include "easyfly_semantic_map/grid_inflation.hpp"
#include "easyfly_semantic_map/map_validity.hpp"

namespace easyfly_semantic_map
{

using easyfly_msgs::msg::ObstacleInfo;
using easyfly_msgs::msg::ObstacleInfoArray;

class SemanticMapNode : public rclcpp::Node
{
public:
    explicit SemanticMapNode(const rclcpp::NodeOptions & options)
        : Node("easyfly_semantic_map", options)
    {
        loadParams();

        GroundPlaneTracker::Params ground_params;
        ground_params.max_tilt_rad = params_.plane_max_tilt_rad;
        ground_params.min_inliers = static_cast<std::size_t>(
            std::max(1, params_.plane_min_inliers));
        ground_params.min_inlier_ratio = params_.plane_min_inlier_ratio;
        ground_params.min_ground_clearance = params_.ground_min_clearance;
        ground_params.max_ground_distance_below_vehicle =
            params_.ground_max_distance_below_vehicle;
        ground_params.init_consecutive_frames = params_.ground_init_consecutive_frames;
        ground_params.init_state_timeout = params_.ground_init_state_timeout;
        ground_params.init_max_z_difference = params_.ground_init_max_z_difference;
        ground_params.init_max_normal_angle_rad = params_.ground_init_max_normal_angle_rad;
        ground_params.max_innovation_z = params_.ground_max_innovation_z;
        ground_params.max_innovation_angle_rad = params_.ground_max_innovation_angle_rad;
        ground_params.smoothing_alpha = params_.ground_smoothing_alpha;
        ground_tracker_ = GroundPlaneTracker(ground_params);

        tf_buffer_ = std::make_unique<tf2_ros::Buffer>(get_clock());
        tf_listener_ = std::make_unique<tf2_ros::TransformListener>(*tf_buffer_);

        // Keep the last map state for late subscribers.  This is important
        // during reset: a planner that discovers the publisher after the
        // reset must receive invalid/not-ready, not an old valid map.
        const auto map_qos = rclcpp::QoS(1).reliable().transient_local();
        obstacles_pub_ = create_publisher<ObstacleInfoArray>(params_.output_topic, map_qos);
        grid_pub_ = create_publisher<nav_msgs::msg::OccupancyGrid>(params_.grid_topic, map_qos);
        marker_pub_ = create_publisher<visualization_msgs::msg::MarkerArray>(
            params_.marker_topic, 10);
        state_sub_ = create_subscription<easyfly_msgs::msg::UAVState>(
            params_.uav_state_topic, 10,
            [this](easyfly_msgs::msg::UAVState::ConstSharedPtr msg) {
                std::lock_guard<std::mutex> lk(state_mtx_);
                latest_state_ = *msg;
                state_received_ = true;
                state_arrival_ = std::chrono::steady_clock::now();
            });

        invalid_map_timer_ = create_wall_timer(std::chrono::milliseconds(500), [this]() {
            bool ready = false;
            {
                std::lock_guard<std::mutex> lk(latest_mtx_);
                ready = map_ready_;
            }
            if (!ready) publishInvalidMap();
        });

        // Publish the explicit invalid/not-ready protocol immediately.  A
        // consumer that was already running must not retain a previous map
        // while this node is rebuilding after a restart.
        publishInvalidMap();

        // 服务独立回调组 (响应内做 TF 查询, 不阻塞点云回调)
        srv_group_ = create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
        srv_ = create_service<easyfly_msgs::srv::GetObstacles>(
            params_.service_name,
            std::bind(&SemanticMapNode::onGetObstacles, this,
                      std::placeholders::_1, std::placeholders::_2),
            rmw_qos_profile_services_default, srv_group_);

        sub_ = create_subscription<sensor_msgs::msg::PointCloud2>(
            params_.input_topic, 10,
            [this](sensor_msgs::msg::PointCloud2::ConstSharedPtr msg) { onCloud(msg); });

        RCLCPP_INFO(get_logger(),
                    "semantic_map 启动: %s → %s (world=%s, 聚类容差 %.2fm, min %d 点, "
                    "栅格 %.0fx%.0fm@%.2fm)",
                    params_.input_topic.c_str(), params_.output_topic.c_str(),
                    params_.world_frame.c_str(), params_.cluster_tolerance,
                    params_.cluster_min_points, params_.grid_width, params_.grid_height,
                    params_.grid_resolution);
    }

private:
    struct NodeParams {
        std::string input_topic{"/pointcloud_filtered"};
        std::string uav_state_topic{"/uav_state"};
        std::string output_topic{"/obstacles"};
        std::string grid_topic{"/occupancy_grid"};
        std::string marker_topic{"/obstacle_markers"};
        std::string service_name{"/get_obstacles"};
        std::string world_frame{"odom"};
        std::string base_frame{"base_link"};
        double plane_distance_threshold{0.12};  // 地面平面厚度 [m] (RANSAC 内点距离)
        double plane_max_tilt_rad{0.15};
        int plane_min_inliers{50};
        double plane_min_inlier_ratio{0.15};
        // Direct landed SITL traces are 0.053-0.054m; retain about 0.02m of
        // measured margin while rejecting zero/near-body-height planes.
        double ground_min_clearance{0.03};
        double ground_max_distance_below_vehicle{8.0};
        int ground_init_consecutive_frames{3};
        double ground_init_max_z_difference{0.25};
        double ground_init_max_normal_angle_rad{0.12};
        double ground_max_innovation_z{0.45};
        double ground_max_innovation_angle_rad{0.15};
        double ground_smoothing_alpha{0.25};
        double ground_init_state_timeout{1.0};
        double tf_guard_jump_distance{1.0};
        int tf_guard_init_consecutive_frames{3};
        int tf_guard_reject_limit{10};
        double obstacle_z_max{4.0};        // 关心高度上限 [m, 离拟合地面]
        double cluster_tolerance{0.4};   // 欧式聚类容差 [m]
        int cluster_min_points{5};
        int cluster_max_points{100000};
        int accumulate_frames{5};        // 滑动窗口帧数 (远目标增密; 1=纯单帧)
        double max_obstacle_size{8.0};   // 单簇包围盒上界 [m] (超过视为噪声链/地面残留)
        double inflate_radius{kDefaultGridInflationRadius};  // 栅格膨胀半径 [m]
        bool verbose{false};             // 逐帧统计日志 (调参用)
        int grid_persist_frames{20};     // 占据保持帧数 (≈3s @7Hz; 漏检不立即可穿越)
        double grid_resolution{0.2};     // 栅格分辨率 [m/cell]
        double grid_width{100.0};        // 栅格宽 [m] (以 world 原点为中心)
        double grid_height{100.0};
    };

    void loadParams()
    {
        declare_parameter<std::string>("config_file", "");
        std::string cfg = get_parameter("config_file").as_string();
        if (cfg.empty()) {
            cfg = ament_index_cpp::get_package_share_directory("easyfly_semantic_map")
                  + "/config/semantic_map.yaml";
        }
        YAML::Node root = YAML::LoadFile(cfg);
        const auto & p = root["semantic_map"];
        params_.input_topic = p["input_topic"].as<std::string>(params_.input_topic);
        params_.uav_state_topic =
            p["uav_state_topic"].as<std::string>(params_.uav_state_topic);
        params_.output_topic = p["output_topic"].as<std::string>(params_.output_topic);
        params_.grid_topic = p["grid_topic"].as<std::string>(params_.grid_topic);
        params_.marker_topic = p["marker_topic"].as<std::string>(params_.marker_topic);
        params_.service_name = p["service_name"].as<std::string>(params_.service_name);
        params_.world_frame = p["world_frame"].as<std::string>(params_.world_frame);
        params_.base_frame = p["base_frame"].as<std::string>(params_.base_frame);
        params_.plane_distance_threshold =
            p["plane_distance_threshold"].as<double>(params_.plane_distance_threshold);
        params_.plane_max_tilt_rad =
            p["plane_max_tilt_rad"].as<double>(params_.plane_max_tilt_rad);
        params_.plane_min_inliers = p["plane_min_inliers"].as<int>(params_.plane_min_inliers);
        params_.plane_min_inlier_ratio =
            p["plane_min_inlier_ratio"].as<double>(params_.plane_min_inlier_ratio);
        params_.ground_min_clearance =
            p["ground_min_clearance"].as<double>(params_.ground_min_clearance);
        params_.ground_max_distance_below_vehicle =
            p["ground_max_distance_below_vehicle"].as<double>(
            params_.ground_max_distance_below_vehicle);
        params_.ground_init_consecutive_frames =
            p["ground_init_consecutive_frames"].as<int>(params_.ground_init_consecutive_frames);
        params_.ground_init_max_z_difference =
            p["ground_init_max_z_difference"].as<double>(params_.ground_init_max_z_difference);
        params_.ground_init_max_normal_angle_rad =
            p["ground_init_max_normal_angle_rad"].as<double>(
            params_.ground_init_max_normal_angle_rad);
        params_.ground_max_innovation_z =
            p["ground_max_innovation_z"].as<double>(params_.ground_max_innovation_z);
        params_.ground_max_innovation_angle_rad =
            p["ground_max_innovation_angle_rad"].as<double>(
            params_.ground_max_innovation_angle_rad);
        params_.ground_smoothing_alpha =
            p["ground_smoothing_alpha"].as<double>(params_.ground_smoothing_alpha);
        params_.ground_init_state_timeout =
            p["ground_init_state_timeout"].as<double>(params_.ground_init_state_timeout);
        params_.tf_guard_jump_distance =
            p["tf_guard_jump_distance"].as<double>(params_.tf_guard_jump_distance);
        params_.tf_guard_init_consecutive_frames =
            p["tf_guard_init_consecutive_frames"].as<int>(params_.tf_guard_init_consecutive_frames);
        params_.tf_guard_reject_limit =
            p["tf_guard_reject_limit"].as<int>(params_.tf_guard_reject_limit);
        params_.obstacle_z_max = p["obstacle_z_max"].as<double>(params_.obstacle_z_max);
        params_.cluster_tolerance = p["cluster_tolerance"].as<double>(params_.cluster_tolerance);
        params_.cluster_min_points = p["cluster_min_points"].as<int>(params_.cluster_min_points);
        params_.cluster_max_points = p["cluster_max_points"].as<int>(params_.cluster_max_points);
        params_.accumulate_frames = p["accumulate_frames"].as<int>(params_.accumulate_frames);
        params_.max_obstacle_size = p["max_obstacle_size"].as<double>(params_.max_obstacle_size);
        params_.inflate_radius = p["inflate_radius"].as<double>(params_.inflate_radius);
        params_.grid_persist_frames =
            p["grid_persist_frames"].as<int>(params_.grid_persist_frames);
        params_.verbose = p["verbose"].as<bool>(params_.verbose);
        params_.grid_resolution = p["grid_resolution"].as<double>(params_.grid_resolution);
        params_.grid_width = p["grid_width"].as<double>(params_.grid_width);
        params_.grid_height = p["grid_height"].as<double>(params_.grid_height);
        const double configured_inflate_radius = params_.inflate_radius;
        params_.inflate_radius = normalizeGridInflationRadius(configured_inflate_radius);
        if (!std::isfinite(configured_inflate_radius) || configured_inflate_radius < 0.0) {
            RCLCPP_WARN(
                get_logger(),
                "inflate_radius=%.3f 无效，使用安全默认值 %.2fm",
                configured_inflate_radius, params_.inflate_radius);
        } else if (configured_inflate_radius < kMinimumGridInflationRadius) {
            RCLCPP_WARN(
                get_logger(),
                "inflate_radius=%.3f 低于安全下限 %.2fm，提升到下限",
                configured_inflate_radius, kMinimumGridInflationRadius);
        }
    }

    /// 与 pixel_to_3d 同款双路容错 TF 查询
    bool lookupTf(const std::string & target, const std::string & source,
                  const rclcpp::Time & stamp, Eigen::Isometry3d & out)
    {
        try {
            auto tf = tf_buffer_->lookupTransform(target, source, stamp,
                                                  rclcpp::Duration::from_seconds(0.05));
            out = tf2::transformToEigen(tf);
            return true;
        } catch (const tf2::TransformException &) {
            try {
                auto tf = tf_buffer_->lookupTransform(target, source, tf2::TimePointZero);
                out = tf2::transformToEigen(tf);
                return true;
            } catch (const tf2::TransformException & e2) {
                RCLCPP_WARN_THROTTLE(
                    get_logger(), *get_clock(), 5000,
                    "TF %s←%s 不可用: %s", target.c_str(), source.c_str(), e2.what());
                return false;
            }
        }
    }

    GroundVehiclePose groundVehiclePose(
        const double x, const double y, const double z)
    {
        GroundVehiclePose pose;
        pose.x = x;
        pose.y = y;
        pose.z = z;
        std::lock_guard<std::mutex> lk(state_mtx_);
        if (!state_received_) return pose;
        pose.connected = latest_state_.connected;
        pose.pose_valid = latest_state_.pose_valid;
        pose.armed = latest_state_.armed;
        pose.state_age_s = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - state_arrival_).count();
        return pose;
    }

    void publishInvalidMap()
    {
        {
            std::lock_guard<std::mutex> lk(latest_mtx_);
            latest_ = makeInvalidObstacles(params_.world_frame);
            map_ready_ = false;
        }
        obstacles_pub_->publish(makeInvalidObstacles(params_.world_frame));
        grid_pub_->publish(makeInvalidGrid(
            params_.grid_width, params_.grid_height, params_.grid_resolution,
            params_.world_frame));

        visualization_msgs::msg::MarkerArray markers;
        visualization_msgs::msg::Marker clear;
        clear.header.frame_id = params_.world_frame;
        clear.ns = "obstacles";
        clear.action = visualization_msgs::msg::Marker::DELETEALL;
        markers.markers.push_back(clear);
        marker_pub_->publish(markers);
    }

    void invalidateMap()
    {
        acc_buf_.clear();
        grid_persist_.clear();
        grid_miss_.clear();
        publishInvalidMap();
    }

    void onCloud(const sensor_msgs::msg::PointCloud2::ConstSharedPtr & msg)
    {
        if (msg->width == 0) return;

        // → PCL (input frame) → world 系 → 可信地面平面分类 → 累积
        // 地面候选仍逐帧由 RANSAC 提取，累积窗口只接收可信平面分类后的点。
        pcl::PointCloud<pcl::PointXYZI>::Ptr cloud(new pcl::PointCloud<pcl::PointXYZI>);
        pcl::fromROSMsg(*msg, *cloud);

        const rclcpp::Time stamp(msg->header.stamp);
        Eigen::Isometry3d T;
        if (!lookupTf(params_.world_frame, msg->header.frame_id, stamp, T)) {
            return;
        }
        // The filtered cloud is normally already in odom, so T can be the
        // identity.  The vehicle pose is still needed independently: it is
        // the physical reference for the TF jump guard and for rejecting a
        // RANSAC plane which has moved up to the aircraft height.
        Eigen::Isometry3d vehicle_T;
        if (!lookupTf(params_.world_frame, params_.base_frame, stamp, vehicle_T)) {
            return;
        }
        // TF 跳变守卫: mavros local_position 存在启动毛刺 (实测首帧 (0.98,-2.52),
        // 与 M6 z=-10 尖峰同族) — 毛刺帧会把整个场景平移复制进累积窗口, 产出
        // 幻影簇。水平帧间平移 >1m 物理上不可能 (7Hz 下 2m/s 飞行 Δ0.3m), 丢帧。
        // z 轴不参与此守卫: 起飞/降落本身就是合法的大尺度 z 运动。
        const Eigen::Vector3d tt = vehicle_T.translation();
        const auto horizontalDistance = [](const Eigen::Vector3d & first,
                                           const Eigen::Vector3d & second) {
            return std::hypot(first.x() - second.x(), first.y() - second.y());
        };
        if (!tf_init_) {
            // 基线须连续 3 帧稳定才建立 (毛刺值若被当作基线, 之后所有正常帧
            // 都会被误判跳变 → 永久丢帧); 稳定前不产出
            if (!pend_init_ || horizontalDistance(tt, pend_t_) >
                params_.tf_guard_jump_distance / 2.0) {
                pend_t_ = tt;
                pend_cnt_ = 1;
                pend_init_ = true;
            } else if (++pend_cnt_ >= params_.tf_guard_init_consecutive_frames) {
                last_tf_t_ = tt;
                tf_init_ = true;
            }
            return;
        }
        if (horizontalDistance(tt, last_tf_t_) > params_.tf_guard_jump_distance) {
            // EKF 启动期是"持续错误后收敛"而非孤立尖峰: 固定基线会永久卡死,
            // 连续拒绝 10 帧 (≈1.4s) 视为真值永久移动, 重置基线
            if (++rej_cnt_ >= params_.tf_guard_reject_limit) {
                RCLCPP_WARN(get_logger(), "TF 位置持续漂移, 基线重置为 (%.2f,%.2f)",
                            tt.x(), tt.y());
                last_tf_t_ = tt;
                rej_cnt_ = 0;
                ground_tracker_.reset();
                invalidateMap();
            } else {
                RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 3000,
                                     "TF 位置跳变 (%.2f,%.2f→%.2f,%.2f), 丢帧",
                                     last_tf_t_.x(), last_tf_t_.y(), tt.x(), tt.y());
            }
            return;
        }
        rej_cnt_ = 0;
        last_tf_t_ = tt;
        pcl::transformPointCloud(*cloud, *cloud, T.matrix());
        // A trusted model can still classify a sparse frame.  Only an
        // uninitialized tracker requires enough points to fit a new candidate.
        if (cloud->size() < 100 && !ground_tracker_.initialized()) return;

        GroundPlaneUpdate plane_update = GroundPlaneUpdate::kRejected;
        double candidate_ground_z = std::numeric_limits<double>::quiet_NaN();
        pcl::ModelCoefficients::Ptr coeff(new pcl::ModelCoefficients);
        pcl::PointIndices::Ptr ground_inliers(new pcl::PointIndices);
        const GroundVehiclePose vehicle_pose = groundVehiclePose(
            vehicle_T.translation().x(), vehicle_T.translation().y(),
            vehicle_T.translation().z());
        if (cloud->size() >= 100) {
            // ---- 本帧地面候选: RANSAC 只提供候选, 不能直接决定剔除 ----
            pcl::SACSegmentation<pcl::PointXYZI> seg;
            seg.setOptimizeCoefficients(true);
            seg.setModelType(pcl::SACMODEL_PERPENDICULAR_PLANE);
            seg.setMethodType(pcl::SAC_RANSAC);
            seg.setAxis(Eigen::Vector3f(0.0f, 0.0f, 1.0f));
            seg.setEpsAngle(0.1);  // ±6° 内视为水平 (EKF 姿态噪声量级, 平面本身随帧倾斜)
            seg.setDistanceThreshold(params_.plane_distance_threshold);
            seg.setMaxIterations(200);
            seg.setInputCloud(cloud);
            seg.segment(*ground_inliers, *coeff);

            if (!ground_inliers->indices.empty() && coeff->values.size() >= 4) {
                GroundPlaneCandidate candidate;
                const double coeff_norm = std::sqrt(
                    static_cast<double>(coeff->values[0]) * coeff->values[0] +
                    static_cast<double>(coeff->values[1]) * coeff->values[1] +
                    static_cast<double>(coeff->values[2]) * coeff->values[2]);
                if (std::isfinite(coeff_norm) && coeff_norm >= 1e-9) {
                    candidate.model.normal = {
                        static_cast<double>(coeff->values[0]) / coeff_norm,
                        static_cast<double>(coeff->values[1]) / coeff_norm,
                        static_cast<double>(coeff->values[2]) / coeff_norm};
                    candidate.model.offset = static_cast<double>(coeff->values[3]) / coeff_norm;
                    if (candidate.model.normal[2] < 0.0) {
                        for (double & component : candidate.model.normal) component = -component;
                        candidate.model.offset = -candidate.model.offset;
                    }
                    candidate.inlier_count = ground_inliers->indices.size();
                    candidate.sample_count = cloud->size();
                    candidate_ground_z = candidate.model.zAt(vehicle_pose.x, vehicle_pose.y);
                    plane_update = ground_tracker_.update(candidate, vehicle_pose);
                }
            }
        }
        if (!ground_tracker_.initialized()) {
            if (std::isfinite(candidate_ground_z) && std::isfinite(vehicle_pose.z)) {
                const double candidate_clearance = vehicle_pose.z - candidate_ground_z;
                RCLCPP_WARN_THROTTLE(
                    get_logger(), *get_clock(), 5000,
                    "可信地面平面尚未初始化, 候选净空 %.3fm (要求 >= %.3fm), 丢弃当前帧",
                    candidate_clearance, params_.ground_min_clearance);
            } else {
                RCLCPP_WARN_THROTTLE(
                    get_logger(), *get_clock(), 5000,
                    "可信地面平面尚未初始化, 候选净空不可用, 丢弃当前帧");
            }
            return;
        }
        if (ground_inliers->indices.empty() || coeff->values.size() < 4) {
            RCLCPP_WARN_THROTTLE(
                get_logger(), *get_clock(), 5000,
                "当前帧未得到有效地面候选, 使用历史可信平面分类");
        }
        if (plane_update == GroundPlaneUpdate::kRejected &&
            std::isfinite(candidate_ground_z)) {
            RCLCPP_WARN_THROTTLE(
                get_logger(), *get_clock(), 5000,
                "地面候选偏离可信模型, 使用历史平面分类当前帧 (候选 z=%.2f, 当前 z=%.2f)",
                candidate_ground_z,
                ground_tracker_.model().zAt(vehicle_pose.x, vehicle_pose.y));
        }

        // Classify against the trusted model, never against the rejected
        // candidate's inlier indices.  This is what prevents a sparse plane
        // at the aircraft height from deleting all low obstacles.
        pcl::PointCloud<pcl::PointXYZI>::Ptr obs(
            new pcl::PointCloud<pcl::PointXYZI>);
        obs->reserve(cloud->size());
        std::size_t above_count = 0;
        for (const auto & p : cloud->points) {
            const double ground_z = ground_tracker_.model().zAt(p.x, p.y);
            const double height = static_cast<double>(p.z) - ground_z;
            if (!ground_tracker_.isGroundPoint(p.x, p.y, p.z,
                                               params_.plane_distance_threshold)) {
                ++above_count;
                if (height > 0.05 && height < params_.obstacle_z_max) {
                    obs->push_back(p);
                }
            }
        }
        if (obs->size() < static_cast<size_t>(params_.cluster_min_points)) return;

        if (params_.verbose) {
            RCLCPP_INFO_THROTTLE(
                get_logger(), *get_clock(), 3000,
                "TF world←%s: (%.2f,%.2f,%.2f) "
                "ground_plane_z=%.2f 点数 %zu→%zu→%zu",
                msg->header.frame_id.c_str(),
                T.translation().x(), T.translation().y(), T.translation().z(),
                ground_tracker_.model().zAt(vehicle_pose.x, vehicle_pose.y),
                cloud->size(), above_count, obs->size());
        }

        // 滑动窗口累积 (world 系, 各帧已经各自地面剔除)
        acc_buf_.push_back(obs);
        while (static_cast<int>(acc_buf_.size()) > std::max(1, params_.accumulate_frames))
            acc_buf_.pop_front();
        // 窗口未填满不发布: 半满数据上早期帧的瞬态 (插件启动首帧异常/平面拟合
        // 不稳) 会产出无物体区域的幻影簇
        if (static_cast<int>(acc_buf_.size()) < std::max(1, params_.accumulate_frames)) return;
        pcl::PointCloud<pcl::PointXYZI>::Ptr merged(new pcl::PointCloud<pcl::PointXYZI>);
        for (const auto & c : acc_buf_) *merged += *c;

        // 欧式聚类 (累积点云)
        std::vector<pcl::PointIndices> clusters;
        pcl::search::KdTree<pcl::PointXYZI>::Ptr tree(new pcl::search::KdTree<pcl::PointXYZI>);
        tree->setInputCloud(merged);
        pcl::EuclideanClusterExtraction<pcl::PointXYZI> ec;
        ec.setClusterTolerance(params_.cluster_tolerance);
        ec.setMinClusterSize(params_.cluster_min_points);
        ec.setMaxClusterSize(params_.cluster_max_points);
        ec.setSearchMethod(tree);
        ec.setInputCloud(merged);
        ec.extract(clusters);

        if (params_.verbose) {
            std::string stat = "merged=" + std::to_string(merged->size()) + " 簇:";
            for (const auto & c : clusters) {
                float x1 = 1e9f, x2 = -1e9f, z1 = 1e9f, z2 = -1e9f;
                for (const auto & idx : c.indices) {
                    const auto & p = merged->points[idx];
                    x1 = std::min(x1, p.x); x2 = std::max(x2, p.x);
                    z1 = std::min(z1, p.z); z2 = std::max(z2, p.z);
                }
                stat += " [" + std::to_string(c.indices.size()) + "pt x" +
                        std::to_string(x2 - x1).substr(0, 4) + " z" +
                        std::to_string(z1).substr(0, 5) + "~" +
                        std::to_string(z2).substr(0, 5) + "]";
            }
            RCLCPP_INFO(get_logger(), "%s", stat.c_str());
        }

        // 簇 → ObstacleInfo (轴对齐包围盒)
        ObstacleInfoArray arr;
        arr.header.stamp = msg->header.stamp;
        if (zeroStamp(arr.header.stamp)) {
            // A zero-stamped cloud cannot establish freshness for consumers;
            // keep the map explicitly invalid instead of inventing a local
            // timestamp and allowing stale coordinates into planning.
            RCLCPP_WARN_THROTTLE(
                get_logger(), *get_clock(), 5000,
                "点云时间戳无效，保持 semantic_map not-ready");
            invalidateMap();
            return;
        }
        arr.header.frame_id = params_.world_frame;
        std::vector<std::array<double, 6>> boxes;  // x1,y1,z1,x2,y2,z2 (栅格/markers 共用)
        boxes.reserve(clusters.size());
        for (const auto & c : clusters) {
            float x1 = 1e9f, y1 = 1e9f, z1 = 1e9f, x2 = -1e9f, y2 = -1e9f, z2 = -1e9f;
            for (const auto & idx : c.indices) {
                const auto & p = merged->points[idx];
                x1 = std::min(x1, p.x); y1 = std::min(y1, p.y); z1 = std::min(z1, p.z);
                x2 = std::max(x2, p.x); y2 = std::max(y2, p.y); z2 = std::max(z2, p.z);
            }
            const double sx = x2 - x1, sy = y2 - y1, sz = z2 - z1;
            if (std::max({sx, sy, sz}) > params_.max_obstacle_size) continue;  // 噪声链
            if (sz < 0.05) continue;                                           // 碎片

            ObstacleInfo o;
            o.header = arr.header;
            o.obstacle_id = static_cast<int32_t>(arr.obstacles.size());
            o.obstacle_type = "unknown";
            o.center_x = (x1 + x2) / 2.0;
            o.center_y = (y1 + y2) / 2.0;
            o.center_z = (z1 + z2) / 2.0;
            o.size_x = sx; o.size_y = sy; o.size_z = sz;
            o.is_dynamic = false;
            arr.obstacles.push_back(o);
            boxes.push_back({x1, y1, z1, x2, y2, z2});
        }

        {
            std::lock_guard<std::mutex> lk(latest_mtx_);
            latest_ = arr;
            map_ready_ = true;
        }
        obstacles_pub_->publish(arr);
        publishGrid(arr.header, boxes);
        publishMarkers(arr.header, boxes);
    }

    // ---- 2D 占据栅格: 簇足迹 (膨胀后) 标记为占据 + 持久化衰减 ----
    // 本帧有簇 → 该格 100; 本帧无簇 → 每帧衰减 20 (≈1s 后归零)。
    // 聚类逐帧闪烁 (8↔25 簇波动), 直接发布单帧会让规划器偶尔拿到缺障碍
    // 的栅格 (实测 A* 直线穿过 person, 最近 0.14m)。
    void publishGrid(const std_msgs::msg::Header & header,
                     const std::vector<std::array<double, 6>> & boxes)
    {
        nav_msgs::msg::OccupancyGrid grid;
        grid.header = header;
        grid.info.resolution = params_.grid_resolution;
        grid.info.width = static_cast<uint32_t>(params_.grid_width / params_.grid_resolution);
        grid.info.height = static_cast<uint32_t>(params_.grid_height / params_.grid_resolution);
        grid.info.origin.position.x = -params_.grid_width / 2.0;
        grid.info.origin.position.y = -params_.grid_height / 2.0;
        grid.info.origin.orientation.w = 1.0;
        const size_t n = static_cast<size_t>(grid.info.width) * grid.info.height;
        grid.data.assign(n, 0);

        const double inf = params_.inflate_radius;
        for (const auto & b : boxes) {
            const int c1 = std::max(0, static_cast<int>(std::floor((b[0] - inf -
                grid.info.origin.position.x) / params_.grid_resolution)));
            const int c2 = std::min(static_cast<int>(grid.info.width) - 1,
                static_cast<int>(std::floor((b[3] + inf -
                grid.info.origin.position.x) / params_.grid_resolution)));
            const int r1 = std::max(0, static_cast<int>(std::floor((b[1] - inf -
                grid.info.origin.position.y) / params_.grid_resolution)));
            const int r2 = std::min(static_cast<int>(grid.info.height) - 1,
                static_cast<int>(std::floor((b[4] + inf -
                grid.info.origin.position.y) / params_.grid_resolution)));
            for (int r = r1; r <= r2; ++r)
                for (int c = c1; c <= c2; ++c)
                    grid.data[r * grid.info.width + c] = 100;
        }

        // 持久化融合 (两段式): 最近 persist_frames 帧内见过 → 100, 超时 → 0。
        // 不用数值衰减: 衰减值会在 A* 占据阈值 (>=50) 边缘抖动 — 测试目标格
        // 采样时 55(占据)、规划执行时 48(空闲), 同一障碍时有时无。
        // 历史尺寸不符则重置。
        if (grid_persist_.size() != n || grid_miss_.size() != n) {
            grid_persist_.assign(n, 0);
            grid_miss_.assign(n, 0);
        }
        for (size_t i = 0; i < n; ++i) {
            if (grid.data[i] == 100) {
                grid_persist_[i] = 100;
                grid_miss_[i] = 0;
            } else if (grid_persist_[i] > 0) {
                if (++grid_miss_[i] > static_cast<uint32_t>(
                        std::max(0, params_.grid_persist_frames))) {
                    grid_persist_[i] = 0;
                    grid_miss_[i] = 0;
                }
                grid.data[i] = grid_persist_[i];
            }
        }
        grid_pub_->publish(grid);
    }

    void publishMarkers(const std_msgs::msg::Header & header,
                        const std::vector<std::array<double, 6>> & boxes)
    {
        visualization_msgs::msg::MarkerArray ma;
        visualization_msgs::msg::Marker del;
        del.header = header;
        del.ns = "obstacles";
        del.action = visualization_msgs::msg::Marker::DELETEALL;
        ma.markers.push_back(del);

        for (size_t i = 0; i < boxes.size(); ++i) {
            const auto & b = boxes[i];
            visualization_msgs::msg::Marker m;
            m.header = header;
            m.ns = "obstacles";
            m.id = static_cast<int32_t>(i);
            m.type = visualization_msgs::msg::Marker::CUBE;
            m.pose.position.x = (b[0] + b[3]) / 2.0;
            m.pose.position.y = (b[1] + b[4]) / 2.0;
            m.pose.position.z = (b[2] + b[5]) / 2.0;
            m.pose.orientation.w = 1.0;
            m.scale.x = std::max(0.1, b[3] - b[0]);
            m.scale.y = std::max(0.1, b[4] - b[1]);
            m.scale.z = std::max(0.1, b[5] - b[2]);
            m.color.r = 1.0f; m.color.g = 0.55f; m.color.b = 0.0f; m.color.a = 0.45f;
            m.lifetime = rclcpp::Duration::from_seconds(1.5);
            ma.markers.push_back(m);
        }
        marker_pub_->publish(ma);
    }

    // ---- /get_obstacles: 按"距机体水平距离"过滤 (range_limit<=0 返回全部) ----
    void onGetObstacles(
        const std::shared_ptr<easyfly_msgs::srv::GetObstacles::Request> req,
        std::shared_ptr<easyfly_msgs::srv::GetObstacles::Response> res)
    {
        res->obstacles = ObstacleInfoArray{};
        ObstacleInfoArray latest;
        bool map_ready = false;
        // Keep the snapshot lock through response construction.  A TF reset
        // cannot clear the map between this readiness check and the reply.
        std::unique_lock<std::mutex> latest_lock(latest_mtx_);
        latest = latest_;
        map_ready = map_ready_;
        if (!map_ready ||
            (latest.header.stamp.sec == 0 && latest.header.stamp.nanosec == 0)) {
            RCLCPP_INFO_THROTTLE(
                get_logger(), *get_clock(), 5000,
                "/get_obstacles 暂无就绪地图，返回空结果");
            return;
        }

        double drone_x = 0.0, drone_y = 0.0;
        if (req->range_limit > 0.0f) {
            Eigen::Isometry3d T;
            if (lookupTf(params_.world_frame, params_.base_frame, this->now(), T)) {
                drone_x = T.translation().x();
                drone_y = T.translation().y();
            }
        }
        for (const auto & o : latest.obstacles) {
            if (req->range_limit > 0.0f) {
                const double dx = o.center_x - drone_x, dy = o.center_y - drone_y;
                if (std::sqrt(dx * dx + dy * dy) > req->range_limit) continue;
            }
            res->obstacles.obstacles.push_back(o);
        }
        res->obstacles.header = latest.header;
        res->obstacles.header.frame_id = params_.world_frame;
    }

    NodeParams params_;
    std::deque<pcl::PointCloud<pcl::PointXYZI>::Ptr> acc_buf_;  // 滑动窗口 (world 系)
    bool tf_init_{false};
    bool pend_init_{false};
    int pend_cnt_{0};
    int rej_cnt_{0};
    Eigen::Vector3d pend_t_{Eigen::Vector3d::Zero()};
    Eigen::Vector3d last_tf_t_{Eigen::Vector3d::Zero()};  // TF 跳变守卫
    GroundPlaneTracker ground_tracker_;
    std::unique_ptr<tf2_ros::Buffer> tf_buffer_;
    std::unique_ptr<tf2_ros::TransformListener> tf_listener_;

    std::mutex latest_mtx_;
    ObstacleInfoArray latest_;
    bool map_ready_{false};
    std::vector<int8_t> grid_persist_;  // 栅格持久化状态 (两段式)
    std::vector<uint32_t> grid_miss_;   // 连续未观测帧数

    std::mutex state_mtx_;
    easyfly_msgs::msg::UAVState latest_state_;
    bool state_received_{false};
    std::chrono::steady_clock::time_point state_arrival_{};

    rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr sub_;
    rclcpp::Subscription<easyfly_msgs::msg::UAVState>::SharedPtr state_sub_;
    rclcpp::TimerBase::SharedPtr invalid_map_timer_;
    rclcpp::Publisher<ObstacleInfoArray>::SharedPtr obstacles_pub_;
    rclcpp::Publisher<nav_msgs::msg::OccupancyGrid>::SharedPtr grid_pub_;
    rclcpp::Publisher<visualization_msgs::msg::MarkerArray>::SharedPtr marker_pub_;
    rclcpp::Service<easyfly_msgs::srv::GetObstacles>::SharedPtr srv_;
    rclcpp::CallbackGroup::SharedPtr srv_group_;
};

}  // namespace easyfly_semantic_map

RCLCPP_COMPONENTS_REGISTER_NODE(easyfly_semantic_map::SemanticMapNode)
