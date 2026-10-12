# Copyright 2026 EasyFly Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Actual flight process, synthetic aircraft feedback; explicitly not SITL."""

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from action_msgs.msg import GoalStatus, GoalStatusArray
from ament_index_python.packages import get_package_prefix
from easyfly_msgs.action import Land, PrecisionLand, Takeoff
from easyfly_msgs.msg import FlightStatus, LandingGuidanceTarget, UAVCommand, UAVState
from easyfly_msgs.srv import ArmMotors, GetActionOwnership, GetCapabilities, SetFlightMode
import pytest
import rclpy
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.qos import DurabilityPolicy, QoSProfile
from rclpy.task import Future


@pytest.mark.parametrize('parent', ['ordinary', 'precision'])
@pytest.mark.parametrize('reply', ['late', 'withheld'])
def test_land_cancel_unknown(parent, reply, tmp_path):
    """Audit terminal/lock first, then assert accepted parent cancel stops output."""
    case = parent + '-' + reply
    executable = Path(get_package_prefix('easyfly_flight_control')) / (
        'lib/easyfly_flight_control/flight_control_node')
    destination = Path(os.environ.get('EASYFLY_COMPONENT_EVIDENCE_DIR', tmp_path))
    destination.mkdir(parents=True, exist_ok=True)
    report_path = destination / (case + '.json')
    log_path = destination / (case + '-controller.log')
    assert not report_path.exists() and not log_path.exists(), 'never overwrite evidence'
    parameters = {
        'precision_enabled': 'true', 'precision_tag_id': '7',
        'precision_tag_size_m': '0.2', 'precision_horizontal_speed': '0.2',
        'precision_descent_speed': '0.1', 'precision_align_tolerance': '0.1',
        'precision_handoff_height': '0.3', 'precision_descent_floor_height': '0.2',
        'precision_max_height': '3.0', 'precision_max_radius': '2.0',
        'precision_plane_z': '0.0', 'land_timeout': '15.0',
    }
    controller_name = 'cancel_unknown_flight_' + case.replace('-', '_')
    command = [str(executable), '--ros-args', '-r', '__node:=' + controller_name]
    for key, value in parameters.items():
        command.extend(['-p', key + ':=' + value])
    evidence = {
        'case': case, 'kind': 'synthetic ROS component, not SITL',
        'flight_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
        'parameters': parameters, 'modes': [], 'arms': [], 'commands': [],
        'land_status': [], 'snapshots': [], 'audit_completed': False,
    }
    rclpy.init()
    node = rclpy.create_node('cancel_unknown_peer_' + case.replace('-', '_'))
    state = UAVState()
    state.header.frame_id = 'odom'
    state.connected = state.pose_valid = state.attitude_valid = True
    state.flight_mode = 2
    gate = Future()
    pending_since = None
    callback_completed = False

    async def mode_callback(request, response):
        nonlocal pending_since, callback_completed
        entry = {'mode': request.flight_mode, 'issued': time.monotonic()}
        evidence['modes'].append(entry)
        state.flight_mode = request.flight_mode
        response.success = True
        if request.flight_mode == 7:
            assert pending_since is None, 'never forward the unknown mode twice'
            pending_since = entry['issued']
            entry['synthetic_remote_executed'] = True
            await gate
            callback_completed = True
        entry['returned'] = time.monotonic()
        return response

    def arm_callback(request, response):
        evidence['arms'].append(request.arm)
        state.armed = request.arm
        state.position_z = 0.3 if request.arm else 0.0
        response.success = True
        return response

    node.create_service(SetFlightMode, '/set_flight_mode', mode_callback,
                        callback_group=ReentrantCallbackGroup())
    node.create_service(ArmMotors, '/arm_motors', arm_callback)
    state_pub = node.create_publisher(UAVState, '/uav_state', 10)
    status_pub = node.create_publisher(FlightStatus, '/flight_status', 10)
    target_pub = node.create_publisher(LandingGuidanceTarget, '/landing/guidance_target', 1)

    def output(message):
        evidence['commands'].append({
            'receipt': time.monotonic(), 'z': message.position_z,
            'source_ns': message.header.stamp.sec * 10**9 + message.header.stamp.nanosec})

    def land_status(message):
        for item in message.status_list:
            evidence['land_status'].append({
                'uuid': bytes(item.goal_info.goal_id.uuid).hex(), 'status': item.status,
                'receipt': time.monotonic()})

    node.create_subscription(UAVCommand, '/uav_command', output, 10)
    node.create_subscription(GoalStatusArray, '/land/_action/status', land_status,
                             QoSProfile(depth=10, durability=DurabilityPolicy.TRANSIENT_LOCAL))
    takeoff = ActionClient(node, Takeoff, '/takeoff')
    land = ActionClient(node, Land, '/land')
    precision = ActionClient(node, PrecisionLand, '/precision_land')
    child_result = node.create_client(Land.Impl.GetResultService, '/land/_action/get_result')
    ownership = node.create_client(GetActionOwnership, '/precision_landing/ownership')
    capabilities = node.create_client(GetCapabilities, '/platform/flight_control/capabilities')
    controller_log = log_path.open('x')
    process = subprocess.Popen(command, stdout=controller_log, stderr=subprocess.STDOUT)
    evidence['pid'] = process.pid
    evidence['start_ticks'] = Path('/proc/' + str(process.pid) + '/stat').read_text().split()[21]

    def pump(duration):
        end = time.monotonic() + duration
        while time.monotonic() < end:
            state.header.stamp = node.get_clock().now().to_msg()
            state_pub.publish(state)
            status = FlightStatus(valid=True, connected=True, armed=state.armed,
                                  flight_mode=state.flight_mode, receipt_age_s=0.0)
            status.header = state.header
            status.flight_mode_name = {3: 'OFFBOARD', 7: 'AUTO.LAND'}.get(
                state.flight_mode, 'OTHER')
            status_pub.publish(status)
            target = LandingGuidanceTarget(valid=True, tag_id=7, tag_size_m=0.2)
            target.header = state.header
            target.source_header.stamp = state.header.stamp
            target.source_header.frame_id = 'camera_down_optical_frame'
            target.plane_normal.z = 1.0
            target_pub.publish(target)
            rclpy.spin_once(node, timeout_sec=0.01)

    def wait(future, timeout=8):
        end = time.monotonic() + timeout
        while not future.done() and time.monotonic() < end:
            pump(0.02)
        assert future.done(), 'do not resend a Goal or command after missing response'
        assert future.exception() is None
        return future.result()

    def snapshot(label):
        response = wait(capabilities.call_async(GetCapabilities.Request()))
        detail = json.loads(response.details[0])
        evidence['snapshots'].append({'label': label, 'receipt': time.monotonic(), **detail})
        # flight_ready deliberately includes !command_uncertain; a latched
        # command fault must not be mistaken for stale synthetic feedback.
        valid = ['context_ok', 'state_received', 'connected', 'pose_valid',
                 'attitude_valid', 'numeric_valid']
        assert all(detail[key] for key in valid)
        assert -0.2 <= detail['source_age_s'] <= 1.0
        assert 0.0 <= detail['receipt_age_s'] <= 1.0
        return detail

    def owned(handle):
        request = GetActionOwnership.Request(goal_id=bytes(handle.goal_id.uuid).hex())
        return wait(ownership.call_async(request)).state

    try:
        deadline = time.monotonic() + 8
        settled = None
        while time.monotonic() < deadline:
            pump(0.02)
            matching = any(info.node_name == controller_name
                           for info in node.get_subscriptions_info_by_topic('/uav_state'))
            ready = matching and all(c.server_is_ready() for c in [takeoff, land, precision])
            ready = ready and all(
                c.service_is_ready() for c in [child_result, ownership, capabilities])
            if not ready:
                settled = None
            elif settled is None:
                settled = time.monotonic()
            elif time.monotonic() - settled >= 1.0:
                break
        else:
            pytest.fail('fresh process graph not settled; no Goal was sent')
        preparation = wait(takeoff.send_goal_async(Takeoff.Goal(target_altitude=0.3)))
        assert preparation.accepted
        assert wait(preparation.get_result_async()).status == GoalStatus.STATUS_SUCCEEDED
        pump(0.15)
        assert len(evidence['commands']) >= 2
        goal = Land.Goal() if parent == 'ordinary' else PrecisionLand.Goal(tag_id=7, timeout=15.0)
        handle = wait((land if parent == 'ordinary' else precision).send_goal_async(goal))
        assert handle.accepted
        evidence['goal_uuid'] = bytes(handle.goal_id.uuid).hex()
        result = handle.get_result_async()
        deadline = time.monotonic() + 3
        while ((pending_since is None or not evidence['land_status'])
               and time.monotonic() < deadline):
            pump(0.02)
        assert pending_since is not None and evidence['land_status']
        child_ids = {row['uuid'] for row in evidence['land_status']}
        assert len(child_ids) == 1
        evidence['child_uuid'] = next(iter(child_ids))
        if parent == 'ordinary':
            assert evidence['child_uuid'] == evidence['goal_uuid']
        request = Land.Impl.GetResultService.Request()
        request.goal_id.uuid = list(bytes.fromhex(evidence['child_uuid']))
        child_future = child_result.call_async(request)
        pending = snapshot('before_cancel')
        assert pending['action_reserved'] and not pending['command_uncertain']
        assert not result.done() and not child_future.done()
        pump(0.15)
        evidence['cancel_sent'] = time.monotonic()
        cancel = handle.cancel_goal_async()
        if parent == 'precision':
            response = wait(cancel, 1)
            evidence['cancel_accepted'] = time.monotonic()
            assert response.return_code == 0
            assert [bytes(g.goal_id.uuid).hex() for g in response.goals_canceling] == [
                evidence['goal_uuid']]
            pump(0.1)  # Exclude already queued commands from the silence window.
            evidence['cancel_window_start'] = time.monotonic()
            pump(0.3)
            evidence['cancel_window_end'] = time.monotonic()
            assert not result.done() and not child_future.done()
            assert owned(handle) == GetActionOwnership.Response.OWNED
        else:
            pump(0.3)
            assert not cancel.done() and not result.done() and not child_future.done()
        pending = snapshot('cancel_pending')
        assert pending['action_reserved'] and not pending['command_uncertain']
        wrapped = wait(result)
        child = wait(child_future)
        canceled = wait(cancel)
        evidence['cancel_return_code'] = canceled.return_code
        evidence['cancel_goals'] = [bytes(g.goal_id.uuid).hex() for g in canceled.goals_canceling]
        evidence['terminal'] = {
            'status': wrapped.status, 'success': wrapped.result.success,
            'message': wrapped.result.message, 'receipt': time.monotonic()}
        evidence['child_terminal'] = {
            'status': child.status, 'success': child.result.success,
            'message': child.result.message}
        assert child.status == GoalStatus.STATUS_ABORTED and not child.result.success
        assert child.result.message.startswith('command_result_unknown:')
        assert not wrapped.result.success
        assert wrapped.status == (GoalStatus.STATUS_CANCELED if parent == 'precision'
                                  else GoalStatus.STATUS_ABORTED)
        if parent == 'ordinary':
            assert not canceled.goals_canceling and canceled.return_code != 0
        else:
            assert owned(handle) == GetActionOwnership.Response.RELEASED
        assert time.monotonic() - pending_since >= 4.9 and not callback_completed
        assert snapshot('fault')['command_uncertain']
        pump(0.1)
        stopped = len(evidence['commands'])
        pump(0.3)
        assert len(evidence['commands']) == stopped
        state.armed = False  # Synthetic external state, not a platform disarm command.
        state.flight_mode = 2
        pump(0.1)
        assert not wait(takeoff.send_goal_async(Takeoff.Goal(target_altitude=1.0))).accepted
        assert not wait(land.send_goal_async(Land.Goal())).accepted
        probe = PrecisionLand.Goal(tag_id=7, timeout=15.0)
        assert not wait(precision.send_goal_async(probe)).accepted
        if reply == 'late':
            gate.set_result(True)
            deadline = time.monotonic() + 2
            while not callback_completed and time.monotonic() < deadline:
                pump(0.02)
            assert callback_completed
            assert snapshot('late_reply')['command_uncertain']
            assert not wait(takeoff.send_goal_async(Takeoff.Goal(target_altitude=1.0))).accepted
            pump(0.3)
            assert len(evidence['commands']) == stopped
        assert [row['mode'] for row in evidence['modes']] == [3, 7]
        assert evidence['arms'] == [True]
        process.send_signal(signal.SIGINT)
        assert process.wait(timeout=4) == 0
        evidence['audit_completed'] = True
        if parent == 'precision':
            window = [row for row in evidence['commands']
                      if evidence['cancel_window_start'] <= row['receipt']
                      <= evidence['cancel_window_end']]
            evidence['commands_after_accepted_cancel'] = len(window)
            assert not window, 'accepted PrecisionLand cancel still streams during child mode wait'
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=6)
            except subprocess.TimeoutExpired:
                evidence['forced_cleanup'] = True
                process.kill()
                process.wait(timeout=3)
        evidence['process_exit'] = process.returncode
        if not gate.done():
            evidence['gate_released_after_process_exit'] = True
            gate.set_result(True)
        if pending_since is not None:
            deadline = time.monotonic() + 2
            while not callback_completed and time.monotonic() < deadline:
                rclpy.spin_once(node, timeout_sec=0.01)
            evidence['callback_drained'] = callback_completed
        controller_log.close()
        node.destroy_node()
        rclpy.shutdown()
        evidence['pid_absent'] = not Path('/proc/' + str(process.pid)).exists()
        report_path.write_text(json.dumps(evidence, indent=2) + '\n')
