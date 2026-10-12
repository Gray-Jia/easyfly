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

"""Explicit downstream MAVROS reply faults with independent bridge latch evidence."""

import json
import time

from easyfly_msgs.srv import ArmMotors, GetCapabilities, SetFlightMode
from mavros_msgs.srv import CommandBool, SetMode

from easyfly_precision_landing.simulation_faults import ModeFaultScenario


BRIDGE_FAULT_SCENARIOS = ('bridge-mode-late', 'bridge-mode-withheld')


def bridge_fault_snapshot(response, ros_now, elapsed):
    """Require live bridge fault evidence even while both real service peers exist."""
    if (response is None or response.names != ['flight_command_transport']
            or response.implemented != [True] or response.ready != [False]
            or len(response.details) != 1):
        raise RuntimeError('bridge fault snapshot shape invalid')
    try:
        detail = json.loads(response.details[0])
    except (ValueError, TypeError) as error:
        raise RuntimeError('bridge fault snapshot JSON invalid') from error
    header = response.header
    stamp = header.stamp.sec * 1000000000 + header.stamp.nanosec
    if not (isinstance(detail, dict) and header.frame_id == 'odom'
            and header.stamp.sec >= 0 and 0 <= header.stamp.nanosec < 1000000000
            and stamp > 0 and ros_now > 0 and -.2 <= (ros_now - stamp) * 1e-9 <= 1.
            and 0 <= elapsed <= .3 and detail.get('clock_ns') == stamp
            and detail.get('reason') == 'command_fault_locked'
            and detail.get('command_fault') is True and detail.get('ready') is False
            and detail.get('context_ok') is True
            and detail.get('mode_service_ready') is True
            and detail.get('arming_service_ready') is True):
        raise RuntimeError('live independent bridge fault not proven')
    return detail


class BridgeModeFaultScenario(ModeFaultScenario):
    """Withhold only MAVROS replies; flight-to-bridge services remain unmodified."""

    scenario_names = BRIDGE_FAULT_SCENARIOS
    fault_layer = 'bridge MAVROS service reply only'
    owns_bridge = True

    def init_services(self, group):
        """Remap only the owned bridge clients; real MAVROS stays at original names."""
        self.real_mode = self.node.create_client(SetMode, '/mavros/set_mode', callback_group=group)
        self.real_arm = self.node.create_client(CommandBool, '/mavros/cmd/arming',
                                                callback_group=group)
        self.proxy_mode = self.node.create_service(
            SetMode, '/d5_test/mavros/set_mode', self.mode_request, callback_group=group)
        self.proxy_arm = self.node.create_service(
            CommandBool, '/d5_test/mavros/cmd/arming', self.arm_request, callback_group=group)

    async def arm_request(self, request, response):
        """Forward the real unchanged CommandBool and retain its actual ACK fields."""
        if not self.real_arm.service_is_ready():
            raise RuntimeError('real MAVROS arming service unavailable; no retry')
        entry = {'arm': request.value, 'received_steady': time.monotonic()}
        self.arm_calls.append(entry)
        actual = await self.real_arm.call_async(request)
        response.success, response.result = actual.success, actual.result
        entry.update(returned_steady=time.monotonic(),
                     success=actual.success, result=actual.result)
        return response

    async def mode_request(self, request, response):
        """Forward one actual SET_MODE request without manufacturing FCU confirmation."""
        if not self.real_mode.service_is_ready():
            raise RuntimeError('real MAVROS mode service unavailable; no retry')
        if request.custom_mode not in ('OFFBOARD', 'AUTO.LAND') or request.base_mode != 0:
            raise RuntimeError('unexpected platform mode command in bridge fault scenario')
        entry = {'mode': 7 if request.custom_mode == 'AUTO.LAND' else 3,
                 'custom_mode': request.custom_mode, 'base_mode': request.base_mode,
                 'received_steady': time.monotonic()}
        self.mode_calls.append(entry)
        if entry['mode'] == 7:
            if self.pending_since is not None:
                raise RuntimeError('duplicate internal Land MAVROS mode request')
            self.pending_since = entry['received_steady']
            await self.admission_gate
            if self.tearing_down:
                entry['cleanup_returned_steady'] = time.monotonic()
                response.mode_sent = False  # Known fixture close before any real forwarding.
                return response
        entry['forwarded_steady'] = time.monotonic()
        actual = await self.real_mode.call_async(request)
        entry.update(upstream_reply_steady=time.monotonic(), upstream_success=actual.mode_sent,
                     upstream_message='mode=' + request.custom_mode,
                     upstream_reply_semantics='MAVROS mode_sent; not FCU COMMAND_ACK')
        if entry['mode'] == 7:
            await self.reply_gate
        response.mode_sent = actual.mode_sent
        entry['cleanup_returned_steady' if self.tearing_down else 'returned_steady'] = (
            time.monotonic())
        return response

    def query_fault(self, wait, label):
        """Query both distinct locks; do not confuse the outer five-second timeout."""
        flight_time = super().query_fault(wait, label)
        client = self.node.create_client(GetCapabilities, '/platform/mavlink_bridge/capabilities')
        try:
            wait(client.service_is_ready, 5)
            deadline = time.monotonic() + 2.
            while time.monotonic() < deadline:
                began = time.monotonic()
                future = client.call_async(GetCapabilities.Request())
                wait(future.done, 1)
                response, now = future.result(), time.monotonic()
                if response is not None and response.ready == [False]:
                    clock = self.node.get_clock().now().nanoseconds
                    detail = bridge_fault_snapshot(
                        response, clock, now - began)
                    self.report['scenario'].setdefault('bridge_fault_snapshots', []).append(
                        {'label': label, 'steady': now, 'ros_now_ns': clock,
                         'query_elapsed_s': now - began, 'snapshot': detail})
                    return max(flight_time, now)
                wait(lambda: time.monotonic() - now >= .02, 1)
            raise RuntimeError('bridge independent fault did not latch after timeout')
        finally:
            self.node.destroy_client(client)

    def deny_followup(self, wait, label):
        """Probe bridge services directly, in addition to rejected flight action goals."""
        super().deny_followup(wait, label)
        for name, kind, request in (
            ('/set_flight_mode', SetFlightMode, SetFlightMode.Request(flight_mode=3)),
            ('/arm_motors', ArmMotors, ArmMotors.Request(arm=True)),
        ):
            client = self.node.create_client(kind, name)
            try:
                wait(client.service_is_ready, 5)
                future = client.call_async(request)
                wait(future.done, 3)
                response = future.result()
                record = {'label': label, 'name': name, 'steady': time.monotonic(),
                          'success': response.success, 'message': response.message}
                record['request'] = ({'flight_mode': request.flight_mode}
                                     if kind is SetFlightMode else {'arm': request.arm})
                self.report['scenario'].setdefault('bridge_service_probes', []).append(record)
                if response.success or response.message != (
                        'command_result_unknown: bridge fault locked; '
                        'inspect remote state before restart'):
                    raise RuntimeError('bridge follow-up command not refused by its own fault')
            finally:
                self.node.destroy_client(client)
