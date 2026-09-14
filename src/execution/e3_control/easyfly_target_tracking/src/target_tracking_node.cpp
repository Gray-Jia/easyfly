// EasyFly E3: TrackTarget 跟随飞行节点 (M4.1)
//
// 数据流:
//   /target_positions (Target3DArray, odom 系, M5 输出)
//     → 目标选择 (goal.target_id, -1=最近; 跳变拒绝: 同 id 突变>2m 视为 EKF
//       毛刺丢弃, 连续 3 次采信为真实快速移动 — question.md Q34 兜底)
//     → 跟随点 = 目标位置沿"无人机→目标"反方向退 follow_distance
//     → GoToWaypoint 重发式跟随 (偏差 >1.0m 才重发, 静止零重发)
//
// 安全设计:
//   - 控制通道复用 flight_control 全部安全链 (渐近 setpoint/超时保护/接管检测);
//   - 丢失处理: first_seen_timeout 内无目标 abort; 跟随中丢失超过 lost_timeout
//     → cancel 航点 + 原地悬停 + abort (不盲飞);
//   - 接管传播: GoToWaypoint 返回 "external takeover" abort (低电量 RTL 等)
//     → TrackTarget 立即 abort, 让位给安全链;
//   - 仅悬停状态可发起 (自身不含起飞, 从地面发起会在首个航点发送时明确报错);
//   - 与任务 FSM 互斥 (flight_control 单动作槽), 不要同时使用。
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <ament_index_cpp/get_package_share_directory.hpp>
#include <yaml-cpp/yaml.h>

#include <easyfly_msgs/action/track_target.hpp>
#include <easyfly_msgs/action/go_to_waypoint.hpp>
#include <easyfly_msgs/msg/target3_d_array.hpp>
#include <easyfly_msgs/msg/uav_state.hpp>

namespace easyfly_target_tracking
{

using TrackTarget = easyfly_msgs::action::TrackTarget;
using GoToWaypoint = easyfly_msgs::action::GoToWaypoint;
using Target3D = easyfly_msgs::msg::Target3D;
using GoalHandleWp = rclcpp_action::ClientGoalHandle<GoToWaypoint>;
using namespace std::chrono_literals;
using namespace std::placeholders;

class TargetTrackingNode : public rclcpp::Node
{
public:
    explicit TargetTrackingNode(const rclcpp::NodeOptions & options)
        : Node("easyfly_target_tracking", options)
    {
        loadParams();

        auto qos = rclcpp::QoS(10);
        targets_sub_ = create_subscription<easyfly_msgs::msg::Target3DArray>(
            params_.input_topic, qos,
            [this](easyfly_msgs::msg::Target3DArray::ConstSharedPtr msg) {
                std::lock_guard<std::mutex> lk(snap_mtx_);
                latest_targets_ = *msg;
                last_arrival_ = std::chrono::steady_clock::now();  // 数据断流检测
            });
        state_sub_ = create_subscription<easyfly_msgs::msg::UAVState>(
            params_.uav_state_topic, qos,
            [this](easyfly_msgs::msg::UAVState::SharedPtr msg) {
                std::lock_guard<std::mutex> lk(snap_mtx_);
                latest_state_ = *msg;
                state_received_ = true;
            });

        cli_wp_ = rclcpp_action::create_client<GoToWaypoint>(this, "/goto_waypoint");

        as_track_ = rclcpp_action::create_server<TrackTarget>(
            this, "/track_target",
            std::bind(&TargetTrackingNode::handle_goal, this, _1, _2),
            std::bind(&TargetTrackingNode::handle_cancel, this, _1),
            std::bind(&TargetTrackingNode::handle_accepted, this, _1));

        RCLCPP_INFO(get_logger(),
                    "TargetTracking 启动: %s → /goto_waypoint (重发阈值 %.1fm, 丢失 %.1fs, "
                    "高度上限 %.1fm)",
                    params_.input_topic.c_str(), params_.reissue_threshold,
                    params_.lost_timeout, params_.max_altitude);
    }

private:
    struct NodeParams {
        std::string input_topic{"/target_positions"};
        std::string uav_state_topic{"/uav_state"};
        double reissue_threshold{1.0};
        double default_follow_distance{4.0};
        double default_follow_height{1.5};
        double max_altitude{2.5};
        double jump_reject_dist{2.0};
        int jump_accept_streak{3};
        double first_seen_timeout{15.0};
        double lost_timeout{5.0};
        double reacquire_radius{2.5};
    };

    void loadParams()
    {
        declare_parameter<std::string>("config_file", "");
        std::string cfg = get_parameter("config_file").as_string();
        if (cfg.empty()) {
            cfg = ament_index_cpp::get_package_share_directory("easyfly_target_tracking")
                  + "/config/follow.yaml";
        }
        YAML::Node root = YAML::LoadFile(cfg);
        const auto & p = root["target_tracking"];
        params_.input_topic = p["input_topic"].as<std::string>(params_.input_topic);
        params_.uav_state_topic = p["uav_state_topic"].as<std::string>(params_.uav_state_topic);
        params_.reissue_threshold = p["reissue_threshold"].as<double>(params_.reissue_threshold);
        params_.default_follow_distance =
            p["default_follow_distance"].as<double>(params_.default_follow_distance);
        params_.default_follow_height =
            p["default_follow_height"].as<double>(params_.default_follow_height);
        params_.max_altitude = p["max_altitude"].as<double>(params_.max_altitude);
        params_.jump_reject_dist = p["jump_reject_dist"].as<double>(params_.jump_reject_dist);
        params_.jump_accept_streak = p["jump_accept_streak"].as<int>(params_.jump_accept_streak);
        params_.first_seen_timeout = p["first_seen_timeout"].as<double>(params_.first_seen_timeout);
        params_.lost_timeout = p["lost_timeout"].as<double>(params_.lost_timeout);
        params_.reacquire_radius = p["reacquire_radius"].as<double>(params_.reacquire_radius);
    }

    // ------------------------------------------------ 快照

    easyfly_msgs::msg::Target3DArray snapTargets()
    {
        std::lock_guard<std::mutex> lk(snap_mtx_);
        return latest_targets_;
    }
    /// /target_positions 数据断流时长 [s] (感知节点死亡 → 到达时刻不再更新)
    double arrivalAgeSec()
    {
        std::lock_guard<std::mutex> lk(snap_mtx_);
        return std::chrono::duration<double>(
            std::chrono::steady_clock::now() - last_arrival_).count();
    }

    easyfly_msgs::msg::UAVState snapState()
    {
        std::lock_guard<std::mutex> lk(snap_mtx_);
        return latest_state_;
    }

    // ------------------------------------------------ Action 服务端

    rclcpp_action::GoalResponse handle_goal(
        const rclcpp_action::GoalUUID &, std::shared_ptr<const TrackTarget::Goal> goal)
    {
        if (goal->target_id == -2) {  // 停止跟踪: 总是接受 (作为对活跃跟随的停止信号)
            return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
        }
        if (active_) {
            RCLCPP_WARN(get_logger(), "已有跟随在执行, 拒绝新 goal (先发 target_id=-2 停止)");
            return rclcpp_action::GoalResponse::REJECT;
        }
        if (goal->target_id < -2) {
            return rclcpp_action::GoalResponse::REJECT;
        }
        return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
    }

    rclcpp_action::CancelResponse handle_cancel(
        const std::shared_ptr<rclcpp_action::ServerGoalHandle<TrackTarget>>)
    {
        cancel_req_ = true;  // 控制线程在轮询点响应: cancel 航点 + 悬停 + canceled
        return rclcpp_action::CancelResponse::ACCEPT;
    }

    void handle_accepted(const std::shared_ptr<rclcpp_action::ServerGoalHandle<TrackTarget>> gh)
    {
        if (gh->get_goal()->target_id == -2) {  // 停止信号
            stop_req_ = true;
            cancel_req_ = true;
            try {
                auto res = std::make_shared<TrackTarget::Result>();
                res->success = true;
                res->message = "tracking stopped";
                gh->succeed(res);
            } catch (...) {}
            RCLCPP_INFO(get_logger(), "收到停止跟踪信号");
            return;
        }

        active_ = true;
        cancel_req_ = false;
        stop_req_ = false;
        takeover_since_ = rclcpp::Time(0, 0, get_clock()->get_clock_type());  // 跨跟随残留清零
        // mission_fsm 同款: detached 线程 + 顶层 try/catch (未捕获异常会杀死进程)
        std::thread([this, gh]() {
            try {
                followLoop(gh);
            } catch (const std::exception & e) {
                RCLCPP_ERROR(get_logger(), "跟随线程异常: %s", e.what());
                try {
                    auto res = std::make_shared<TrackTarget::Result>();
                    res->success = false;
                    res->message = std::string("internal error: ") + e.what();
                    gh->abort(res);
                } catch (...) {}
                active_ = false;
            }
        }).detach();
    }

    // ------------------------------------------------ 跟随控制线程

    /// 目标查找: id 精确匹配 (target_id<0 时取距无人机最近的 valid 目标)
    /// 返回 false = 本帧无有效观测
    bool findTarget(const easyfly_msgs::msg::Target3DArray & arr, int target_id,
                    const easyfly_msgs::msg::UAVState & uav, Target3D & out)
    {
        const bool nearest = target_id < 0;
        double best = 1e18;
        bool found = false;
        for (const auto & t : arr.targets) {
            if (!t.position_valid) continue;
            if (!nearest && t.track_id != target_id) continue;
            if (nearest) {
                const double dx = t.position_x - uav.position_x;
                const double dy = t.position_y - uav.position_y;
                const double d = dx * dx + dy * dy;
                if (d >= best) continue;
                best = d;
            }
            out = t;
            found = true;
            if (!nearest) break;
        }
        return found;
    }

    /// 半径内最近目标 (重捕获用)
    bool findNearestTo(double x, double y, double radius,
                       const easyfly_msgs::msg::Target3DArray & arr,
                       const easyfly_msgs::msg::UAVState &,
                       Target3D & out)
    {
        double best = radius * radius;
        bool found = false;
        for (const auto & t : arr.targets) {
            if (!t.position_valid) continue;
            const double dx = t.position_x - x;
            const double dy = t.position_y - y;
            const double d = dx * dx + dy * dy;
            if (d < best) {
                best = d;
                out = t;
                found = true;
            }
        }
        return found;
    }

    /// 跳变拒绝 (Q34 兜底): 同 id 相邻有效位置突变视为毛刺; 连续多次突变
    /// 视为真实快速移动放行。仅跟随线程调用, 无需加锁。
    bool jumpGuard(int id, const Target3D & t)
    {
        auto it = last_accepted_.find(id);
        if (it == last_accepted_.end()) {
            last_accepted_[id] = {t.position_x, t.position_y, t.position_z};
            streak_[id] = 0;
            return true;
        }
        const double dx = t.position_x - it->second[0];
        const double dy = t.position_y - it->second[1];
        const double dz = t.position_z - it->second[2];
        if (std::sqrt(dx * dx + dy * dy + dz * dz) > params_.jump_reject_dist) {
            if (++streak_[id] >= params_.jump_accept_streak) {  // 连续突变 → 真实移动
                last_accepted_[id] = {t.position_x, t.position_y, t.position_z};
                streak_[id] = 0;
                return true;
            }
            return false;
        }
        last_accepted_[id] = {t.position_x, t.position_y, t.position_z};
        streak_[id] = 0;
        return true;
    }

    /// 轮询等待 future, 期间响应取消/停止. 返回 0=ready, 1=timeout, 2=中断
    template <typename F>
    int pollFuture(F & fut, double timeout_s)
    {
        const auto t0 = std::chrono::steady_clock::now();
        while (true) {
            if (cancel_req_ || stop_req_) return 2;
            if (fut.wait_for(std::chrono::milliseconds(100)) == std::future_status::ready)
                return 0;
            if (std::chrono::steady_clock::now() - t0 >
                std::chrono::duration<double>(timeout_s))
                return 1;
        }
    }

    /// 发送一个航点 (阻塞至被接受). 成功后由调用方挂 result future.
    bool issueWaypoint(double x, double y, double z, double max_speed,
                       std::shared_ptr<GoalHandleWp> & gh,
                       std::shared_future<typename GoalHandleWp::SharedPtr> & goal_fut)
    {
        GoToWaypoint::Goal g;
        g.target_x = x;
        g.target_y = y;
        g.target_z = z;
        g.max_speed = max_speed;
        g.acceptance_radius = 0.5;
        if (!cli_wp_->wait_for_action_server(3s)) {
            RCLCPP_ERROR(get_logger(), "GoToWaypoint action server 不可用");
            return false;
        }
        goal_fut = cli_wp_->async_send_goal(g);
        const int pst = pollFuture(goal_fut, 10.0);
        if (pst != 0) {
            // 中断 (取消/停止) 或超时: goal 可能已被接受, 补取消防孤儿航点
            if (goal_fut.wait_for(1s) == std::future_status::ready) {
                if (auto early_gh = goal_fut.get()) {
                    try { cli_wp_->async_cancel_goal(early_gh); } catch (...) {}
                }
            }
            return false;
        }
        gh = goal_fut.get();
        if (!gh) {
            RCLCPP_ERROR(get_logger(),
                         "GoToWaypoint 被拒 (flight_control 不在 HOVER? 需先起飞悬停)");
            return false;
        }
        return true;
    }

    /// 取消当前航点并等待其终态 (CANCELED/SUCCEEDED/ABORTED 都代表
    /// flight_control 已回 HOVER, 可接受新 goal)
    void cancelWaypoint(std::shared_ptr<GoalHandleWp> & gh,
                        std::shared_future<rclcpp_action::Client<GoToWaypoint>::WrappedResult> & res_fut,
                        bool & wp_has)
    {
        if (!wp_has || !gh) return;
        try {
            cli_wp_->async_cancel_goal(gh);
        } catch (const std::exception & e) {
            RCLCPP_WARN(get_logger(), "取消航点异常: %s", e.what());
        }
        const auto t0 = std::chrono::steady_clock::now();
        while (res_fut.wait_for(std::chrono::milliseconds(100)) != std::future_status::ready) {
            if (std::chrono::steady_clock::now() - t0 > 5s) {
                RCLCPP_WARN(get_logger(), "等待航点终态超时 (5s), 继续重发");
                break;
            }
        }
        if (res_fut.wait_for(0s) == std::future_status::ready) {
            res_fut.get();  // 消费掉, 避免下一轮误判
        }
        gh.reset();
        wp_has = false;
    }

    void followLoop(std::shared_ptr<rclcpp_action::ServerGoalHandle<TrackTarget>> gh)
    {
        const auto goal = gh->get_goal();
        const int target_id = goal->target_id;
        const double follow_distance =
            goal->follow_distance > 0 ? goal->follow_distance : params_.default_follow_distance;
        const double follow_height_req =
            goal->follow_height > 0 ? goal->follow_height : params_.default_follow_height;

        RCLCPP_INFO(get_logger(), "跟随发起: id=%d 距离=%.1fm 高度=%.1fm",
                    target_id, follow_distance, follow_height_req);
        int cur_tid_ = target_id;

        // ---- 等待首次捕获 ----
        Target3D tgt;
        {
            const auto t0 = std::chrono::steady_clock::now();
            bool found = false;
            while (std::chrono::steady_clock::now() - t0 <
                   std::chrono::duration<double>(params_.first_seen_timeout))
            {
                if (cancel_req_ || stop_req_) break;
                const auto arr = snapTargets();
                const auto uav = snapState();
                if (findTarget(arr, target_id, uav, tgt) && jumpGuard(tgt.track_id, tgt)) {
                    found = true;
                    break;
                }
                std::this_thread::sleep_for(100ms);
            }
            if (cancel_req_ || stop_req_) {
                auto res = std::make_shared<TrackTarget::Result>();
                res->success = false;
                res->message = "cancelled before target acquired";
                gh->canceled(res);
                active_ = false;
                return;
            }
            if (!found) {
                auto res = std::make_shared<TrackTarget::Result>();
                res->success = false;
                res->message = "target not found (" +
                               std::to_string(params_.first_seen_timeout) + "s)";
                gh->abort(res);
                active_ = false;
                return;
            }
        }
        auto last_seen = std::chrono::steady_clock::now();

        // ---- 跟随主循环 ----
        std::shared_ptr<GoalHandleWp> wp_gh_;
        std::shared_future<typename GoalHandleWp::SharedPtr> wp_goal_fut_;
        std::shared_future<rclcpp_action::Client<GoToWaypoint>::WrappedResult> wp_res_fut_;
        bool wp_has_ = false;
        bool takeover_ = false;
        double cur_wp_x_ = 0, cur_wp_y_ = 0;
        bool first_issue_ = true;

        while (true) {
            if (cancel_req_ || stop_req_ || takeover_) {
                cancelWaypoint(wp_gh_, wp_res_fut_, wp_has_);
                auto res = std::make_shared<TrackTarget::Result>();
                res->success = false;
                res->message = stop_req_ ? "stopped"
                             : (takeover_ ? "external takeover (RTL/AUTO.LAND)" : "cancelled");
                // 终态语义: 用户主动取消=CANCELED, 接管/异常=ABORTED, 停止指令=SUCCEEDED
                if (stop_req_) gh->succeed(res);
                else if (cancel_req_) gh->canceled(res);
                else gh->abort(res);
                break;
            }

            const auto arr = snapTargets();
            const auto uav = snapState();
            Target3D t;
            const bool seen = findTarget(arr, cur_tid_, uav, t) && jumpGuard(cur_tid_, t);
            if (seen) last_seen = std::chrono::steady_clock::now();

            // ---- id 轮换重捕获 ----
            // SORT 在视角/检出变化时会重新分配 id (Q19: 飞行中 ~26 个/次),
            // 锁定单一 id 在实战中脆弱。丢失判定前先在"最后已知位置"附近
            // (reacquire_radius) 认领新 id —— 等价于操作员视觉重锁。
            if (!seen && last_accepted_.count(cur_tid_)) {
                const auto arr2 = snapTargets();
                const auto uav2 = snapState();
                Target3D cand;
                if (findNearestTo(last_accepted_[cur_tid_][0], last_accepted_[cur_tid_][1],
                                  params_.reacquire_radius, arr2, uav2, cand) &&
                    jumpGuard(cand.track_id, cand))
                {
                    RCLCPP_WARN(get_logger(), "id 轮换重捕获: %d → %d (@ %.2f,%.2f)",
                                cur_tid_, cand.track_id, cand.position_x, cand.position_y);
                    last_accepted_.erase(cur_tid_);   // 旧 id 状态清理 (防 map 无界增长)
                    streak_.erase(cur_tid_);
                    cur_tid_ = cand.track_id;
                    t = cand;
                    last_seen = std::chrono::steady_clock::now();
                }
            }

            // ---- 丢失处理: cancel 航点 + 悬停 + abort ----
            // 两路信号: (a) /target_positions 断流 (快照是缓存的最后一帧,
            // 不按到达时刻判定的话, 感知节点死亡后 seen 永远为 true — 实测);
            // (b) 跟随 id 长时间无有效观测 (数据在流但目标消失)
            const double stale_s = arrivalAgeSec();
            const double lost_s = std::chrono::duration<double>(
                std::chrono::steady_clock::now() - last_seen).count();
            if (stale_s > params_.lost_timeout || lost_s > params_.lost_timeout) {
                RCLCPP_WARN(get_logger(), "目标丢失超过 %.0fs, 悬停并终止跟随",
                            params_.lost_timeout);
                cancelWaypoint(wp_gh_, wp_res_fut_, wp_has_);
                auto res = std::make_shared<TrackTarget::Result>();
                res->success = false;
                res->message = "target lost";
                gh->abort(res);
                break;
            }

            // ---- 外部接管检测: PX4 被切 RTL/AUTO.LAND (低电量/地面站) ----
            // 直接读 flight_mode (比等航点 abort 消息更快更可靠: 丢失判定
            // 5s 可能先触发)。持续 2s 去抖 (模式反馈链有 ~1s 延迟)。
            {
                const int mode = uav.flight_mode;
                if (mode == 6 || mode == 7) {
                    if (takeover_since_.nanoseconds() == 0) {
                        takeover_since_ = now();
                    } else if ((now() - takeover_since_).seconds() > 2.0) {
                        RCLCPP_WARN(get_logger(),
                                    "检测到外部接管 (mode=%d), 跟随让位", mode);
                        takeover_ = true;
                        continue;
                    }
                } else {
                    takeover_since_ = rclcpp::Time(0, 0, now().get_clock_type());
                }
            }

            // ---- 航点结果检查: 接管传播 / 终态清位 ----
            if (wp_has_ && wp_res_fut_.valid() &&
                wp_res_fut_.wait_for(0s) == std::future_status::ready)
            {
                const auto wrapped = wp_res_fut_.get();
                wp_has_ = false;
                if (wrapped.code == rclcpp_action::ResultCode::ABORTED &&
                    wrapped.result && wrapped.result->message.find("takeover") !=
                                          std::string::npos)
                {
                    RCLCPP_WARN(get_logger(), "航点被外部接管中止 (%s), 跟随让位",
                                wrapped.result->message.c_str());
                    takeover_ = true;
                    continue;
                }
                // SUCCEEDED (到达跟随点) / CANCELED / ABORTED(超时就地悬停):
                // 均回到 HOVER, 等下一帧目标位置触发重发
            }

            // ---- 跟随点计算与航点重发 ----
            if (seen) {
                double dx = t.position_x - uav.position_x;
                double dy = t.position_y - uav.position_y;
                const double d = std::sqrt(dx * dx + dy * dy);
                double fx = cur_wp_x_, fy = cur_wp_y_;
                if (d > 0.3) {  // 无人机→目标 水平反方向退 follow_distance
                    fx = t.position_x - dx / d * follow_distance;
                    fy = t.position_y - dy / d * follow_distance;
                }
                // 高度双端 clamp: 深度毛刺可给出异常 target_z (实测 -1.4 → 跟随点
                // 落地), 下限防砸地, 上限为 SLAM 盲区约束
                const double fz = std::clamp(
                    t.position_z + follow_height_req, 0.8, params_.max_altitude);

                // 重发条件 = 跟随点相对"上次下发点"移动超阈值 (水平)。
                // 注意不含 !wp_has_: 航点完成后 flight_control 已在跟随点悬停,
                // 若无条件重发会形成 300ms 一次的 0.0Xm 微航点风暴 (实测)。
                const bool need =
                    first_issue_ ||
                    std::sqrt(std::pow(fx - cur_wp_x_, 2) + std::pow(fy - cur_wp_y_, 2)) >
                        params_.reissue_threshold;
                if (need) {
                    if (wp_has_) cancelWaypoint(wp_gh_, wp_res_fut_, wp_has_);
                    if (cancel_req_ || stop_req_ || takeover_) continue;
                    // 首个航点礼貌重试: flight_control 从 "上个动作结束" 到 HOVER
                    // 存在时序窗口 (如跟随紧接起飞发起), REJECT 不是错误而是"未就绪"
                    bool issued = false;
                    for (int attempt = 0; attempt < 10 && !issued; ++attempt) {
                        if (issueWaypoint(fx, fy, fz, 2.5, wp_gh_, wp_goal_fut_)) {
                            issued = true;
                            break;
                        }
                        if (cancel_req_ || stop_req_) break;
                        RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 3000,
                                             "航点未就绪 (等 HOVER), 重试 %d/10", attempt + 1);
                        std::this_thread::sleep_for(1s);
                    }
                    if (issued) {
                        wp_res_fut_ = cli_wp_->async_get_result(wp_gh_);
                        cur_wp_x_ = fx;
                        cur_wp_y_ = fy;
                        wp_has_ = true;
                        first_issue_ = false;
                        RCLCPP_INFO(get_logger(), "跟随点 → (%.2f, %.2f, %.2f)", fx, fy, fz);
                    } else {
                        if (cancel_req_ || stop_req_) continue;
                        auto res = std::make_shared<TrackTarget::Result>();
                        res->success = false;
                        res->message = "waypoint rejected (need takeoff+hover first?)";
                        gh->abort(res);
                        break;
                    }
                }
            }

            // ---- 反馈 ----
            try {
                auto fb = std::make_shared<TrackTarget::Feedback>();
                fb->current_target_id = cur_tid_;
                fb->target_visible = seen;
                fb->distance_to_target = seen
                    ? std::sqrt(std::pow(t.position_x - uav.position_x, 2) +
                                std::pow(t.position_y - uav.position_y, 2))
                    : 0.0;
                gh->publish_feedback(fb);
            } catch (...) {}

            std::this_thread::sleep_for(100ms);
        }
        active_ = false;
        RCLCPP_INFO(get_logger(), "跟随结束");
    }

    // ------------------------------------------------ 成员

    NodeParams params_;

    std::mutex snap_mtx_;
    std::chrono::steady_clock::time_point last_arrival_{std::chrono::steady_clock::now()};
    easyfly_msgs::msg::Target3DArray latest_targets_;
    easyfly_msgs::msg::UAVState latest_state_;
    bool state_received_{false};

    rclcpp::Time takeover_since_{0, 0, RCL_ROS_TIME};  // 接管检测去抖 (跟随线程私有)
    std::map<int, std::array<double, 3>> last_accepted_;  // 跳变拒绝 (跟随线程私有)
    std::map<int, int> streak_;

    std::atomic<bool> active_{false};
    std::atomic<bool> cancel_req_{false};
    std::atomic<bool> stop_req_{false};

    rclcpp::Subscription<easyfly_msgs::msg::Target3DArray>::SharedPtr targets_sub_;
    rclcpp::Subscription<easyfly_msgs::msg::UAVState>::SharedPtr state_sub_;
    rclcpp_action::Client<GoToWaypoint>::SharedPtr cli_wp_;
    rclcpp_action::Server<TrackTarget>::SharedPtr as_track_;
};

}  // namespace easyfly_target_tracking

#include <rclcpp_components/register_node_macro.hpp>
RCLCPP_COMPONENTS_REGISTER_NODE(easyfly_target_tracking::TargetTrackingNode)
