#include <easyfly_core/client.hpp>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <limits>
namespace py = pybind11;
using namespace easyfly_core;
PYBIND11_MODULE(easyfly_pybind, m) {
  m.doc() = "Owned EasyFly C++ SDK; polling only, no Python callbacks from ROS threads.";
  py::enum_<Admission>(m, "Admission")
    .value("PENDING", Admission::Pending).value("ACCEPTED", Admission::Accepted)
    .value("REJECTED", Admission::Rejected).value("UNAVAILABLE", Admission::Unavailable)
    .value("UNSUPPORTED", Admission::Unsupported).value("CAPACITY_EXCEEDED", Admission::CapacityExceeded)
    .value("CLOSED", Admission::Closed);
  py::enum_<Status>(m, "Status")
    .value("PENDING", Status::Pending).value("SUCCEEDED", Status::Succeeded)
    .value("FAILED", Status::Failed).value("CANCELED", Status::Canceled)
    .value("REJECTED", Status::Rejected).value("UNAVAILABLE", Status::Unavailable)
    .value("UNSUPPORTED", Status::Unsupported).value("CAPACITY_EXCEEDED", Status::CapacityExceeded)
    .value("NOT_SENT", Status::NotSent);
  py::enum_<LocalStatus>(m, "LocalStatus")
    .value("ACTIVE", LocalStatus::Active).value("ADMISSION_TIMED_OUT", LocalStatus::AdmissionTimedOut)
    .value("CLOSED", LocalStatus::Closed).value("TRANSPORT_ERROR", LocalStatus::TransportError);
  py::enum_<CancelStatus>(m, "CancelStatus")
    .value("NONE", CancelStatus::None).value("REQUESTED", CancelStatus::Requested)
    .value("ACCEPTED", CancelStatus::Accepted).value("REJECTED", CancelStatus::Rejected)
    .value("TRANSPORT_ERROR", CancelStatus::TransportError);
  py::class_<OperationSnapshot>(m, "OperationSnapshot")
    .def_readonly("admission", &OperationSnapshot::admission)
    .def_readonly("status", &OperationSnapshot::status)
    .def_readonly("local_status", &OperationSnapshot::local_status)
    .def_readonly("cancel_status", &OperationSnapshot::cancel_status)
    .def_readonly("remote_execution_pending", &OperationSnapshot::remote_execution_pending)
    .def_readonly("success", &OperationSnapshot::success)
    .def_readonly("action_terminal_received", &OperationSnapshot::action_terminal_received)
    .def_readonly("result_received_seconds", &OperationSnapshot::result_received_seconds)
    .def_readonly("goal_id", &OperationSnapshot::goal_id)
    .def_readonly("message", &OperationSnapshot::message)
    .def_readonly("local_message", &OperationSnapshot::local_message)
    .def_readonly("cancel_message", &OperationSnapshot::cancel_message)
    .def_property_readonly("feedback", [](const OperationSnapshot &s) {
      py::dict result;
      for (const auto &v : s.feedback.numbers) result[py::str(v.first)] = v.second;
      for (const auto &v : s.feedback.flags) result[py::str(v.first)] = v.second;
      for (const auto &v : s.feedback.strings) result[py::str(v.first)] = v.second;
      return result;
    });
  py::class_<Operation, std::shared_ptr<Operation>>(m, "Operation")
    .def("snapshot", &Operation::snapshot)
    .def("wait", &Operation::wait, py::arg("timeout_seconds"), py::call_guard<py::gil_scoped_release>())
    .def("cancel", &Operation::cancel);
  py::class_<Client>(m, "Client")
    .def(py::init([](std::size_t capacity, double admission_timeout, bool automatic_cancel, bool sim_time, bool ownership) {
      ClientOptions o;
      o.max_pending_operations = capacity;
      o.admission_timeout_seconds = admission_timeout;
      o.cancel_on_admission_timeout = automatic_cancel;
      o.use_sim_time = sim_time;
      o.require_managed_ownership = ownership;
      return std::make_unique<Client>(o);
    }), py::arg("max_pending_operations") = 32, py::arg("admission_timeout_seconds") = 5.0,
        py::arg("cancel_on_admission_timeout") = false, py::arg("use_sim_time") = false,
        py::arg("require_managed_ownership") = false)
    .def("running", &Client::running)
    .def("server_ready", &Client::server_ready)
    .def("pending_operations", &Client::pending_operations)
    .def("close", &Client::close, py::arg("timeout_seconds") = 0.0, py::call_guard<py::gil_scoped_release>())
    .def("__enter__", [](Client &self) -> Client & { return self; }, py::return_value_policy::reference_internal)
    .def("__exit__", [](Client &self, py::object, py::object, py::object) {
      py::gil_scoped_release release;
      self.close(self.pending_operations() == 0 ? 2.0 : 0.0);
      return false;
    })
    .def("state", [](const Client &self) {
      const auto s = self.state(); const auto &v = s.value;
      py::dict d;
      d["received"] = s.received; d["fresh"] = s.fresh; d["receipt_age_seconds"] = s.receipt_age_seconds;
      d["receipt_fresh"] = s.receipt_fresh; d["source_time_valid"] = s.source_time_valid;
      d["source_age_seconds"] = s.source_age_seconds;
      d["frame_id"] = v.header.frame_id;
      d["stamp_sec"] = v.header.stamp.sec; d["stamp_nanosec"] = v.header.stamp.nanosec;
      d["connected"] = v.connected; d["pose_valid"] = v.pose_valid;
      d["velocity_valid"] = v.velocity_valid; d["attitude_valid"] = v.attitude_valid;
      d["armed"] = v.armed; d["flight_mode"] = v.flight_mode; d["flight_mode_name"] = v.flight_mode_name;
      d["position"] = py::make_tuple(v.position_x, v.position_y, v.position_z);
      d["velocity"] = py::make_tuple(v.velocity_x, v.velocity_y, v.velocity_z);
      d["yaw"] = v.yaw; d["battery_valid"] = v.battery_valid;
      d["gps_valid"] = v.gps_valid; d["rc_connected"] = v.rc_connected;
      d["battery_remaining"] = v.battery_remaining;
      return d;
    })
    .def("takeoff", [](Client &self, double altitude, double speed) {
      easyfly_msgs::action::Takeoff::Goal g; g.target_altitude = altitude; g.climb_speed = speed;
      return self.takeoff(g);
    }, py::arg("target_altitude"), py::arg("climb_speed") = 0.0)
    .def("land", [](Client &self, double speed) {
      easyfly_msgs::action::Land::Goal g; g.landing_speed = speed; return self.land(g);
    }, py::arg("landing_speed") = 0.0)
    .def("navigate", [](Client &self, double x, double y, double z, double speed) {
      easyfly_msgs::action::NavigateTo::Goal g; g.target_x=x; g.target_y=y; g.target_z=z; g.max_speed=speed;
      return self.navigate(g);
    }, py::arg("x"), py::arg("y"), py::arg("z") = std::numeric_limits<double>::quiet_NaN(), py::arg("max_speed") = 0.0)
    .def("execute_mission", [](Client &self, const std::string &file) {
      easyfly_msgs::action::ExecuteMission::Goal g; g.mission_file=file; return self.execute_mission(g);
    })
    .def("unsupported", &Client::unsupported);
}
