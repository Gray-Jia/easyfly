#include <algorithm>
#include <chrono>
#include <deque>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <map>
#include <memory>
#include <random>
#include <sstream>
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <cerrno>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <ament_index_cpp/get_package_share_directory.hpp>
#include <easyfly_msgs/action/execute_mission.hpp>
#include <easyfly_msgs/action/search_area.hpp>
#include <easyfly_msgs/srv/get_action_ownership.hpp>
#include <easyfly_core/ownership_registry.hpp>
#include <easyfly_msgs/srv/manage_mission.hpp>
#include <easyfly_msgs/srv/get_capabilities.hpp>
#include <easyfly_mission_fsm/mission_format.hpp>

namespace fs = std::filesystem;
using Api = easyfly_msgs::srv::ManageMission;
using Action = easyfly_msgs::action::ExecuteMission;
using Child = rclcpp_action::ClientGoalHandle<Action>;
using Clock = std::chrono::steady_clock;
using Ownership = easyfly_msgs::srv::GetActionOwnership;
class MissionServices : public rclcpp::Node {
  struct Reply {
    std::shared_ptr<rclcpp::Service<Api>> service;
    std::shared_ptr<rmw_request_id_t> header;
    Clock::time_point created{Clock::now()};
    bool sent{false};
  };
  struct Execution {
    std::string id, status{"pending"}, message, snapshot;
    bool terminal{false}, cancel_requested{false}, cancel_sent{false};
    bool result_received{false}, ownership_inflight{false};
    int64_t ownership_request{0};
    Clock::time_point ownership_sent{};
    Child::SharedPtr child;
    easyfly_msgs::msg::MissionStatus feedback;
    Clock::time_point received{};
    std::shared_ptr<Reply> admission, cancellation;
    ~Execution() {if (terminal && !snapshot.empty()) {std::error_code ec; fs::remove(snapshot, ec);}}
  };
public:
  MissionServices() : Node("easyfly_mission_srvs") {
    rcl_interfaces::msg::ParameterDescriptor readonly; readonly.read_only = true;
    // ament --symlink-install may create an installed directory containing
    // individual resource symlinks. Resolve our trusted packaged anchor once;
    // explicitly configured catalogs still reject targets outside their root.
    const auto default_directory = fs::canonical(
      ament_index_cpp::get_package_share_directory("easyfly_mission_fsm") +
      "/missions/waypoint_demo.mission").parent_path().string();
    root_ = fs::canonical(declare_parameter<std::string>("mission_directory",
      default_directory, readonly));
    if (!fs::is_directory(root_)) throw std::invalid_argument("mission_directory must be a directory");
    timeout_ = declare_parameter<double>("response_timeout", 5.0, readonly);
    freshness_ = declare_parameter<double>("feedback_max_age", 1.0, readonly);
    if (!std::isfinite(timeout_) || timeout_ < 0.05 || timeout_ > 30 ||
        !std::isfinite(freshness_) || freshness_ < 0.05 || freshness_ > 10)
      throw std::invalid_argument("invalid service timeouts");
    client_ = rclcpp_action::create_client<Action>(this, "/execute_mission");
    ownership_client_ = create_client<Ownership>("/mission/ownership");
    search_client_ = rclcpp_action::create_client<easyfly_msgs::action::SearchArea>(this, "/search_area");
    service_ = create_service<Api>("/platform/mission/manage",
      [this](std::shared_ptr<rclcpp::Service<Api>> service, std::shared_ptr<rmw_request_id_t> header,
             Api::Request::SharedPtr req) {
        auto reply = std::make_shared<Reply>(); reply->service = service; reply->header = header;
        handle(reply, *req);
      });
    capabilities_ = create_service<easyfly_msgs::srv::GetCapabilities>("/platform/mission/capabilities",
      [this](easyfly_msgs::srv::GetCapabilities::Request::SharedPtr,
             easyfly_msgs::srv::GetCapabilities::Response::SharedPtr response) {
        response->header.stamp = now(); response->header.frame_id = "odom";
        response->names = {"legacy_mission", "versioned_yaml", "search"};
        response->implemented = {true, true, true};
        const auto ready = client_->action_server_is_ready() && ownership_client_->service_is_ready() && !active_;
        response->ready = {ready, ready, ready && search_client_->action_server_is_ready()};
        response->details = {"legacy four-step format", "schema_version=1, odom m/rad/s, strict sequential seven types",
          "mission step supported; search backend/live flight admission separately required"};
      });
    timer_ = create_wall_timer(std::chrono::milliseconds(50), [this]() {tick();});
  }
private:
  static double elapsed(Clock::time_point t) {return std::chrono::duration<double>(Clock::now() - t).count();}
  static std::string identity() {
    std::random_device random; std::ostringstream out;
    for (int i = 0; i < 16; ++i) out << std::hex << std::setw(2) << std::setfill('0') << (random() & 255);
    return out.str();
  }
  void respond(const std::shared_ptr<Reply> & p, bool success, const std::string & status,
               const std::string & message, const std::shared_ptr<Execution> & e = {},
               const std::vector<std::string> & names = {}) {
    if (!p || p->sent) return;
    p->sent = true;
    Api::Response response; response.success = success; response.status = status;
    response.message = message; response.missions = names;
    if (e) {
      response.execution_id = e->id; response.current_status = e->feedback;
      response.execution_pending = !e->terminal;
      const auto & stamp = e->feedback.header.stamp;
      if (stamp.sec >= 0 && stamp.nanosec < 1000000000u && (stamp.sec || stamp.nanosec)) {
        const auto age = (now() - rclcpp::Time(stamp, get_clock()->get_clock_type())).seconds();
        response.feedback_valid = age >= -0.2 && age <= freshness_ && elapsed(e->received) <= freshness_ &&
          std::isfinite(e->feedback.progress) && e->feedback.progress >= 0 && e->feedback.progress <= 1 &&
          e->feedback.mission_phase <= easyfly_msgs::msg::MissionStatus::EMERGENCY &&
          e->feedback.current_waypoint >= -1 && e->feedback.total_waypoints >= 0;
      }
    }
    try {p->service->send_response(*p->header, response);}
    catch (const std::exception & exc) {RCLCPP_WARN(get_logger(), "mission response: %s", exc.what());}
  }
  fs::path catalogPath(const std::string & name) const {
    if (name.empty() || name.size() > 128 || fs::path(name).filename() != name || name[0] == '.')
      throw std::invalid_argument("mission_name must be a catalog basename");
    const auto named_extension = fs::path(name).extension().string();
    if (named_extension != ".mission" && named_extension != ".yaml" && named_extension != ".yml")
      throw std::invalid_argument("unsupported mission name extension");
    auto path = fs::canonical(root_ / name);
    if (path.parent_path() != root_ || !fs::is_regular_file(path) || fs::file_size(path) > 65536)
      throw std::invalid_argument("mission outside catalog or too large");
    const auto extension = path.extension().string();
    if (extension != ".mission" && extension != ".yaml" && extension != ".yml")
      throw std::invalid_argument("unsupported mission extension");
    return path;
  }
  std::string validatedText(const std::string & name) const {
    const auto path = catalogPath(name);
    const int fd = open(path.c_str(), O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) throw std::invalid_argument("cannot open regular catalog file");
    struct Guard {int fd; ~Guard() {close(fd);}} guard{fd};
    struct stat info{};
    if (fstat(fd, &info) || !S_ISREG(info.st_mode) || info.st_size > 65536)
      throw std::invalid_argument("mission must be a regular file <=64KiB");
    std::string text(65537, '\0'); size_t size=0;
    while (size < text.size()) {
      auto n = read(fd, text.data()+size, text.size()-size);
      if (n < 0 && errno == EINTR) continue;
      if (n < 0) throw std::invalid_argument("mission read failed");
      if (!n) break;
      size += static_cast<size_t>(n);
    }
    if (size > 65536) throw std::invalid_argument("mission too large");
    text.resize(size);
    const auto check = easyfly_mission_fsm::validateMissionText(text);
    if (!check.valid()) throw std::invalid_argument(check.error);
    return text;
  }
  static std::string snapshot(const std::string & text) {
    char path[] = "/tmp/easyfly-d2-mission-XXXXXX";
    int fd = mkstemp(path);
    if (fd < 0) throw std::runtime_error("cannot create private mission snapshot");
    size_t written = 0;
    while (written < text.size()) {
      const auto n = write(fd, text.data() + written, text.size() - written);
      if (n <= 0) {close(fd); unlink(path); throw std::runtime_error("snapshot write failed");}
      written += static_cast<size_t>(n);
    }
    close(fd); return path;
  }
  void handle(const std::shared_ptr<Reply> & p, const Api::Request & req) {
    try {
      if (req.operation == "list") {
        std::vector<std::string> names;
        size_t entries = 0;
        for (const auto & entry : fs::directory_iterator(root_)) {
          if (++entries > 256) throw std::invalid_argument("catalog exceeds 256 directory entries");
          try {catalogPath(entry.path().filename().string()); names.push_back(entry.path().filename().string());}
          catch (const std::exception &) {}
        }
        std::sort(names.begin(), names.end()); respond(p, true, "catalog", "schema v1 YAML and legacy flat format", {}, names);
      } else if (req.operation == "validate" || req.operation == "start") {
        const auto text = validatedText(req.mission_name);
        if (req.operation == "validate") {respond(p, true, "valid", "full static validation; live flight admission is separate"); return;}
        if (active_) {respond(p, false, "busy", "previous execution ownership unresolved", active_); return;}
        if (!client_->action_server_is_ready() || !ownership_client_->service_is_ready()) {
          respond(p, false, "unsupported", "execute_mission or ownership protocol unavailable"); return;
        }
        auto e = std::make_shared<Execution>(); e->id = identity(); e->admission = p;
        e->snapshot = snapshot(text); active_ = e; history_[e->id] = e; history_order_.push_back(e->id);
        rclcpp_action::Client<Action>::SendGoalOptions callbacks;
        callbacks.goal_response_callback = [this, e](Child::SharedPtr child) {
          e->child = child;
          if (!child) {
            e->terminal = true; e->status = "rejected"; e->message = "execution rejected by backend";
            respond(e->admission, false, e->status, e->message, e); resolve(e); return;
          }
          e->status = "running"; respond(e->admission, true, "accepted", "accepted, not completed", e);
          if (e->cancel_requested) cancel(e);
        };
        callbacks.feedback_callback = [e](Child::SharedPtr, std::shared_ptr<const Action::Feedback> feedback) {
          if (!e->terminal) {e->feedback = feedback->current_status; e->received = Clock::now();}
        };
        callbacks.result_callback = [this, e](const Child::WrappedResult & result) {
          e->result_received = true;
          e->status = result.code == rclcpp_action::ResultCode::CANCELED ? "canceled" :
            result.code == rclcpp_action::ResultCode::SUCCEEDED && result.result && result.result->success ? "succeeded" : "failed";
          e->message = result.result ? result.result->message : "missing backend result";
        };
        Action::Goal goal; goal.mission_file = e->snapshot;
        try {client_->async_send_goal(goal, callbacks);}
        catch (const std::exception & exc) {
          e->status = "fault"; e->message = exc.what(); e->cancel_requested = true;
          respond(p, false, e->status, "send failed; ownership not confirmed", e);
        }
      } else if (req.operation == "query" || req.operation == "cancel") {
        auto found = history_.find(req.execution_id);
        if (req.execution_id.empty() || found == history_.end()) {respond(p, false, "not_found", "unknown execution ID"); return;}
        auto e = found->second;
        if (req.operation == "query") {respond(p, true, e->status, e->message, e); return;}
        if (e->terminal || e != active_) {respond(p, false, e->status, "execution is already terminal", e); return;}
        if (e->cancellation && !e->cancellation->sent) {respond(p, false, "busy", "cancellation already pending", e); return;}
        e->cancellation = p; e->cancel_requested = true; cancel(e);
      } else respond(p, false, "unsupported", "unknown operation");
    } catch (const std::exception & exc) {respond(p, false, "invalid", exc.what());}
  }
  void cancel(const std::shared_ptr<Execution> & e) {
    if (e->terminal || e->result_received || !e->child || e->cancel_sent) return;
    e->cancel_sent = true; e->status = "canceling";
    try {client_->async_cancel_goal(e->child, [this, e](auto response) {
      const auto owned = e->child->get_goal_id();
      const bool accepted = response && response->return_code == 0 &&
        std::any_of(response->goals_canceling.begin(), response->goals_canceling.end(),
          [&](const auto & info) {return info.goal_id.uuid == owned;});
      respond(e->cancellation, accepted, accepted ? "cancel_requested" : "cancel_rejected",
        "cancel response does not confirm terminal", e);
      if (!accepted && !e->terminal && !e->result_received) {
        e->status = "fault"; e->cancel_sent = false; e->cancel_requested = false;
      }
    });} catch (const std::exception & exc) {
      respond(e->cancellation, false, "fault", exc.what(), e);
      if (!e->result_received) e->status = "fault";
      e->cancel_sent = false; e->cancel_requested = false;
    }
  }
  void resolve(const std::shared_ptr<Execution> & e) {
    respond(e->cancellation, e->status == "canceled", e->status, "real terminal observed", e);
    if (!e->snapshot.empty()) {std::error_code error; fs::remove(e->snapshot, error); e->snapshot.clear();}
    if (active_ == e) active_.reset();
    while (history_.size() > 32) {
      auto found = history_.find(history_order_.front());
      if (found == history_.end() || !found->second->terminal) break;
      history_.erase(found); history_order_.pop_front();
    }
  }
  void tick() {
    auto e = active_; if (!e) return;
    if (e->result_received && e->child && !e->terminal) {
      if (e->ownership_inflight && elapsed(e->ownership_sent) >= 1) {
        ownership_client_->remove_pending_request(e->ownership_request); e->ownership_inflight = false;
      }
      if (!e->ownership_inflight && elapsed(e->ownership_sent) >= .2 && ownership_client_->service_is_ready()) {
        auto request = std::make_shared<Ownership::Request>();
        request->goal_id = easyfly_core::goalIdentity(e->child->get_goal_id());
        e->ownership_inflight = true; e->ownership_sent = Clock::now();
        try {
          auto pending = ownership_client_->async_send_request(request,
            [this, e, id=request->goal_id](rclcpp::Client<Ownership>::SharedFuture future) {
            e->ownership_inflight = false;
            try {
              auto response = future.get();
              if (response && response->goal_id == id && response->state == Ownership::Response::RELEASED) {
                e->terminal = true; resolve(e);
              }
            } catch (const std::exception &) {}  // A failed query is not release evidence.
          });
          e->ownership_request = pending.request_id;
        } catch (const std::exception &) {e->ownership_inflight = false;}
      }
    }
    if (e->admission && !e->admission->sent && elapsed(e->admission->created) >= timeout_) {
      e->status = "pending_timeout"; e->cancel_requested = true;
      respond(e->admission, false, e->status, "admission timeout; retained for late exact cancellation", e);
    }
    if (e->cancellation && !e->cancellation->sent && elapsed(e->cancellation->created) >= timeout_)
      respond(e->cancellation, false, "cancel_timeout", "terminal not confirmed; execution remains owned", e);
    if (e->cancel_requested) cancel(e);
  }
  fs::path root_;
  double timeout_, freshness_;
  std::shared_ptr<Execution> active_;
  std::map<std::string, std::shared_ptr<Execution>> history_;
  std::deque<std::string> history_order_;
  rclcpp_action::Client<Action>::SharedPtr client_;
  rclcpp_action::Client<easyfly_msgs::action::SearchArea>::SharedPtr search_client_;
  rclcpp::Client<Ownership>::SharedPtr ownership_client_;
  rclcpp::Service<Api>::SharedPtr service_;
  rclcpp::Service<easyfly_msgs::srv::GetCapabilities>::SharedPtr capabilities_;
  rclcpp::TimerBase::SharedPtr timer_;
};
int main(int argc, char ** argv) {
  rclcpp::init(argc, argv);
  try {rclcpp::spin(std::make_shared<MissionServices>());}
  catch (const std::exception & e) {fprintf(stderr, "mission services: %s\n", e.what()); rclcpp::shutdown(); return 1;}
  rclcpp::shutdown(); return 0;
}
