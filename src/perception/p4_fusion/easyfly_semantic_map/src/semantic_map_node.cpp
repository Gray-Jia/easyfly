// EasyFly P4: 障碍表征节点 (semantic_map, M4.0)
//
// 数据流:
//   /pointcloud_filtered (PointCloud2, base_link 系, 来自 easyfly_pointcloud_filter)
//     → TF 变换到 world 系 (odom) → 滑动窗口累积
//     → 地面剔除: RANSAC 拟合水平主平面 (SACMODEL_PERPENDICULAR_PLANE,
//       免疫 EKF 高度抖动/机体沉降 — 写死裁剪带已实测失效, 地面漏点会
//       把聚类链成跨场景巨簇)
//     → PCL 欧式聚类 → 每簇轴对齐包围盒
//     → /obstacles        (easyfly_msgs/ObstacleInfoArray, world 系)
//     → /get_obstacles    (srv: 按距机体水平距离查询)
//     → /occupancy_grid   (nav_msgs/OccupancyGrid, 2D 投影 + 膨胀, 供全局规划)
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
#include <array>
#include <cmath>
#include <deque>
#include <algorithm>
#include <mutex>
#include <memory>
#include <string>
#include <vector>

#include <std_msgs/msg/header.hpp>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_components/register_node_macro.hpp>
#include <ament_index_cpp/get_package_share_directory.hpp>
#include <yaml-cpp/yaml.h>

#include <sensor_msgs/msg/point_cloud2.hpp>
#include <nav_msgs/msg/occupancy_grid.hpp>
#include <visualization_msgs/msg/marker_array.hpp>
#include <easyfly_msgs/msg/obstacle_info_array.hpp>
#include <easyfly_msgs/srv/get_obstacles.hpp>
#include <tf2_ros/buffer.h>
#include <tf2_ros/transform_listener.h>
#include <tf2_eigen/tf2_eigen.hpp>
#include <Eigen/Geometry>

#include <pcl/point_cloud.h>
#include <pcl/point_types.h>
#include <pcl/conversions.h>
#include <pcl_conversions/pcl_conversions.h>
#include <pcl/common/transforms.h>
#include <pcl/segmentation/extract_clusters.h>
#include <pcl/segmentation/sac_segmentation.h>
#include <pcl/filters/extract_indices.h>
#include <pcl/search/kdtree.h>

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

        tf_buffer_ = std::make_unique<tf2_ros::Buffer>(get_clock());
        tf_listener_ = std::make_unique<tf2_ros::TransformListener>(*tf_buffer_);

        obstacles_pub_ = create_publisher<ObstacleInfoArray>(params_.output_topic, 10);
        grid_pub_ = create_publisher<nav_msgs::msg::OccupancyGrid>(params_.grid_topic, 10);
        marker_pub_ = create_publisher<visualization_msgs::msg::MarkerArray>(
            params_.marker_topic, 10);

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
        std::string output_topic{"/obstacles"};
        std::string grid_topic{"/occupancy_grid"};
        std::string marker_topic{"/obstacle_markers"};
        std::string service_name{"/get_obstacles"};
        std::string world_frame{"odom"};
        double plane_distance_threshold{0.12};  // 地面平面厚度 [m] (RANSAC 内点距离)
        double obstacle_z_max{4.0};        // 关心高度上限 [m, 离拟合地面]
        double cluster_tolerance{0.4};   // 欧式聚类容差 [m]
        int cluster_min_points{5};
        int cluster_max_points{100000};
        int accumulate_frames{5};        // 滑动窗口帧数 (远目标增密; 1=纯单帧)
        double max_obstacle_size{8.0};   // 单簇包围盒上界 [m] (超过视为噪声链/地面残留)
        double inflate_radius{0.3};      // 栅格膨胀半径 [m]
        bool verbose{false};             // 逐帧统计日志 (调参用)
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
        params_.output_topic = p["output_topic"].as<std::string>(params_.output_topic);
        params_.grid_topic = p["grid_topic"].as<std::string>(params_.grid_topic);
        params_.marker_topic = p["marker_topic"].as<std::string>(params_.marker_topic);
        params_.service_name = p["service_name"].as<std::string>(params_.service_name);
        params_.world_frame = p["world_frame"].as<std::string>(params_.world_frame);
        params_.plane_distance_threshold =
            p["plane_distance_threshold"].as<double>(params_.plane_distance_threshold);
        params_.obstacle_z_max = p["obstacle_z_max"].as<double>(params_.obstacle_z_max);
        params_.cluster_tolerance = p["cluster_tolerance"].as<double>(params_.cluster_tolerance);
        params_.cluster_min_points = p["cluster_min_points"].as<int>(params_.cluster_min_points);
        params_.cluster_max_points = p["cluster_max_points"].as<int>(params_.cluster_max_points);
        params_.accumulate_frames = p["accumulate_frames"].as<int>(params_.accumulate_frames);
        params_.max_obstacle_size = p["max_obstacle_size"].as<double>(params_.max_obstacle_size);
        params_.inflate_radius = p["inflate_radius"].as<double>(params_.inflate_radius);
        params_.verbose = p["verbose"].as<bool>(params_.verbose);
        params_.grid_resolution = p["grid_resolution"].as<double>(params_.grid_resolution);
        params_.grid_width = p["grid_width"].as<double>(params_.grid_width);
        params_.grid_height = p["grid_height"].as<double>(params_.grid_height);
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
                RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 5000,
                                     "TF %s←%s 不可用: %s", target.c_str(), source.c_str(), e2.what());
                return false;
            }
        }
    }

    void onCloud(const sensor_msgs::msg::PointCloud2::ConstSharedPtr & msg)
    {
        if (msg->width == 0) return;

        // → PCL (base_link) → world 系 → 逐帧地面剔除 → 累积
        // 地面剔除必须在"单帧内"做: 累积窗口里 mavros EKF 姿态噪声 (~0.5°)
        // 经 25m 杠杆把平面涂抹成 ±0.3m 厚带, 整体 RANSAC 拟不干净;
        // 单帧内姿态一致, 倾斜的地面仍是完美平面, 每帧独立拟合即可干净移除。
        pcl::PointCloud<pcl::PointXYZI>::Ptr cloud(new pcl::PointCloud<pcl::PointXYZI>);
        pcl::fromROSMsg(*msg, *cloud);

        Eigen::Isometry3d T;
        if (!lookupTf(params_.world_frame, msg->header.frame_id,
                      rclcpp::Time(msg->header.stamp), T)) {
            return;
        }
        // TF 跳变守卫: mavros local_position 存在启动毛刺 (实测首帧 (0.98,-2.52),
        // 与 M6 z=-10 尖峰同族) — 毛刺帧会把整个场景平移复制进累积窗口, 产出
        // 幻影簇。帧间平移 >1m 物理上不可能 (7Hz 下 2m/s 飞行 Δ0.3m), 丢帧。
        const Eigen::Vector3d tt = T.translation();
        if (!tf_init_) {
            // 基线须连续 3 帧稳定才建立 (毛刺值若被当作基线, 之后所有正常帧
            // 都会被误判跳变 → 永久丢帧); 稳定前不产出
            if (!pend_init_ || (tt - pend_t_).norm() > 0.5) {
                pend_t_ = tt;
                pend_cnt_ = 1;
                pend_init_ = true;
            } else if (++pend_cnt_ >= 3) {
                last_tf_t_ = tt;
                tf_init_ = true;
            }
            return;
        }
        if ((tt - last_tf_t_).norm() > 1.0) {
            // EKF 启动期是"持续错误后收敛"而非孤立尖峰: 固定基线会永久卡死,
            // 连续拒绝 10 帧 (≈1.4s) 视为真值永久移动, 重置基线
            if (++rej_cnt_ >= 10) {
                RCLCPP_WARN(get_logger(), "TF 位置持续漂移, 基线重置为 (%.2f,%.2f)",
                            tt.x(), tt.y());
                last_tf_t_ = tt;
                rej_cnt_ = 0;
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
        if (cloud->size() < 100) return;  // 平面拟合最少点数

        // ---- 本帧地面: RANSAC 拟合水平主平面 (地面点占比 ~80%, 必为主平面) ----
        pcl::ModelCoefficients::Ptr coeff(new pcl::ModelCoefficients);
        pcl::PointIndices::Ptr ground_inliers(new pcl::PointIndices);
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
        if (ground_inliers->indices.empty()) {
            RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 5000, "地面平面未拟合到");
            return;
        }
        const float ground_z = -coeff->values[3] / coeff->values[2];  // 水平面 z

        // 非地面点 (剔除平面内点) + 高度带过滤
        pcl::ExtractIndices<pcl::PointXYZI> extract;
        extract.setInputCloud(cloud);
        extract.setIndices(ground_inliers);
        extract.setNegative(true);
        pcl::PointCloud<pcl::PointXYZI>::Ptr above(new pcl::PointCloud<pcl::PointXYZI>);
        extract.filter(*above);
        const float z_max = ground_z + static_cast<float>(params_.obstacle_z_max);
        pcl::PointCloud<pcl::PointXYZI>::Ptr obs(new pcl::PointCloud<pcl::PointXYZI>);
        obs->reserve(above->size());
        for (const auto & p : above->points) {
            if (p.z > ground_z + 0.05f && p.z < z_max) obs->push_back(p);
        }
        if (obs->size() < static_cast<size_t>(params_.cluster_min_points)) return;

        if (params_.verbose) {
            RCLCPP_INFO_THROTTLE(get_logger(), *get_clock(), 3000,
                                 "TF world←%s: (%.2f,%.2f,%.2f) ground_plane_z=%.2f 点数 %zu→%zu→%zu",
                                 msg->header.frame_id.c_str(),
                                 T.translation().x(), T.translation().y(), T.translation().z(),
                                 ground_z, cloud->size(), above->size(), obs->size());
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
        }
        obstacles_pub_->publish(arr);
        publishGrid(arr.header, boxes);
        publishMarkers(arr.header, boxes);
    }

    // ---- 2D 占据栅格: 簇足迹 (膨胀后) 标记为占据 ----
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
        grid.data.assign(grid.info.width * grid.info.height, 0);

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
        ObstacleInfoArray latest;
        {
            std::lock_guard<std::mutex> lk(latest_mtx_);
            latest = latest_;
        }

        double drone_x = 0.0, drone_y = 0.0;
        if (req->range_limit > 0.0f) {
            Eigen::Isometry3d T;
            if (lookupTf(params_.world_frame, "base_link", this->now(), T)) {
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
    std::unique_ptr<tf2_ros::Buffer> tf_buffer_;
    std::unique_ptr<tf2_ros::TransformListener> tf_listener_;

    std::mutex latest_mtx_;
    ObstacleInfoArray latest_;

    rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr sub_;
    rclcpp::Publisher<ObstacleInfoArray>::SharedPtr obstacles_pub_;
    rclcpp::Publisher<nav_msgs::msg::OccupancyGrid>::SharedPtr grid_pub_;
    rclcpp::Publisher<visualization_msgs::msg::MarkerArray>::SharedPtr marker_pub_;
    rclcpp::Service<easyfly_msgs::srv::GetObstacles>::SharedPtr srv_;
    rclcpp::CallbackGroup::SharedPtr srv_group_;
};

}  // namespace easyfly_semantic_map

RCLCPP_COMPONENTS_REGISTER_NODE(easyfly_semantic_map::SemanticMapNode)
