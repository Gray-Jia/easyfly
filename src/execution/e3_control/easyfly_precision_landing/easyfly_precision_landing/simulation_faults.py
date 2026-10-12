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

"""Opt-in SITL response withholding; never synthesize flight feedback or replies."""

import json
import math
import time

from easyfly_msgs.action import GoToWaypoint, Land, PrecisionLand, Takeoff
from easyfly_msgs.srv import ArmMotors, GetActionOwnership, GetCapabilities, SetFlightMode
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.task import Future

from easyfly_precision_landing.simulation_scenarios import (
    PrecisionScenario, ScenarioComplete, downstream_baseline,
    fresh_owned_state, fresh_status_mode,
)


FAULT_SCENARIOS = ('unknown-mode-late', 'unknown-mode-withheld')


def fault_snapshot(response, ros_now, elapsed):
    """Require explicit fresh internal fault evidence, not merely a refused goal."""
    if (response is None or response.names != ['takeoff']
            or response.implemented != [True] or response.ready != [False]
            or len(response.details) != 1):
        raise RuntimeError('flight fault snapshot shape invalid')
    try:
        detail = json.loads(response.details[0])
    except (ValueError, TypeError) as error:
        raise RuntimeError('flight fault snapshot JSON invalid') from error
    header = response.header
    stamp = header.stamp.sec * 1000000000 + header.stamp.nanosec
    if not (isinstance(detail, dict) and header.frame_id == 'odom'
            and header.stamp.sec >= 0 and 0 <= header.stamp.nanosec < 1000000000
            and stamp > 0 and ros_now > 0 and -.2 <= (ros_now - stamp) * 1e-9 <= 1.
            and 0 <= elapsed <= .3 and detail.get('clock_ns') == stamp
            and detail.get('reason') == 'command_uncertain'
            and detail.get('command_uncertain') is True and detail.get('ready') is False
            and detail.get('state_received') is True
            and type(detail.get('state_sequence')) is int and detail['state_sequence'] > 0
            and type(detail.get('state_source_ns')) is int and detail['state_source_ns'] > 0
            and -.2 <= (ros_now - detail['state_source_ns']) * 1e-9 <= 1.
            and isinstance(detail.get('receipt_age_s'), (int, float))
            and 0 <= detail['receipt_age_s'] + elapsed <= 1.
            and detail.get('active') == 0 and detail.get('action_reserved') is False
            and detail.get('precision_reserved') is False):
        raise RuntimeError('fresh released action with persistent flight fault not proven')
    return detail


class ModeFaultScenario(PrecisionScenario):
    """Delay only an actual internal Land reply and audit independent ownership."""

    scenario_names = FAULT_SCENARIOS
    fault_layer = 'flight controller service reply only'
    terminal_status = 6
    parent_message_prefix = 'command_result_unknown:'

    def __init__(self, name, node, report, latest, receipts, started):
        """Expose isolated test endpoints only for an explicit fault scenario."""
        if name not in self.scenario_names:
            raise ValueError('explicit fault scenario required')
        super().__init__(name, node, report, latest, receipts, started)
        group = ReentrantCallbackGroup()
        self.init_services(group)
        self.admission_gate, self.reply_gate = Future(), Future()
        self.pending_since = None
        self.tearing_down = False
        self.mode_calls, self.arm_calls = [], []
        report['scenario'].update(mode_calls=self.mode_calls, arm_calls=self.arm_calls,
                                  fault_layer=self.fault_layer, reply_policy=name)

    def init_services(self, group):
        """Bind only the original flight-level proxy endpoints for this fixture."""
        node = self.node
        self.real_mode = node.create_client(SetFlightMode, '/set_flight_mode',
                                            callback_group=group)
        self.real_arm = node.create_client(ArmMotors, '/arm_motors', callback_group=group)
        self.proxy_mode = node.create_service(SetFlightMode, '/d5_test/set_flight_mode',
                                              self.mode_request, callback_group=group)
        self.proxy_arm = node.create_service(ArmMotors, '/d5_test/arm_motors',
                                             self.arm_request, callback_group=group)

    async def arm_request(self, request, response):
        """Forward the unchanged real arm command and retain compensation evidence."""
        if not self.real_arm.service_is_ready():
            raise RuntimeError('real arming service unavailable; no retry')
        self.arm_calls.append({'arm': request.arm, 'received_steady': time.monotonic()})
        actual = await self.real_arm.call_async(request)
        response.success, response.message = actual.success, actual.message
        self.arm_calls[-1]['returned_steady'] = time.monotonic()
        return response

    async def mode_request(self, request, response):
        """Forward once, preserving the real reply while withholding its delivery."""
        if not self.real_mode.service_is_ready():
            raise RuntimeError('real mode service unavailable; no retry')
        entry = {'mode': request.flight_mode, 'received_steady': time.monotonic()}
        self.mode_calls.append(entry)
        if request.flight_mode == 7:
            if self.pending_since is not None:
                raise RuntimeError('duplicate internal Land mode request')
            self.pending_since = entry['received_steady']
            await self.admission_gate
            if self.tearing_down:
                entry['cleanup_returned_steady'] = time.monotonic()
                response.success, response.message = False, 'fixture closed before forwarding'
                return response
        entry['forwarded_steady'] = time.monotonic()
        actual = await self.real_mode.call_async(request)
        entry.update(upstream_reply_steady=time.monotonic(),
                     upstream_success=actual.success, upstream_message=actual.message)
        if request.flight_mode == 7:
            await self.reply_gate
        response.success, response.message = actual.success, actual.message
        entry['cleanup_returned_steady' if self.tearing_down else 'returned_steady'] = (
            time.monotonic())
        return response

    def tick(self):
        """Admit the injection only from fresh real phase, state and output traffic."""
        if self.injected is not None:
            self.confirm_real_land()
            return
        if self.pending_since is None:
            return
        now, clock = time.monotonic(), self.node.get_clock().now().nanoseconds
        if now - self.pending_since > 1.:
            raise RuntimeError('internal Land request injection evidence deadline')
        feedback = [item for item in self.report['precision_feedback']
                    if item['goal_uuid'] == self.identity]
        if not feedback or feedback[-1]['phase'] != 'land_handoff':
            return
        if not 0 <= now - self.started - feedback[-1]['elapsed_s'] <= .3:
            return
        if len(self.land_statuses) != 1 or next(iter(self.land_statuses.values())) != 2:
            return
        state, status = self.latest.get('/uav_state'), self.latest.get('/flight_status')
        if not (fresh_owned_state(state, self.receipts.get('/uav_state', 0.),
                                  clock, now, 'OFFBOARD') and
                fresh_status_mode(status, self.receipts.get('/flight_status', 0.),
                                  clock, now, 'OFFBOARD')):
            return
        baseline = downstream_baseline(self.output_samples, now)
        platform = sum(0 <= now - item['steady'] <= 1. for item in self.commands)
        if platform < 2:
            raise RuntimeError('fresh platform command baseline missing')
        self.injected = now
        self.report['scenario'].update(
            injected=True, injected_steady=now, goal_uuid=self.identity,
            trigger_phase='land_handoff', downstream_baseline=baseline,
            platform_baseline_count=platform, internal_land_at_injection=dict(self.land_statuses),
            injection_mode_source_ns=status.header.stamp.sec * 1000000000
            + status.header.stamp.nanosec)
        self.admission_gate.set_result(True)

    def confirm_real_land(self):
        """Require actual PX4 mode evidence; upstream success means only SET_MODE sent."""
        now, clock = time.monotonic(), self.node.get_clock().now().nanoseconds
        state, status = self.latest.get('/uav_state'), self.latest.get('/flight_status')
        if self.confirmed is not None:
            return
        if not (fresh_owned_state(state, self.receipts.get('/uav_state', 0.),
                                  clock, now, 'AUTO.LAND') and
                fresh_status_mode(status, self.receipts.get('/flight_status', 0.),
                                  clock, now, 'AUTO.LAND')):
            return
        source = status.header.stamp.sec * 1000000000 + status.header.stamp.nanosec
        if source <= self.report['scenario']['injection_mode_source_ns']:
            return
        self.confirmed = now
        self.report['scenario']['confirmed_mode_evidence'] = {
            'mode': status.flight_mode_name, 'source_ns': source,
            'steady': now, 'ros_age_s': (clock - source) * 1e-9,
            'origin_receipt_age_s': status.receipt_age_s,
            'observer_receipt_age_s': now - self.receipts['/flight_status'],
            'armed': status.armed, 'connected': status.connected, 'valid': status.valid}

    def query_fault(self, wait, label):
        """Record actual fresh internal locks without clearing them or reserving control."""
        client = self.node.create_client(GetCapabilities, '/platform/flight_control/capabilities')
        try:
            wait(client.service_is_ready, 5)
            began = time.monotonic()
            future = client.call_async(GetCapabilities.Request())
            wait(future.done, 3)
            now = time.monotonic()
            detail = fault_snapshot(future.result(), self.node.get_clock().now().nanoseconds,
                                    now - began)
            self.report['scenario'].setdefault('fault_snapshots', []).append(
                {'label': label, 'steady': now, 'snapshot': detail})
            return now
        finally:
            self.node.destroy_client(client)

    def check_stopped(self, wait, fault_began, label):
        """Check positive baseline to real silence on platform and all bridge outputs."""
        began = time.monotonic()
        wait(lambda: time.monotonic() - began >= 2.5, 4)
        counts = {'platform': sum(c['steady'] >= fault_began + .5 for c in self.commands),
                  'downstream': sum(t >= fault_began + 1.5 for t in self.outputs)}
        self.report['scenario'].setdefault('stream_checks', []).append(
            {'label': label, 'fault_steady': fault_began,
             'observed_until_steady': time.monotonic(), **counts})
        if any(counts.values()):
            raise RuntimeError('setpoints continued after command fault latch')

    def deny_followup(self, wait, label):
        """Send distinct bounded admission probes, never retry the original flight goal."""
        probes = (
            ('/takeoff', Takeoff, Takeoff.Goal(target_altitude=1., climb_speed=.3)),
            ('/land', Land, Land.Goal()),
            ('/goto_waypoint', GoToWaypoint, GoToWaypoint.Goal(target_z=1.)),
            ('/precision_land', PrecisionLand, PrecisionLand.Goal(tag_id=7, timeout=90.)),
        )
        for name, kind, goal in probes:
            client = ActionClient(self.node, kind, name)
            try:
                wait(client.server_is_ready, 5)
                future = client.send_goal_async(goal)
                wait(future.done, 3)
                handle = future.result()
                self.report['scenario'].setdefault('admission_probes', []).append(
                    {'label': label, 'name': name, 'goal_uuid': bytes(handle.goal_id.uuid).hex(),
                     'accepted': handle.accepted, 'steady': time.monotonic()})
                if handle.accepted:
                    result = handle.get_result_async()
                    cancel = handle.cancel_goal_async()
                    wait(cancel.done, 5)
                    wait(result.done, 20)
                    raise RuntimeError('follow-up flight admitted while fault latched')
            finally:
                client.destroy()

    def accept_terminal(self, value, wait):
        """Require true child drain and persistent fault before and after a late reply."""
        self.terminal = True
        if value.status != self.terminal_status or value.result.success:
            raise RuntimeError('scenario unexpected true terminal')
        if not value.result.message.startswith(self.parent_message_prefix):
            raise RuntimeError('unknown command outcome reported as a known failure')
        if self.injected is None:
            raise RuntimeError('scenario completed before requested injection')
        if self.confirmed is None:
            raise RuntimeError('real AUTO.LAND mode never independently confirmed')
        if self.reply_gate.done() or 'returned_steady' in self.mode_calls[-1]:
            raise RuntimeError('mode reply returned before the fault terminal')
        entry = self.mode_calls[-1]
        if (not entry.get('upstream_success') or
                entry.get('upstream_message') != 'mode=AUTO.LAND' or
                time.monotonic() - entry['received_steady'] < 4.9):
            raise RuntimeError('real successful upstream reply and local timeout not proven')
        self.audit_action_drain(value, wait)
        self.before_terminal_audit(wait)
        fault_began = self.query_fault(wait, 'terminal_before_reply')
        self.check_stopped(wait, fault_began, 'before_reply')
        # Native PX4 AUTO.LAND may complete physically; this is not Action success.
        self.wait_disarmed(wait)
        self.query_fault(wait, 'fresh_disarmed_before_reply')
        self.deny_followup(wait, 'before_reply')
        if self.name.endswith('-late'):
            self.report['scenario']['late_release_steady'] = time.monotonic()
            self.reply_gate.set_result(True)
            wait(lambda: 'returned_steady' in entry, 3)
        self.query_fault(wait, 'after_late_reply' if self.reply_gate.done() else 'still_withheld')
        self.deny_followup(wait, 'after_reply' if self.reply_gate.done() else 'still_withheld')
        self.check_stopped(wait, fault_began, 'final')
        if [item['mode'] for item in self.mode_calls] != [3, 7]:
            raise RuntimeError('mode retries or compensating commands detected')
        if [item['arm'] for item in self.arm_calls] != [True]:
            raise RuntimeError('compensating arm/disarm detected')
        self.report['scenario'].update(internal_land_statuses=dict(self.land_statuses),
                                       passed=True, negative_terminal_expected=True)
        raise ScenarioComplete()

    def audit_action_drain(self, value, wait):
        """Check exact precision ownership release and its sole child GetResult."""
        owner = self.node.create_client(GetActionOwnership, '/precision_landing/ownership')
        child = self.node.create_client(Land.Impl.GetResultService, '/land/_action/get_result')
        try:
            wait(owner.service_is_ready, 5)
            future = owner.call_async(GetActionOwnership.Request(goal_id=self.identity))
            wait(future.done, 3)
            response = future.result()
            if (response is None or response.goal_id != self.identity or
                    response.state != GetActionOwnership.Response.RELEASED):
                raise RuntimeError('exact precision action drain not confirmed')
            self.report['scenario']['ownership_released_uuid'] = self.identity
            identity = next(iter(self.report['scenario']['internal_land_at_injection']))
            wait(lambda: self.land_statuses == {identity: 6}, 5)
            wait(child.service_is_ready, 5)
            request = Land.Impl.GetResultService.Request()
            request.goal_id.uuid = list(bytes.fromhex(identity))
            future = child.call_async(request)
            wait(future.done, 3)
            result = future.result()
            if (result is None or result.status != 6 or result.result.success
                    or result.result.message != self.expected_child_message(value)):
                raise RuntimeError('matching true child abort result not confirmed')
            self.report['scenario']['internal_land_result'] = {
                'goal_uuid': identity, 'status': result.status,
                'success': result.result.success, 'message': result.result.message}
        finally:
            self.node.destroy_client(child)
            self.node.destroy_client(owner)

    def expected_child_message(self, value):
        """Keep the default parent and child fault result messages identical."""
        return value.result.message

    def before_terminal_audit(self, wait):
        """Allow a bounded subclass to audit an accepted pending parent cancellation."""

    def wait_disarmed(self, wait):
        """Observe real native disarming before probes; never send a disarm command."""
        def disarmed():
            state, status = self.latest.get('/uav_state'), self.latest.get('/flight_status')
            now, clock = time.monotonic(), self.node.get_clock().now().nanoseconds
            if state is None or status is None or state.armed or status.armed:
                return False
            source = state.header.stamp.sec * 1000000000 + state.header.stamp.nanosec
            origin = status.header.stamp.sec * 1000000000 + status.header.stamp.nanosec
            return (state.connected and state.pose_valid and state.attitude_valid
                    and status.valid and status.connected and source > 0 and origin > 0
                    and all(math.isfinite(v) for v in
                            (state.position_x, state.position_y, state.position_z))
                    and -.2 <= (clock - source) * 1e-9 <= 1.
                    and -.2 <= (clock - origin) * 1e-9 <= 1.
                    and 0 <= now - self.receipts.get('/uav_state', 0.) <= .3
                    and 0 <= now - self.receipts.get('/flight_status', 0.) <= .3
                    and 0 <= status.receipt_age_s
                    + now - self.receipts['/flight_status'] <= 1.)
        wait(disarmed, 30)
        self.report['scenario']['native_disarmed_before_probes'] = True
        state, status = self.latest['/uav_state'], self.latest['/flight_status']
        self.report['scenario']['disarmed_baseline'] = {
            'steady': time.monotonic(), 'clock_ns': self.node.get_clock().now().nanoseconds,
            'state_source_ns': state.header.stamp.sec * 1000000000 + state.header.stamp.nanosec,
            'mode_source_ns': status.header.stamp.sec * 1000000000 + status.header.stamp.nanosec,
            'state_armed': state.armed, 'status_armed': status.armed,
            'state_mode': state.flight_mode_name, 'status_mode': status.flight_mode_name}

    def drain(self, spin_once):
        """Drain held callbacks only after flight teardown, while the executor still runs."""
        self.tearing_down = True
        self.report['scenario']['fixture_drain_began_steady'] = time.monotonic()
        for gate in (self.admission_gate, self.reply_gate):
            if not gate.done():
                gate.set_result(True)
        deadline = time.monotonic() + 5.
        while time.monotonic() < deadline:
            spin_once()
            if (all('returned_steady' in row or 'cleanup_returned_steady' in row
                    for row in self.mode_calls)
                    and all('returned_steady' in row or 'cleanup_returned_steady' in row
                            for row in self.arm_calls)):
                self.report['scenario']['fixture_callbacks_drained'] = True
                return
        raise RuntimeError('fixture service callbacks did not drain before shutdown')

    def destroy(self):
        """Remove only owned fixture resources after the controlled flight process exits."""
        for gate in (self.admission_gate, self.reply_gate):
            if not gate.done():
                gate.cancel()
        self.node.destroy_service(self.proxy_mode)
        self.node.destroy_service(self.proxy_arm)
        self.node.destroy_client(self.real_mode)
        self.node.destroy_client(self.real_arm)
        super().destroy()
