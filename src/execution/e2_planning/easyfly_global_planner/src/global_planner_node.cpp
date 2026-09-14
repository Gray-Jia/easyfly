// EasyFly E2: 全局规划节点 (M4.2)
//
// 数据流:
//   /occupancy_grid (OccupancyGrid, semantic_map 产出, 已含膨胀)
//   /uav_state      (起点)
//     → goal (/navigate: NavigateTo)
//     → 2D A* + 视线剪枝 (astar.hpp)
//     → 逐段 GoToWaypoint 执行 (mission_fsm 同款轮询模式)
//
// 失败语义:
//   - 目标在膨胀障碍内 / 越界 / 无可行动作: goal REJECT 或 abort (message 说明)
//   - 段执行 ABORTED 带 "takeover" (低电量 RTL 等) → 传播 abort 让位
//   - 用户 cancel → 取消当前段 + 悬停 + CANCELED
//   - V1 不做动态重规划 (静态世界假设, 动态避障归 M4.4 obstacle_avoidance)
#include <atomic>
#include <chrono>
#include <cmath>
#include <limits>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <ament_index_cpp/get_package_share_directory.hpp>
#include <yaml-cpp/yaml.h>

#include <nav_msgs/msg/occupancy_grid.hpp>
#include <easyfly_msgs/action/navigate_to.hpp>
#include <easyfly_msgs/action/go_to_waypoint.hpp>
#include <easyfly_msgs/msg/uav_state.hpp>

#include "easyfly_global_planner/astar.hpp"

namespace easyfly_global_planner
{

using NavigateTo = easyfly_msgs::action::NavigateTo;
using GoToWaypoint = easyfly_msgs::action::GoToWaypoint;
using GoalHandleWp = rclcpp_action::ClientGoalHandle<GoToWaypoint>;
using namespace std::chrono_literals;
using namespace std::placeholders;

class GlobalPlannerNode : public rclcpp::Node
{
public:
    explicit GlobalPlannerNode(const rclcpp::NodeOptions & options)
        : Node("easyfly_global_planner", options)
    {
        loadParams();

        auto qos = rclcpp::QoS(10);
        grid_sub_ = create_subscription<nav_msgs::msg::OccupancyGrid>(
            params_.grid_topic, qos,
            [this](nav_msgs::msg::OccupancyGrid::ConstSharedPtr msg) {
                std::lock_guard<std::mutex> lk(snap_mtx_);
                latest_grid_ = std::move(msg);
                grid_arrival_ = std::chrono::steady_clock::now();
            });
        state_sub_ = create_subscription<easyfly_msgs::msg::UAVState>(
            "/uav_state", qos,
            [this](easyfly_msgs::msg::UAVState::SharedPtr msg) {
                std::lock_guard<std::mutex> lk(snap_mtx_);
                latest_state_ = *msg;
                state_received_ = true;
            });

        cli_wp_ = rclcpp_action::create_client<GoToWaypoint>(this, "/goto_waypoint");

        as_nav_ = rclcpp_action::create_server<NavigateTo>(
            this, "/navigate",
            std::bind(&GlobalPlannerNode::handle_goal, this, _1, _2),
            std::bind(&GlobalPlannerNode::handle_cancel, this, _1),
            std::bind(&GlobalPlannerNode::handle_accepted, this, _1));

        RCLCPP_INFO(get_logger(),
                    "GlobalPlanner 启动: %s → /navigate (栅格超时 %.0fs, 段到位半径 %.2fm)",
                    params_.grid_topic.c_str(), params_.grid_stale_timeout,
                    params_.segment_acceptance);
    }

private:
    struct NodeParams {
        std::string grid_topic{"/occupancy_grid"};
        double grid_stale_timeout{5.0};   // 栅格数据过期判定 [s]
        double segment_acceptance{0.5};   // 段到位半径 [m]
        double max_speed_default{2.0};
        double z_min{0.5};
        double z_max{2.5};                // SLAM 盲区约束 (Q22)
    };

    void loadParams()
    {
        declare_parameter<std::string>("config_file", "");
        std::string cfg = get_parameter("config_file").as_string();
        if (cfg.empty()) {
            cfg = ament_index_cpp::get_package_share_directory("easyfly_global_planner")
                  + "/config/navigate.yaml";
        }
        YAML::Node root = YAML::LoadFile(cfg);
        const auto & p = root["global_planner"];
        params_.grid_topic = p["grid_topic"].as<std::string>(params_.grid_topic);
        params_.grid_stale_timeout =
            p["grid_stale_timeout"].as<double>(params_.grid_stale_timeout);
        params_.segment_acceptance =
            p["segment_acceptance"].as<double>(params_.segment_acceptance);
        params_.max_speed_default =
            p["max_speed_default"].as<double>(params_.max_speed_default);
        params_.z_min = p["z_min"].as<double>(params_.z_min);
        params_.z_max = p["z_max"].as<double>(params_.z_max);
    }

    // ------------------------------------------------ 快照

    nav_msgs::msg::OccupancyGrid::ConstSharedPtr snapGrid(double & age_s)
    {
        std::lock_guard<std::mutex> lk(snap_mtx_);
        age_s = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - grid_arrival_).count();
        return latest_grid_;
    }
    easyfly_msgs::msg::UAVState snapState()
    {
        std::lock_guard<std::mutex> lk(snap_mtx_);
        return latest_state_;
    }

    // ------------------------------------------------ Action 服务端

    rclcpp_action::GoalResponse handle_goal(
        const rclcpp_action::GoalUUID &, std::shared_ptr<const NavigateTo::Goal>)
    {
        if (active_) {
            RCLCPP_WARN(get_logger(), "已有导航在执行, 拒绝新 goal");
            return rclcpp_action::GoalResponse::REJECT;
        }
        return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
    }

    rclcpp_action::CancelResponse handle_cancel(
        const std::shared_ptr<rclcpp_action::ServerGoalHandle<NavigateTo>>)
    {
        cancel_req_ = true;  // 控制线程在轮询点响应: 取消当前段 + 悬停 + CANCELED
        return rclcpp_action::CancelResponse::ACCEPT;
    }

    void handle_accepted(
        const std::shared_ptr<rclcpp_action::ServerGoalHandle<NavigateTo>> gh)
    {
        active_ = true;
        cancel_req_ = false;
        std::thread([this, gh]() {
            try {
                navigateLoop(gh);
            } catch (const std::exception & e) {
                RCLCPP_ERROR(get_logger(), "导航线程异常: %s", e.what());
                try {
                    auto res = std::make_shared<NavigateTo::Result>();
                    res->success = false;
                    res->message = std::string("internal error: ") + e.what();
                    gh->abort(res);
                } catch (...) {}
                active_ = false;
            }
        }).detach();
    }

    // ------------------------------------------------ 执行线程

    /// 轮询等待 future, 期间响应取消. 返回 0=ready, 1=timeout, 2=中断
    template <typename F>
    int pollFuture(F & fut, double timeout_s)
    {
        const auto t0 = std::chrono::steady_clock::now();
        while (true) {
            if (cancel_req_) return 2;
            if (fut.wait_for(std::chrono::milliseconds(100)) == std::future_status::ready)
                return 0;
            if (std::chrono::steady_clock::now() - t0 >
                std::chrono::duration<double>(timeout_s))
                return 1;
        }
    }

    void cancelWaypoint(std::shared_ptr<GoalHandleWp> & gh,
                        std::shared_future<rclcpp_action::Client<GoToWaypoint>::WrappedResult> & res_fut)
    {
        if (!gh) return;
        try {
            cli_wp_->async_cancel_goal(gh);
        } catch (const std::exception & e) {
            RCLCPP_WARN(get_logger(), "取消段异常: %s", e.what());
        }
        const auto t0 = std::chrono::steady_clock::now();
        while (res_fut.wait_for(100ms) != std::future_status::ready) {
            if (std::chrono::steady_clock::now() - t0 > 5s) break;
        }
        if (res_fut.wait_for(0s) == std::future_status::ready) res_fut.get();
        gh.reset();
    }

    void navigateLoop(std::shared_ptr<rclcpp_action::ServerGoalHandle<NavigateTo>> gh)
    {
        const auto goal = gh->get_goal();
        const double max_speed =
            goal->max_speed > 0 ? goal->max_speed : params_.max_speed_default;

        // ---- 栅格新鲜度 ----
        double grid_age = 0;
        const auto grid_msg = snapGrid(grid_age);
        if (!grid_msg || grid_age > params_.grid_stale_timeout) {
            auto res = std::make_shared<NavigateTo::Result>();
            res->success = false;
            res->message = "occupancy grid stale (" +
                           std::to_string(grid_age).substr(0, 4) + "s), semantic_map 未运行?";
            gh->abort(res);
            active_ = false;
            return;
        }

        // ---- 栅格 → A* 输入 ----
        OccupancyGrid2d grid;
        grid.width = static_cast<int>(grid_msg->info.width);
        grid.height = static_cast<int>(grid_msg->info.height);
        grid.resolution = grid_msg->info.resolution;
        grid.origin_x = grid_msg->info.origin.position.x;
        grid.origin_y = grid_msg->info.origin.position.y;
        grid.data = grid_msg->data;

        const auto uav = snapState();
        if (!state_received_) {
            auto res = std::make_shared<NavigateTo::Result>();
            res->success = false;
            res->message = "no /uav_state";
            gh->abort(res);
            active_ = false;
            return;
        }

        // ---- 目标高度: NaN = 当前高度, 双端钳位 ----
        const double goal_z = std::isfinite(goal->target_z)
            ? std::clamp(goal->target_z, params_.z_min, params_.z_max)
            : std::clamp(uav.position_z, params_.z_min, params_.z_max);

        // ---- 规划 ----
        const auto plan = planPath(grid, uav.position_x, uav.position_y,
                                   goal->target_x, goal->target_y);
        {
            // 诊断: 规划时刻直线上栅格的占据采样 (分流"A*没绕"vs"栅格没障碍")
            std::string diag;
            for (int i = 0; i <= 10; ++i) {
                const double t = i / 10.0;
                const double sx = uav.position_x +
                    (goal->target_x - uav.position_x) * t;
                const double sy = uav.position_y +
                    (goal->target_y - uav.position_y) * t;
                diag += std::to_string(grid.worldOccupied(sx, sy) ? 1 : 0);
            }
            RCLCPP_INFO(get_logger(),
                        "[规划诊断] 直线占据采样(起→终): %s raw/smooth=%zu/%zu",
                        diag.c_str(), plan.waypoints.size() >= 2 ? plan.waypoints.size() : 0,
                        plan.waypoints.size());
        }
        if (!plan.ok) {
            const char * msg =
                plan.fail == AStarResult::Fail::GOAL_IN_OBSTACLE ? "goal in inflated obstacle"
              : plan.fail == AStarResult::Fail::OUT_OF_BOUNDS    ? "goal out of grid bounds"
              : plan.fail == AStarResult::Fail::START_IN_OBSTACLE ? "start deeply in obstacle"
              : "no path found";
            RCLCPP_WARN(get_logger(), "规划失败: %s", msg);
            auto res = std::make_shared<NavigateTo::Result>();
            res->success = false;
            res->message = msg;
            gh->abort(res);
            active_ = false;
            return;
        }

        const size_t total_seg = plan.waypoints.size() - 1;
        RCLCPP_INFO(get_logger(), "导航规划: (%.1f,%.1f)→(%.1f,%.1f) %zu 段 (剪枝后)",
                    uav.position_x, uav.position_y, goal->target_x, goal->target_y,
                    total_seg);

        // ---- 逐段执行 (waypoints[0] ≈ 当前位置, 跳过) ----
        const auto t_total0 = std::chrono::steady_clock::now();
        for (size_t seg = 1; seg < plan.waypoints.size(); ++seg) {
            if (cancel_req_) {
                auto res = std::make_shared<NavigateTo::Result>();
                res->success = false;
                res->message = "cancelled";
                gh->canceled(res);
                active_ = false;
                return;
            }

            const double wx = plan.waypoints[seg].first;
            const double wy = plan.waypoints[seg].second;
            // 末段用目标 z; 中间段维持巡航高度
            const double wz = (seg + 1 == plan.waypoints.size()) ? goal_z
                                                                 : std::clamp(uav.position_z, params_.z_min, params_.z_max);

            GoToWaypoint::Goal seg_goal;
            seg_goal.target_x = wx;
            seg_goal.target_y = wy;
            seg_goal.target_z = wz;
            seg_goal.max_speed = max_speed;
            seg_goal.acceptance_radius = params_.segment_acceptance;

            if (!cli_wp_->wait_for_action_server(3s)) {
                auto res = std::make_shared<NavigateTo::Result>();
                res->success = false;
                res->message = "GoToWaypoint server unavailable";
                gh->abort(res);
                active_ = false;
                return;
            }
            auto goal_fut = cli_wp_->async_send_goal(seg_goal);
            if (pollFuture(goal_fut, 10.0) != 0) {
                if (goal_fut.wait_for(1s) == std::future_status::ready) {
                    if (auto early = goal_fut.get()) {
                        try { cli_wp_->async_cancel_goal(early); } catch (...) {}
                    }
                }
                auto res = std::make_shared<NavigateTo::Result>();
                res->success = false;
                res->message = "cancelled";
                gh->canceled(res);
                active_ = false;
                return;
            }
            auto wp_gh = goal_fut.get();
            if (!wp_gh) {
                auto res = std::make_shared<NavigateTo::Result>();
                res->success = false;
                res->message = "segment goal rejected (need takeoff+hover first?)";
                gh->abort(res);
                active_ = false;
                return;
            }
            auto res_fut = cli_wp_->async_get_result(wp_gh);

            // 段结果轮询
            bool seg_done = false;
            int seg_fail_code = 0;  // 0=ok, 1=takeover, 2=timeout
            while (!seg_done) {
                if (cancel_req_) {
                    try { cli_wp_->async_cancel_goal(wp_gh); } catch (...) {}
                    if (res_fut.wait_for(5s) != std::future_status::ready)
                        RCLCPP_WARN(get_logger(), "段取消等待超时");
                    else
                        res_fut.get();
                    auto res = std::make_shared<NavigateTo::Result>();
                    res->success = false;
                    res->message = "cancelled";
                    gh->canceled(res);
                    active_ = false;
                    return;
                }
                if (res_fut.wait_for(100ms) == std::future_status::ready) {
                    const auto wrapped = res_fut.get();
                    if (wrapped.code == rclcpp_action::ResultCode::ABORTED) {
                        if (wrapped.result &&
                            wrapped.result->message.find("takeover") != std::string::npos)
                            seg_fail_code = 1;
                        else
                            seg_fail_code = 2;  // 段超时就地悬停
                    }
                    seg_done = true;
                    break;
                }
                // 反馈
                try {
                    auto fb = std::make_shared<NavigateTo::Feedback>();
                    fb->current_segment = static_cast<int32_t>(seg);
                    fb->total_segments = static_cast<int32_t>(total_seg);
                    // 剩余 = 当前位置到本段终点 + 其后各段长度
                    const auto cur = snapState();
                    double remaining = std::hypot(
                        plan.waypoints[seg].first - cur.position_x,
                        plan.waypoints[seg].second - cur.position_y);
                    for (size_t k = seg + 1; k < plan.waypoints.size(); ++k) {
                        remaining += std::hypot(
                            plan.waypoints[k].first - plan.waypoints[k - 1].first,
                            plan.waypoints[k].second - plan.waypoints[k - 1].second);
                    }
                    fb->distance_remaining = remaining;
                    gh->publish_feedback(fb);
                } catch (...) {}
            }

            if (seg_fail_code == 1) {
                RCLCPP_WARN(get_logger(), "段 %zu 被外部接管中止, 导航让位", seg);
                auto res = std::make_shared<NavigateTo::Result>();
                res->success = false;
                res->message = "external takeover (RTL/AUTO.LAND)";
                gh->abort(res);
                active_ = false;
                return;
            }
            if (seg_fail_code == 2) {
                RCLCPP_WARN(get_logger(), "段 %zu 超时就地悬停, 导航中止", seg);
                auto res = std::make_shared<NavigateTo::Result>();
                res->success = false;
                res->message = "segment timeout (hovering in place)";
                gh->abort(res);
                active_ = false;
                return;
            }
            RCLCPP_INFO(get_logger(), "段 %zu/%zu 到达 (%.1f, %.1f)",
                        seg, total_seg, wx, wy);
        }

        const double total_s = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - t_total0).count();
        RCLCPP_INFO(get_logger(), "导航完成, 用时 %.0fs", total_s);
        auto res = std::make_shared<NavigateTo::Result>();
        res->success = true;
        res->message = "navigated";
        gh->succeed(res);
        active_ = false;
    }

    // ------------------------------------------------ 成员

    NodeParams params_;

    std::mutex snap_mtx_;
    nav_msgs::msg::OccupancyGrid::ConstSharedPtr latest_grid_;
    std::chrono::steady_clock::time_point grid_arrival_{std::chrono::steady_clock::now()};
    easyfly_msgs::msg::UAVState latest_state_;
    bool state_received_{false};

    std::atomic<bool> active_{false};
    std::atomic<bool> cancel_req_{false};

    rclcpp::Subscription<nav_msgs::msg::OccupancyGrid>::SharedPtr grid_sub_;
    rclcpp::Subscription<easyfly_msgs::msg::UAVState>::SharedPtr state_sub_;
    rclcpp_action::Client<GoToWaypoint>::SharedPtr cli_wp_;
    rclcpp_action::Server<NavigateTo>::SharedPtr as_nav_;
};

}  // namespace easyfly_global_planner

#include <rclcpp_components/register_node_macro.hpp>
RCLCPP_COMPONENTS_REGISTER_NODE(easyfly_global_planner::GlobalPlannerNode)
