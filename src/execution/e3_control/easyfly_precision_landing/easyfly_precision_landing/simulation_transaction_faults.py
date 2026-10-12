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

"""Bounded Takeoff cancellation during unknown transactions and upstream arming loss."""

import json
import math
import time

from easyfly_msgs.srv import GetCapabilities

from easyfly_precision_landing.simulation_arm_faults import (
    BridgeArmFaultScenario, fresh_arm_evidence,
)
from easyfly_precision_landing.simulation_faults import ModeFaultScenario
from easyfly_precision_landing.simulation_scenarios import downstream_baseline, exact_cancel


CANCEL_TRANSACTION_SCENARIOS = (
    'cancel-bridge-arm-late', 'cancel-bridge-arm-withheld',
    'cancel-bridge-mode-late', 'cancel-bridge-mode-withheld',
)
UPSTREAM_ARM_SCENARIOS = ('upstream-arm-late', 'upstream-arm-withheld')


def available_bridge_snapshot(response, ros_now, elapsed):
    """Require live independent transport availability, not an assumed second fault."""
    if (response is None or response.names != ['flight_command_transport']
            or response.implemented != [True] or response.ready != [True]
            or len(response.details) != 1):
        raise RuntimeError('bridge available snapshot shape invalid')
    try:
        detail = json.loads(response.details[0])
    except (ValueError, TypeError) as error:
        raise RuntimeError('bridge available snapshot JSON invalid') from error
    stamp = response.header.stamp.sec * 1000000000 + response.header.stamp.nanosec
    if not (isinstance(detail, dict) and response.header.frame_id == 'odom'
            and stamp > 0 and ros_now > 0 and -.2 <= (ros_now - stamp) * 1e-9 <= 1.
            and 0 <= elapsed <= .3 and detail.get('clock_ns') == stamp
            and detail.get('reason') == 'command_transport_available'
            and detail.get('command_fault') is False and detail.get('ready') is True
            and detail.get('context_ok') is True and detail.get('mode_service_ready') is True
            and detail.get('arming_service_ready') is True):
        raise RuntimeError('live independent available bridge not proven')
    return detail


def fresh_ground_sources(state, status, receipts, clock, now):
    """Require real fresh matching disarmed baseline before an initial mode request."""
    if state is None or status is None or clock <= 0:
        return False
    source = state.header.stamp.sec * 1000000000 + state.header.stamp.nanosec
    origin = status.header.stamp.sec * 1000000000 + status.header.stamp.nanosec
    numeric = (state.position_x, state.position_y, state.position_z)
    return (source > 0 and origin > 0 and state.connected and state.pose_valid
            and state.attitude_valid and status.connected and status.valid
            and not state.armed and not status.armed and state.flight_mode <= 7
            and bool(state.flight_mode_name) and state.flight_mode_name == status.flight_mode_name
            and all(math.isfinite(v) for v in numeric)
            and -.2 <= (clock - source) * 1e-9 <= 1.
            and -.2 <= (clock - origin) * 1e-9 <= 1.
            and 0 <= now - receipts.get('/uav_state', 0.) <= .3
            and 0 <= now - receipts.get('/flight_status', 0.) <= .3
            and 0 <= status.receipt_age_s + now - receipts['/flight_status'] <= 1.)


class CancelTransactionScenario(BridgeArmFaultScenario):
    """Cancel only the owned Takeoff after actual remote state and before reply timeout."""

    scenario_names = CANCEL_TRANSACTION_SCENARIOS
    terminal_status = 5

    def __init__(self, *args):
        """Prevent nested observer waits from recursively querying the same pending snapshot."""
        super().__init__(*args)
        self.recording_pending = False

    @property
    def fault_layer(self):
        """Label the actual withheld transaction, not a generic outer timeout."""
        return ('bridge MAVROS mode service reply only' if self.mode_fault else
                'bridge MAVROS arming service reply only')

    @property
    def mode_fault(self):
        """Distinguish the initial OFFBOARD transaction from the subsequent arm transaction."""
        return '-mode-' in self.name

    async def mode_request(self, request, response):
        """Withhold the real initial SetMode reply only for explicit mode-cancel cases."""
        if not self.mode_fault:
            return await super().mode_request(request, response)
        if (request.custom_mode != 'OFFBOARD' or request.base_mode != 0
                or self.pending_since is not None):
            raise RuntimeError('mode retry or compensating mode detected')
        if not self.real_mode.service_is_ready():
            raise RuntimeError('real MAVROS mode service unavailable; no retry')
        entry = dict(mode=3, custom_mode=request.custom_mode, base_mode=request.base_mode,
                     received_steady=time.monotonic())
        self.mode_calls.append(entry)
        self.pending_since = entry['received_steady']
        await self.admission_gate
        if self.tearing_down:
            entry['cleanup_returned_steady'] = time.monotonic()
            response.mode_sent = False
            return response
        entry['forwarded_steady'] = time.monotonic()
        actual = await self.real_mode.call_async(request)
        entry.update(upstream_reply_steady=time.monotonic(), upstream_success=actual.mode_sent,
                     upstream_reply_semantics='MAVROS mode_sent; not FCU COMMAND_ACK')
        await self.reply_gate
        response.mode_sent = actual.mode_sent
        entry['cleanup_returned_steady' if self.tearing_down else 'returned_steady'] = (
            time.monotonic())
        return response

    async def arm_request(self, request, response):
        """Never arm after unresolved OFFBOARD; arm cases keep the real arming gate."""
        if self.mode_fault:
            raise RuntimeError('unexpected arming after unknown initial mode request')
        return await super().arm_request(request, response)

    def tick_mode(self):
        """Gate initial mode send on ground evidence; confirm OFFBOARD with both sources."""
        if self.pending_since is None:
            return
        now, clock = time.monotonic(), self.node.get_clock().now().nanoseconds
        state, status = self.latest.get('/uav_state'), self.latest.get('/flight_status')
        if self.injected is None:
            if now - self.pending_since > 1.:
                raise RuntimeError('initial mode injection evidence deadline')
            if self.identity is None or self.takeoff_statuses != {self.identity: 2}:
                return
            if not fresh_ground_sources(state, status, self.receipts, clock, now):
                return
            baseline = downstream_baseline(self.output_samples, now)
            platform = sum(0 <= now - item['steady'] <= 1. for item in self.commands)
            if platform < 2:
                raise RuntimeError('fresh platform mode command baseline missing')
            self.injected = now
            self.report['scenario'].update(
                injected=True, injected_steady=now, goal_uuid=self.identity,
                trigger_phase='takeoff_preparing_mode', downstream_baseline=baseline,
                platform_baseline_count=platform, takeoff_at_injection=dict(self.takeoff_statuses),
                injection_evidence=dict(
                    clock_ns=clock, state_armed=state.armed, status_armed=status.armed,
                    state_mode=state.flight_mode_name, status_mode=status.flight_mode_name,
                    state_source_ns=state.header.stamp.sec * 1000000000
                    + state.header.stamp.nanosec,
                    mode_source_ns=status.header.stamp.sec * 1000000000
                    + status.header.stamp.nanosec))
            self.admission_gate.set_result(True)
        if self.confirmed is not None or not fresh_arm_evidence(
                state, status, self.receipts, clock, now, False):
            return
        source = state.header.stamp.sec * 1000000000 + state.header.stamp.nanosec
        origin = status.header.stamp.sec * 1000000000 + status.header.stamp.nanosec
        before = self.report['scenario']['injection_evidence']
        if source <= before['state_source_ns'] or origin <= before['mode_source_ns']:
            return
        self.confirmed = now
        self.report['scenario']['confirmed_initial_mode'] = dict(
            steady=now, clock_ns=clock, state_source_ns=source, mode_source_ns=origin,
            mode=status.flight_mode_name, state_armed=state.armed, status_armed=status.armed,
            state_ros_age_s=(clock - source) * 1e-9, mode_ros_age_s=(clock - origin) * 1e-9,
            state_receipt_age_s=now - self.receipts['/uav_state'],
            observer_receipt_age_s=now - self.receipts['/flight_status'],
            origin_receipt_age_s=status.receipt_age_s)

    def tick(self):
        """Submit a single exact cancel only within the known live pending transaction."""
        if self.mode_fault:
            self.tick_mode()
        else:
            super().tick()
        if self.confirmed is None or self.cancel is not None:
            return
        entry = self.reply_entry()
        now = time.monotonic()
        if (now - entry['received_steady'] >= 3. or self.reply_gate.done()
                or 'returned_steady' in entry or self.takeoff_statuses != {self.identity: 2}):
            raise RuntimeError('cancel was not inside the actual pending request')
        self.report['scenario']['cancel_request_steady'] = now
        self.cancel = self.handle.cancel_goal_async()
        self.pending_result = self.handle.get_result_async()

    def reply_entry(self):
        """Return actual original positive mode send or arming ACK, never FCU fiction."""
        if not self.mode_fault:
            return super().reply_entry()
        if len(self.mode_calls) != 1 or not self.mode_calls[0].get('upstream_success'):
            raise RuntimeError('one real successful initial mode send not proven')
        return self.mode_calls[0]

    def before_terminal_audit(self, wait):
        """Require exact cancel ACK and bounded transaction reservation observed while pending."""
        if self.cancel is None:
            raise RuntimeError('cancel was never requested')
        wait(self.cancel.done, 3)
        response = self.cancel.result()
        self.report['scenario']['cancel_ack_exact'] = exact_cancel(response, self.identity)
        if not exact_cancel(response, self.identity):
            raise RuntimeError('exact cancellation not accepted')
        if not self.report['scenario'].get('pending_cancel_snapshot'):
            raise RuntimeError('pending cancellation reservation not recorded')
        ack = self.report['scenario']['cancel_ack_steady']
        wait(lambda: time.monotonic() - ack >= 2.5, 3)
        counts = dict(platform=sum(row['steady'] >= ack + .5 for row in self.commands),
                      downstream=sum(value >= ack + 1.5 for value in self.outputs))
        self.report['scenario']['cancel_stream_check'] = dict(
            cancel_ack_steady=ack, observed_until_steady=time.monotonic(), **counts)
        if any(counts.values()):
            raise RuntimeError('outputs continued during pending cancellation')

    def record_pending(self, wait):
        """Observe real cancel ACK, unresolved GetResult and still-reserved internal action."""
        if (self.recording_pending or self.cancel is None or not self.cancel.done()
                or self.report['scenario'].get('pending_cancel_snapshot')):
            return
        if not exact_cancel(self.cancel.result(), self.identity):
            raise RuntimeError('exact pending cancel not accepted')
        response = self.cancel.result()
        self.report['scenario']['cancel_response'] = dict(
            return_code=response.return_code,
            goals_canceling=[bytes(row.goal_id.uuid).hex() for row in response.goals_canceling])
        if self.pending_result.done() or self.reply_gate.done():
            raise RuntimeError('Takeoff released before local transaction drain')
        self.report['scenario']['cancel_ack_steady'] = time.monotonic()
        self.recording_pending = True
        client = self.node.create_client(GetCapabilities, '/platform/flight_control/capabilities')
        try:
            wait(lambda: self.takeoff_statuses == {self.identity: 3}, 1)
            wait(client.service_is_ready, 1)
            began = time.monotonic()
            future = client.call_async(GetCapabilities.Request())
            wait(future.done, 1)
            elapsed = time.monotonic() - began
            response = future.result()
            detail = json.loads(response.details[0])
            if (response.names != ['takeoff'] or response.ready != [False] or elapsed > .3
                    or not detail.get('action_reserved') or detail.get('active') == 0
                    or detail.get('command_uncertain') or not detail.get('context_ok')
                    or self.pending_result.done()):
                raise RuntimeError('issued command did not retain pending cancellation lock')
            self.report['scenario']['pending_cancel_snapshot'] = detail
            self.report['scenario']['pending_cancel_query'] = dict(
                steady=time.monotonic(), query_elapsed_s=elapsed,
                clock_ns=self.node.get_clock().now().nanoseconds,
                takeoff_statuses=dict(self.takeoff_statuses), pending_result_done=False)
        finally:
            self.node.destroy_client(client)
            self.recording_pending = False

    def verify_calls(self):
        """Initial-mode cancellation must never arm; both variants forbid compensation."""
        if self.mode_fault:
            if ([row['mode'] for row in self.mode_calls] != [3] or self.arm_calls
                    or self.land_statuses or self.report['precision_feedback']):
                raise RuntimeError('mode-cancel arming, retry or compensation detected')
        else:
            super().verify_calls()


class UpstreamArmFaultScenario(BridgeArmFaultScenario):
    """Withhold only flight-to-bridge arming reply; bridge must remain independently healthy."""

    scenario_names = UPSTREAM_ARM_SCENARIOS
    owns_bridge = False
    fault_layer = 'flight controller arming service reply only'

    def init_services(self, group):
        """Bind typed public bridge services with only the owned flight clients remapped."""
        ModeFaultScenario.init_services(self, group)

    async def mode_request(self, request, response):
        """Pass through the original initial OFFBOARD reply unchanged."""
        if request.flight_mode != 3:
            raise RuntimeError('unexpected mode compensation in upstream arming scenario')
        return await ModeFaultScenario.mode_request(self, request, response)

    async def arm_request(self, request, response):
        """Hold one real successful EasyFly arm reply without affecting the bridge transaction."""
        if not request.arm or self.pending_since is not None:
            raise RuntimeError('upstream arming retry or disarm detected')
        if not self.real_arm.service_is_ready():
            raise RuntimeError('real bridge arming service unavailable; no retry')
        entry = dict(arm=request.arm, received_steady=time.monotonic())
        self.arm_calls.append(entry)
        self.pending_since = entry['received_steady']
        await self.admission_gate
        if self.tearing_down:
            entry['cleanup_returned_steady'] = time.monotonic()
            response.success, response.message = False, 'fixture closed before forwarding'
            return response
        entry['forwarded_steady'] = time.monotonic()
        actual = await self.real_arm.call_async(request)
        entry.update(upstream_reply_steady=time.monotonic(),
                     success=actual.success, message=actual.message)
        await self.reply_gate
        response.success, response.message = actual.success, actual.message
        entry['cleanup_returned_steady' if self.tearing_down else 'returned_steady'] = (
            time.monotonic())
        return response

    def reply_entry(self):
        """Require one original successful bridge reply, not a manufactured MAVROS ACK."""
        if len(self.arm_calls) != 1 or not self.arm_calls[0].get('success'):
            raise RuntimeError('one successful bridge arming reply not proven')
        entry = self.arm_calls[0]
        if entry.get('message') != 'armed':
            raise RuntimeError('original bridge arming reply not proven')
        return entry

    def query_fault(self, wait, label):
        """Confirm flight fault and distinct non-faulted bridge via read-only queries."""
        flight_time = ModeFaultScenario.query_fault(self, wait, label)
        client = self.node.create_client(GetCapabilities, '/platform/mavlink_bridge/capabilities')
        try:
            wait(client.service_is_ready, 3)
            began = time.monotonic()
            future = client.call_async(GetCapabilities.Request())
            wait(future.done, 1)
            now = time.monotonic()
            clock = self.node.get_clock().now().nanoseconds
            detail = available_bridge_snapshot(future.result(), clock, now - began)
            self.report['scenario'].setdefault('bridge_transport_snapshots', []).append(
                dict(label=label, steady=now, ros_now_ns=clock,
                     query_elapsed_s=now - began, snapshot=detail))
            return max(flight_time, now)
        finally:
            self.node.destroy_client(client)

    def deny_followup(self, wait, label):
        """Probe flight admission only; do not command the healthy bridge directly."""
        ModeFaultScenario.deny_followup(self, wait, label)


TRANSACTION_SCENARIO_TYPES = {
    **dict.fromkeys(CANCEL_TRANSACTION_SCENARIOS, CancelTransactionScenario),
    **dict.fromkeys(UPSTREAM_ARM_SCENARIOS, UpstreamArmFaultScenario),
}
