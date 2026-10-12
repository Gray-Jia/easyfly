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

"""Ordinary Land cancel cannot bypass its actual pending AUTO.LAND transaction."""

import json
import time

from easyfly_msgs.action import Land
from easyfly_msgs.srv import GetCapabilities

from easyfly_precision_landing.simulation_faults import ModeFaultScenario
from easyfly_precision_landing.simulation_scenarios import (
    downstream_baseline, fresh_owned_state, fresh_status_mode,
)


LAND_CANCEL_FAULT_SCENARIOS = ('cancel-land-mode-late', 'cancel-land-mode-withheld')


class CancelLandModeScenario(ModeFaultScenario):
    """Request exact cancellation but preserve the original Land transaction and lock."""

    scenario_names = LAND_CANCEL_FAULT_SCENARIOS
    action_name = '/land'

    def __init__(self, *args):
        """Create only independent read-only queries before the flight Goal."""
        super().__init__(*args)
        self.recording_pending = False
        self.flight_query = self.node.create_client(
            GetCapabilities, '/platform/flight_control/capabilities')

    def tick(self):
        """Inject from sole actual Land EXECUTING and fresh real OFFBOARD output baseline."""
        if self.injected is None:
            if self.pending_since is None:
                return
            now, clock = time.monotonic(), self.node.get_clock().now().nanoseconds
            if now - self.pending_since > 1.:
                raise RuntimeError('ordinary Land injection evidence deadline')
            if self.land_statuses != {self.identity: 2}:
                return
            state, status = self.latest.get('/uav_state'), self.latest.get('/flight_status')
            if not (fresh_owned_state(state, self.receipts.get('/uav_state', 0.),
                                      clock, now, 'OFFBOARD') and
                    fresh_status_mode(status, self.receipts.get('/flight_status', 0.),
                                      clock, now, 'OFFBOARD')):
                return
            baseline = downstream_baseline(self.output_samples, now)
            platform = sum(0 <= now - row['steady'] <= 1. for row in self.commands)
            if platform < 2:
                raise RuntimeError('actual platform command baseline missing')
            self.injected = now
            self.report['scenario'].update(
                injected=True, injected_steady=now, goal_uuid=self.identity,
                trigger_phase='ordinary_land_preparing', downstream_baseline=baseline,
                platform_baseline_count=platform, land_at_injection=dict(self.land_statuses),
                injection_mode_source_ns=status.header.stamp.sec * 1000000000
                + status.header.stamp.nanosec)
            self.admission_gate.set_result(True)
        self.confirm_real_land()
        if self.confirmed is None or self.cancel is not None:
            return
        entry = self.mode_calls[-1]
        if (time.monotonic() - entry['received_steady'] >= 3.
                or not entry.get('upstream_success') or self.reply_gate.done()
                or self.land_statuses != {self.identity: 2}):
            raise RuntimeError('ordinary cancel not inside the actual original transaction')
        self.report['scenario']['cancel_request_steady'] = time.monotonic()
        self.cancel = self.handle.cancel_goal_async()
        self.pending_result = self.handle.get_result_async()

    def record_pending(self, wait):
        """Prove cancel response waits on transaction while original Goal remains reserved."""
        if (self.recording_pending or self.cancel is None
                or self.report['scenario'].get('pending_cancel_snapshot')):
            return
        if self.cancel.done() or self.pending_result.done():
            raise RuntimeError('ordinary cancel bypassed pending transaction')
        self.recording_pending = True
        try:
            began = time.monotonic()
            future = self.flight_query.call_async(GetCapabilities.Request())
            wait(future.done, 1)
            now, clock = time.monotonic(), self.node.get_clock().now().nanoseconds
            detail = json.loads(future.result().details[0])
            if (self.cancel.done() or self.pending_result.done() or now - began > .3
                    or self.land_statuses != {self.identity: 2}
                    or detail.get('action_reserved') is not True
                    or detail.get('precision_reserved') is not False
                    or detail.get('command_uncertain') is not False
                    or not detail.get('flight_ready') or detail.get('active') == 0
                    or not -.2 <= (clock - detail['clock_ns']) * 1e-9 <= 1.
                    or not 0 <= detail['receipt_age_s'] + now - began <= 1.):
                raise RuntimeError('fresh original Land transaction reservation not proven')
            self.report['scenario']['pending_cancel_snapshot'] = dict(
                detail, steady=now, goal_uuid=self.identity, land_status=2,
                cancel_response_pending=True, result_pending=True)
        finally:
            self.recording_pending = False

    def audit_action_drain(self, value, wait):
        """Check the original exact Land GetResult, not precision ownership or a fake child."""
        wait(lambda: self.land_statuses == {self.identity: 6}, 3)
        client = self.node.create_client(Land.Impl.GetResultService, '/land/_action/get_result')
        try:
            wait(client.service_is_ready, 3)
            request = Land.Impl.GetResultService.Request()
            request.goal_id.uuid = list(bytes.fromhex(self.identity))
            future = client.call_async(request)
            wait(future.done, 3)
            result = future.result()
            if (result.status != 6 or result.result.success
                    or result.result.message != value.result.message):
                raise RuntimeError('original Land true abort result mismatch')
            self.report['scenario']['land_result'] = dict(
                goal_uuid=self.identity, status=result.status,
                success=result.result.success, message=result.result.message)
        finally:
            self.node.destroy_client(client)

    def before_terminal_audit(self, wait):
        """Require true cancel rejection only after the unknown original request drained."""
        if not self.report['scenario'].get('pending_cancel_snapshot'):
            raise RuntimeError('pending ordinary cancel transaction not audited')
        wait(self.cancel.done, 3)
        response = self.cancel.result()
        if response.return_code != 1 or response.goals_canceling:
            raise RuntimeError('ordinary cancel incorrectly accepted unknown mode outcome')
        self.report['scenario']['cancel_response'] = dict(
            return_code=response.return_code, goals_canceling=[], steady=time.monotonic())

    def destroy(self):
        """Remove only the owned read-only query after callback draining."""
        self.node.destroy_client(self.flight_query)
        super().destroy()
