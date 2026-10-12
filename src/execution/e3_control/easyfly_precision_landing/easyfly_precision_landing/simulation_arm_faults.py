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

"""Explicit Takeoff arming-reply faults; no synthesized state or compensating commands."""

import math
import time

from action_msgs.msg import GoalStatusArray
from easyfly_msgs.action import Takeoff
from rclpy.qos import DurabilityPolicy, QoSProfile

from easyfly_precision_landing.simulation_bridge_faults import BridgeModeFaultScenario
from easyfly_precision_landing.simulation_scenarios import ScenarioComplete, downstream_baseline


BRIDGE_ARM_FAULT_SCENARIOS = ('bridge-arm-late', 'bridge-arm-withheld')


def fresh_arm_evidence(state, status, receipts, clock, now, armed):
    """Require independent fresh OFFBOARD evidence with matching actual arming state."""
    if state is None or status is None or clock <= 0:
        return False
    source = state.header.stamp.sec * 1000000000 + state.header.stamp.nanosec
    origin = status.header.stamp.sec * 1000000000 + status.header.stamp.nanosec
    numeric = (state.position_x, state.position_y, state.position_z,
               state.roll, state.pitch, state.yaw)
    return (source > 0 and origin > 0 and state.connected and state.pose_valid
            and state.attitude_valid and status.valid and status.connected
            and state.armed == armed and status.armed == armed
            and state.flight_mode == 3 and state.flight_mode_name == 'OFFBOARD'
            and status.flight_mode_name == 'OFFBOARD'
            and all(math.isfinite(v) for v in numeric)
            and -.2 <= (clock - source) * 1e-9 <= 1.
            and -.2 <= (clock - origin) * 1e-9 <= 1.
            and 0 <= now - receipts.get('/uav_state', 0.) <= .3
            and 0 <= now - receipts.get('/flight_status', 0.) <= .3
            and 0 <= status.receipt_age_s + now - receipts['/flight_status'] <= 1.)


class BridgeArmFaultScenario(BridgeModeFaultScenario):
    """Hold one real CommandBool reply during Takeoff preparation, never climb."""

    scenario_names = BRIDGE_ARM_FAULT_SCENARIOS
    fault_layer = 'bridge MAVROS arming service reply only'
    action_name = '/takeoff'
    terminal_status = 6

    def __init__(self, *args):
        """Observe the actual owned Takeoff status before opening the send gate."""
        super().__init__(*args)
        self.takeoff_statuses = {}
        self.subscriptions.append(self.node.create_subscription(
            GoalStatusArray, '/takeoff/_action/status', self.takeoff_status,
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)))

    def takeoff_status(self, message):
        """Keep exact status identities, including status arriving before attach."""
        for entry in message.status_list:
            self.takeoff_statuses[bytes(entry.goal_info.goal_id.uuid).hex()] = entry.status

    async def mode_request(self, request, response):
        """Permit only unchanged initial OFFBOARD; any compensation fails the fixture."""
        if request.custom_mode != 'OFFBOARD' or request.base_mode != 0:
            raise RuntimeError('unexpected mode command in arming fault scenario')
        return await super().mode_request(request, response)

    async def arm_request(self, request, response):
        """Forward one actual arm request and withhold its original ACK fields."""
        if not request.value or self.pending_since is not None:
            raise RuntimeError('arming retry or compensating disarm detected')
        if not self.real_arm.service_is_ready():
            raise RuntimeError('real MAVROS arming service unavailable; no retry')
        entry = {'arm': request.value, 'received_steady': time.monotonic()}
        self.arm_calls.append(entry)
        self.pending_since = entry['received_steady']
        await self.admission_gate
        if self.tearing_down:
            entry['cleanup_returned_steady'] = time.monotonic()
            response.success, response.result = False, 4  # Fixture closed before send.
            return response
        entry['forwarded_steady'] = time.monotonic()
        actual = await self.real_arm.call_async(request)
        entry.update(upstream_reply_steady=time.monotonic(),
                     success=actual.success, result=actual.result)
        await self.reply_gate
        response.success, response.result = actual.success, actual.result
        entry['cleanup_returned_steady' if self.tearing_down else 'returned_steady'] = (
            time.monotonic())
        return response

    def state(self, message):
        """Arming is not external takeover; OFFBOARD evidence must not imply reclamation."""
        pass

    def flight_status(self, message):
        """Observe arming through tick using independent sources, not takeover semantics."""
        pass

    def tick(self):
        """Admit on actual ground OFFBOARD and confirm real arming before reply release."""
        if self.pending_since is None:
            return
        now, clock = time.monotonic(), self.node.get_clock().now().nanoseconds
        state, status = self.latest.get('/uav_state'), self.latest.get('/flight_status')
        if self.injected is None:
            if now - self.pending_since > 1.:
                raise RuntimeError('Takeoff arming injection evidence deadline')
            if self.identity is None or self.takeoff_statuses != {self.identity: 2}:
                return
            if not fresh_arm_evidence(state, status, self.receipts, clock, now, False):
                return
            baseline = downstream_baseline(self.output_samples, now)
            platform = sum(0 <= now - item['steady'] <= 1. for item in self.commands)
            if platform < 2:
                raise RuntimeError('fresh platform ground command baseline missing')
            self.injected = now
            self.report['scenario'].update(
                injected=True, injected_steady=now, goal_uuid=self.identity,
                trigger_phase='takeoff_preparing_arm', downstream_baseline=baseline,
                platform_baseline_count=platform,
                takeoff_at_injection=dict(self.takeoff_statuses),
                injection_evidence={'clock_ns': clock, 'state_armed': state.armed,
                                    'status_armed': status.armed, 'position_z': state.position_z,
                                    'state_source_ns': state.header.stamp.sec * 1000000000
                                    + state.header.stamp.nanosec,
                                    'mode_source_ns': status.header.stamp.sec * 1000000000
                                    + status.header.stamp.nanosec})
            self.admission_gate.set_result(True)
        if self.confirmed is not None or not fresh_arm_evidence(
                state, status, self.receipts, clock, now, True):
            return
        source = state.header.stamp.sec * 1000000000 + state.header.stamp.nanosec
        origin = status.header.stamp.sec * 1000000000 + status.header.stamp.nanosec
        before = self.report['scenario']['injection_evidence']
        if source <= before['state_source_ns'] or origin <= before['mode_source_ns']:
            return
        self.confirmed = now
        self.report['scenario']['confirmed_arm_evidence'] = {
            'steady': now, 'clock_ns': clock, 'state_source_ns': source,
            'mode_source_ns': origin, 'state_armed': state.armed, 'status_armed': status.armed,
            'mode': status.flight_mode_name, 'connected': status.connected,
            'valid': status.valid, 'state_ros_age_s': (clock - source) * 1e-9,
            'mode_ros_age_s': (clock - origin) * 1e-9,
            'state_receipt_age_s': now - self.receipts['/uav_state'],
            'observer_receipt_age_s': now - self.receipts['/flight_status'],
            'origin_receipt_age_s': status.receipt_age_s}

    def reply_entry(self):
        """Select the sole positively acknowledged arming request for terminal audit."""
        if len(self.arm_calls) != 1:
            raise RuntimeError('single real arming request not proven')
        entry = self.arm_calls[0]
        if not entry.get('success') or entry.get('result') != 0:
            raise RuntimeError('real arming ACK not proven')
        return entry

    def before_terminal_audit(self, wait):
        """Leave normal fault-only behavior unchanged; cancel fixtures add exact ACK checks."""
        pass

    def verify_calls(self):
        """Reject retry or compensation without assuming a successful Takeoff."""
        if ([row['mode'] for row in self.mode_calls] != [3]
                or [row['arm'] for row in self.arm_calls] != [True]
                or self.land_statuses or self.report['precision_feedback']):
            raise RuntimeError('retry, compensation, Land or precision action detected')

    def accept_terminal(self, value, wait):
        """Require true Takeoff abort, distinct locks and safe post-disarm probe batches."""
        self.terminal = True
        if (value.status != self.terminal_status or value.result.success or value.result.message !=
                'command_result_unknown: flight fault latch set; manual audit required'):
            raise RuntimeError('arming outcome did not produce true unknown Takeoff abort')
        if self.injected is None or self.confirmed is None:
            raise RuntimeError('real remote transaction injection not proven')
        entry = self.reply_entry()
        if (self.reply_gate.done() or 'returned_steady' in entry
                or time.monotonic() - entry['received_steady'] < 4.9):
            raise RuntimeError('real command reply and local timeout not proven')
        self.before_terminal_audit(wait)
        wait(lambda: self.takeoff_statuses == {self.identity: self.terminal_status}, 5)
        client = self.node.create_client(
            Takeoff.Impl.GetResultService, '/takeoff/_action/get_result')
        try:
            wait(client.service_is_ready, 5)
            request = Takeoff.Impl.GetResultService.Request()
            request.goal_id.uuid = list(bytes.fromhex(self.identity))
            future = client.call_async(request)
            wait(future.done, 3)
            result = future.result()
            if (result is None or result.status != self.terminal_status or result.result.success
                    or result.result.message != value.result.message):
                raise RuntimeError('exact Takeoff true GetResult not confirmed')
            self.report['scenario']['takeoff_get_result'] = {
                'goal_uuid': self.identity, 'status': result.status,
                'success': result.result.success, 'message': result.result.message}
        finally:
            self.node.destroy_client(client)
        fault_began = self.query_fault(wait, 'terminal_before_reply')
        self.check_stopped(wait, fault_began, 'before_reply')
        self.wait_disarmed(wait)  # PX4's original protection, not a platform disarm request.
        self.query_fault(wait, 'fresh_disarmed_before_reply')
        self.deny_followup(wait, 'before_reply')
        if self.name.endswith('-late'):
            self.report['scenario']['late_release_steady'] = time.monotonic()
            self.reply_gate.set_result(True)
            wait(lambda: 'returned_steady' in entry, 3)
        self.query_fault(wait, 'after_late_reply' if self.reply_gate.done() else 'still_withheld')
        self.deny_followup(wait, 'after_reply' if self.reply_gate.done() else 'still_withheld')
        self.check_stopped(wait, fault_began, 'final')
        self.verify_calls()
        self.report['scenario'].update(takeoff_statuses=dict(self.takeoff_statuses),
                                       passed=True, negative_terminal_expected=True)
        raise ScenarioComplete()
