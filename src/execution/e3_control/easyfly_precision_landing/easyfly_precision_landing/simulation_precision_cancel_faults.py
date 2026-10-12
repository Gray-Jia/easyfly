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

"""Exact parent cancel during an actual, forwarded internal Land mode transaction."""

import json
import time

from action_msgs.msg import GoalStatusArray
from easyfly_msgs.action import Land
from easyfly_msgs.srv import GetActionOwnership, GetCapabilities
from rclpy.qos import DurabilityPolicy, QoSProfile

from easyfly_precision_landing.simulation_faults import ModeFaultScenario
from easyfly_precision_landing.simulation_scenarios import exact_cancel


PRECISION_CANCEL_FAULT_SCENARIOS = (
    'cancel-precision-mode-late', 'cancel-precision-mode-withheld')
CHILD_UNKNOWN_MESSAGE = 'command_result_unknown: flight fault latch set; manual audit required'


class CancelPrecisionModeScenario(ModeFaultScenario):
    """Hold a real reply, cancel the sole parent, and observe its child drain."""

    scenario_names = PRECISION_CANCEL_FAULT_SCENARIOS
    terminal_status = 5
    parent_message_prefix = 'precision landing canceled; child Land drained'

    def __init__(self, *args):
        """Create read-only queries before any Goal; never add a control service."""
        super().__init__(*args)
        self.recording_pending = False
        self.parent_statuses = {}
        self.parent_status_sub = self.node.create_subscription(
            GoalStatusArray, '/precision_land/_action/status', self.parent_status,
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.owner_query = self.node.create_client(
            GetActionOwnership, '/precision_landing/ownership')
        self.flight_query = self.node.create_client(
            GetCapabilities, '/platform/flight_control/capabilities')
        self.child_query = self.node.create_client(
            Land.Impl.GetResultService, '/land/_action/get_result')

    def parent_status(self, message):
        """Keep actual parent CANCELING evidence independently of its cancel ACK."""
        for row in message.status_list:
            self.parent_statuses[bytes(row.goal_info.goal_id.uuid).hex()] = row.status

    def tick(self):
        """Cancel only after the single original mode was forwarded and confirmed."""
        super().tick()
        if self.confirmed is None or self.cancel is not None:
            return
        entry = self.mode_calls[-1]
        if (time.monotonic() - entry['received_steady'] >= 3.
                or not entry.get('upstream_success') or self.reply_gate.done()
                or len(self.land_statuses) != 1 or next(iter(self.land_statuses.values())) != 2):
            raise RuntimeError('parent cancel not inside actual pending child transaction')
        if not all(c.service_is_ready() for c in
                   (self.owner_query, self.flight_query, self.child_query)):
            raise RuntimeError('read-only pending audit endpoints not ready; no retry')
        self.report['scenario']['cancel_request_steady'] = time.monotonic()
        self.cancel = self.handle.cancel_goal_async()
        self.pending_result = self.handle.get_result_async()
        request = Land.Impl.GetResultService.Request()
        request.goal_id.uuid = list(bytes.fromhex(next(iter(self.land_statuses))))
        self.pending_child = self.child_query.call_async(request)

    def record_pending(self, wait):
        """Prove exact parent CANCELING, owned lock and unresolved actual child result."""
        if (self.recording_pending or self.cancel is None or not self.cancel.done()
                or self.report['scenario'].get('pending_cancel_snapshot')):
            return
        response = self.cancel.result()
        if not exact_cancel(response, self.identity):
            raise RuntimeError('exact parent cancellation not accepted')
        self.recording_pending = True
        try:
            self.report['scenario']['cancel_ack_steady'] = time.monotonic()
            canceled_goals = [bytes(row.goal_id.uuid).hex() for row in response.goals_canceling]
            self.report['scenario']['cancel_response'] = dict(
                return_code=response.return_code, goals_canceling=canceled_goals)
            wait(lambda: self.parent_statuses.get(self.identity) == 3, 1)
            owner = self.owner_query.call_async(GetActionOwnership.Request(goal_id=self.identity))
            query_began = time.monotonic()
            flight = self.flight_query.call_async(GetCapabilities.Request())
            wait(lambda: owner.done() and flight.done(), 1)
            current = time.monotonic()
            detail = json.loads(flight.result().details[0])
            clock = self.node.get_clock().now().nanoseconds
            own = owner.result()
            if (own.goal_id != self.identity or own.state != GetActionOwnership.Response.OWNED
                    or self.pending_result.done() or self.pending_child.done()
                    or current - query_began > .3 or not detail.get('flight_ready')
                    or detail.get('command_uncertain') is not False
                    or detail.get('action_reserved') is not True
                    or detail.get('precision_reserved') is not True
                    or not -.2 <= (clock - detail['clock_ns']) * 1e-9 <= 1.
                    or not 0 <= detail['receipt_age_s'] + current - query_began <= 1.):
                raise RuntimeError('fresh pending parent/child ownership not proven')
            self.report['scenario']['pending_cancel_snapshot'] = dict(
                detail, steady=current, goal_uuid=self.identity, parent_status=3,
                owner_state=own.state, parent_result_pending=True, child_result_pending=True)
        finally:
            self.recording_pending = False

    def expected_child_message(self, value):
        """Parent cancellation must not hide the independently unknown child outcome."""
        return CHILD_UNKNOWN_MESSAGE

    def before_terminal_audit(self, wait):
        """Measure actual platform/downstream silence while both results were unresolved."""
        scene = self.report['scenario']
        if not scene.get('pending_cancel_snapshot') or not exact_cancel(
                self.cancel.result(), self.identity):
            raise RuntimeError('pending parent cancellation not audited')
        ack = scene['cancel_ack_steady']
        wait(lambda: time.monotonic() - ack >= 2.5, 3)
        counts = dict(platform=sum(row['steady'] >= ack + .5 for row in self.commands),
                      downstream=sum(value >= ack + 1.5 for value in self.outputs))
        scene['cancel_ack_exact'] = True
        scene['cancel_stream_check'] = dict(
            cancel_ack_steady=ack, observed_until_steady=time.monotonic(), **counts)
        if any(counts.values()):
            raise RuntimeError('outputs continued while canceled parent waited for child mode')

    def destroy(self):
        """Remove only this fixture's read-only resources after controlled teardown."""
        self.node.destroy_subscription(self.parent_status_sub)
        for client in (self.owner_query, self.flight_query, self.child_query):
            self.node.destroy_client(client)
        super().destroy()
