# Copyright 2026 EasyFly Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Explicit simulation-only lifecycle probes; never fabricate flight observations."""

import math
from functools import partial
from pathlib import Path
import time

from action_msgs.msg import GoalStatusArray
from easyfly_msgs.action import Land
from easyfly_msgs.srv import GetActionOwnership
from geometry_msgs.msg import PoseStamped, Twist
from mavros_msgs.msg import AttitudeTarget, PositionTarget
from mavros_msgs.srv import SetMode
from rclpy.qos import qos_profile_sensor_data, DurabilityPolicy, QoSProfile
from sensor_msgs.msg import Image


TAKEOVERS = {
    'external-takeover': ('AUTO.LAND', 'descend', 'OFFBOARD'),
    'external-posctl-descent': ('POSCTL', 'descend', 'OFFBOARD'),
    'external-posctl-handoff': ('POSCTL', 'land_handoff', 'AUTO.LAND'),
    'external-rtl-descent': ('AUTO.RTL', 'descend', 'OFFBOARD'),
    'external-rtl-handoff': ('AUTO.RTL', 'land_handoff', 'AUTO.LAND'),
}
SCENARIOS = ('nominal', 'loss-recover', 'loss-persistent', 'cancel-descent',
             'cancel-handoff', *TAKEOVERS)
DOWNSTREAM_TOPICS = (
    (PoseStamped, '/mavros/setpoint_position/local'),
    (Twist, '/mavros/setpoint_velocity/cmd_vel_unstamped'),
    (AttitudeTarget, '/mavros/setpoint_raw/attitude'),
    (PositionTarget, '/mavros/setpoint_raw/local'),
)


def downstream_baseline(samples, now):
    """Require actual recent position-mode bridge traffic before a takeover test."""
    counts = {topic: sum(s['topic'] == topic and 0 <= now - s['steady'] <= 1.
                         for s in samples) for _, topic in DOWNSTREAM_TOPICS}
    if counts['/mavros/setpoint_position/local'] < 2:
        raise RuntimeError('fresh downstream position traffic baseline missing')
    return counts


class ScenarioComplete(Exception):
    """Finish an expected negative scenario without misreporting successful landing."""


def fresh_owned_state(state, receipt, ros_now, now, mode):
    """Require current armed connected valid pose evidence before an injection."""
    if state is None:
        return False
    stamp = state.header.stamp.sec * 1000000000 + state.header.stamp.nanosec
    return (stamp > 0 and ros_now > 0 and -.2 <= (ros_now - stamp) * 1e-9 <= 1.
            and 0 <= now - receipt <= .3 and state.connected and state.armed
            and state.pose_valid and state.flight_mode_name == mode
            and all(math.isfinite(v) for v in
                    (state.position_x, state.position_y, state.position_z)))


def fresh_status_mode(status, receipt, ros_now, now, mode):
    """Check original independent mode evidence, not renewed aggregate timestamps."""
    if status is None:
        return False
    header = status.header.stamp
    source = header.sec * 1000000000 + header.nanosec
    return (header.sec >= 0 and 0 <= header.nanosec < 1000000000
            and source > 0 and ros_now > 0 and -.2 <= (ros_now - source) * 1e-9 <= 1.
            and 0 <= now - receipt <= .3
            and 0 <= status.receipt_age_s + now - receipt <= 1.
            and status.valid and status.connected and status.armed
            and status.flight_mode_name == mode)


def held_commands(commands, began, ended):
    """Compare real held position commands after one control/observation settling interval."""
    window = [c for c in commands if began + .15 <= c['steady'] <= ended]
    if len(window) < 2:
        return False
    return all(c['mode'] == 0 and all(abs(a - b) <= 1e-6 for a, b in
               zip(c['position'], window[0]['position'])) for c in window)


def exact_cancel(response, identity):
    """Accept only successful cancellation of this exact UUID, not another goal's ACK."""
    return (response is not None and response.return_code == 0
            and [bytes(g.goal_id.uuid).hex() for g in response.goals_canceling] == [identity])


def loss_hold_end(feedback, identity, started, restored):
    """Bound active loss by recovery or the last holding phase, never ownership wait."""
    if restored is not None:
        return restored
    phases = [f for f in feedback if f['goal_uuid'] == identity]
    failed = [f['elapsed_s'] for f in phases if f['phase'] == 'failed']
    held = [f['elapsed_s'] for f in phases if f['phase'] in ('lost_hold', 'reacquire_hold')]
    if not failed or not held or max(held) >= min(failed):
        raise RuntimeError('active loss/failed phase boundary evidence missing')
    return started + max(held)


def owned_descendants(parent):
    """Read only the process tree created by this isolated simulation owner."""
    found = {}
    try:
        children = Path(f'/proc/{parent}/task/{parent}/children').read_text().split()
    except FileNotFoundError:
        return found
    for child in children:
        try:
            base = Path('/proc') / child
            found[child] = {'executable': str(base.joinpath('exe').resolve(strict=True)),
                            'start_ticks': base.joinpath('stat').read_text().rsplit(
                                ')', 1)[1].split()[19]}
        except (FileNotFoundError, ProcessLookupError):
            continue
        found.update(owned_descendants(child))
    return found


def remaining_owned(identities):
    """Count live or zombie identities without confusing a reused PID with our process."""
    residuals = []
    for pid, identity in identities.items():
        try:
            ticks = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
            if ticks == identity['start_ticks']:
                residuals.append({'pid': pid, **identity})
        except (FileNotFoundError, ProcessLookupError):
            pass
    return residuals


class PrecisionScenario:
    """Inject only after actual matching feedback and verify exact terminal ownership."""

    def __init__(self, name, node, report, latest, receipts, started):
        """Prepare explicit probe resources without submitting any flight command."""
        self.name, self.node, self.report = name, node, report
        self.latest, self.receipts, self.started = latest, receipts, started
        self.identity = None
        self.handle = None
        self.terminal = False
        self.injected = None
        self.restored = None
        self.first_lost = None
        self.cancel = None
        self.mode_future = None
        self.confirmed = None
        self.images_enabled = True
        self.commands, self.outputs, self.land_statuses = [], [], {}
        self.output_samples = []
        self.relay = (node.create_publisher(Image, '/d5_test/image_raw', qos_profile_sensor_data)
                      if name.startswith('loss-') else None)
        self.mode_client = (node.create_client(SetMode, '/mavros/set_mode')
                            if name in TAKEOVERS else None)
        self.subscriptions = [node.create_subscription(
            kind, topic, partial(self.downstream, topic), qos_profile_sensor_data)
            for kind, topic in DOWNSTREAM_TOPICS]
        self.subscriptions.append(node.create_subscription(
            GoalStatusArray, '/land/_action/status', self.land_status,
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)))
        report['scenario'] = {'name': name, 'injected': False}
        report['scenario']['command_samples'] = self.commands
        report['scenario']['downstream_steady_samples'] = self.outputs
        report['scenario']['downstream_samples'] = self.output_samples
        if name in TAKEOVERS:
            mode, phase, baseline = TAKEOVERS[name]
            report['scenario'].update(requested_mode=mode, requested_phase=phase,
                                      baseline_mode=baseline)

    def downstream(self, topic, message):
        """Observe all actual bridge outputs; reject truncated acceptance evidence."""
        if len(self.outputs) >= 10000:
            raise RuntimeError('downstream observation capacity exhausted')
        now = time.monotonic()
        self.outputs.append(now)
        self.output_samples.append({'topic': topic, 'steady': now})

    def land_status(self, message):
        """Observe the sole internal Land started during the owned precision action."""
        if self.identity is not None:
            for entry in message.status_list:
                self.land_statuses[bytes(entry.goal_info.goal_id.uuid).hex()] = entry.status

    def image(self, message):
        """Forward unmodified actual camera messages, or suppress them during deliberate loss."""
        if self.relay is not None and self.images_enabled:
            self.relay.publish(message)

    def command(self, message):
        """Retain bounded real command intent, not a synthesized hold position."""
        if len(self.commands) < 10000:
            self.commands.append({'steady': time.monotonic(), 'mode': message.control_mode,
                                  'position': [message.position_x, message.position_y,
                                               message.position_z]})

    def state(self, message):
        """Detect fresh OFFBOARD reclamation even after the public action has terminated."""
        if self.confirmed is not None and fresh_owned_state(
                message, time.monotonic(), self.node.get_clock().now().nanoseconds,
                time.monotonic(), 'OFFBOARD'):
            raise RuntimeError('platform reclaimed OFFBOARD after external takeover')

    def flight_status(self, message):
        """Keep monitoring independent mode ownership after public termination."""
        now = time.monotonic()
        source = message.header.stamp.sec * 1000000000 + message.header.stamp.nanosec
        if self.confirmed is not None and fresh_status_mode(
                message, now, self.node.get_clock().now().nanoseconds, now, 'OFFBOARD') and (
                    source > self.report['scenario']['confirmed_mode_evidence']['source_ns']):
            raise RuntimeError('platform reclaimed OFFBOARD after external takeover')

    def attach(self, handle):
        """Bind one accepted action; never cancel a global action slot."""
        self.handle = handle
        self.identity = bytes(handle.goal_id.uuid).hex()

    def tick(self):
        """Perform nonblocking injections from actual fresh feedback and state."""
        if self.identity is None or self.terminal or self.name == 'nominal':
            return
        now = time.monotonic()
        feedback = [f for f in self.report['precision_feedback']
                    if f['goal_uuid'] == self.identity]
        if not feedback:
            return
        last = feedback[-1]
        phase = last['phase']
        state = self.latest.get('/uav_state')
        receipt = self.receipts.get('/uav_state', 0.)
        ros_now = self.node.get_clock().now().nanoseconds
        fresh = fresh_owned_state(state, receipt, ros_now, now, 'OFFBOARD')
        phase_fresh = 0 <= now - self.started - last['elapsed_s'] <= .3
        if self.injected is None:
            trigger = (TAKEOVERS[self.name][1] if self.name in TAKEOVERS else
                       'land_handoff' if self.name == 'cancel-handoff' else 'descend')
            if phase != trigger or not phase_fresh:
                return
            if trigger == 'land_handoff':
                fresh = fresh_owned_state(state, receipt, ros_now, now, 'AUTO.LAND')
            if not fresh:
                return
            if self.name in TAKEOVERS:
                mode, _, baseline = TAKEOVERS[self.name]
                status = self.latest.get('/flight_status')
                if not fresh_status_mode(status, self.receipts.get('/flight_status', 0.),
                                         ros_now, now, baseline):
                    return
                if trigger == 'land_handoff' and (
                        len(self.land_statuses) != 1 or
                        next(iter(self.land_statuses.values())) != 2):
                    return
                if not self.mode_client.service_is_ready():
                    raise RuntimeError('external takeover service unavailable; no retry')
                self.report['scenario']['downstream_baseline'] = downstream_baseline(
                    self.output_samples, now)
                self.report['scenario']['injection_mode_source_ns'] = (
                    status.header.stamp.sec * 1000000000 + status.header.stamp.nanosec)
                self.report['scenario']['injection_mode_origin_age_s'] = status.receipt_age_s
                self.report['scenario']['internal_land_at_injection'] = dict(self.land_statuses)
            self.injected = now
            self.report['scenario'].update(injected=True, injected_steady=now,
                                           goal_uuid=self.identity, trigger_phase=phase,
                                           state_mode=state.flight_mode_name,
                                           state_z=state.position_z)
            if self.name.startswith('loss-'):
                self.images_enabled = False
            elif self.name.startswith('cancel-'):
                self.cancel = self.handle.cancel_goal_async()
            elif self.name in TAKEOVERS:
                self.mode_future = self.mode_client.call_async(
                    SetMode.Request(custom_mode=mode))
        if self.name.startswith('loss-'):
            if phase == 'lost_hold' and self.first_lost is None:
                self.first_lost = now
                self.report['scenario']['first_lost_steady'] = now
            if (self.name == 'loss-recover' and self.first_lost is not None
                    and now - self.first_lost >= .6 and self.restored is None):
                self.images_enabled = True
                self.restored = now
                self.report['scenario']['restored_steady'] = now
        if self.name in TAKEOVERS and self.mode_future is not None:
            if self.mode_future.done():
                response = self.mode_future.result()
                if response is None or not response.mode_sent:
                    raise RuntimeError('external mode request not sent')
            if not self.confirm_takeover() and self.confirmed is not None and fresh:
                raise RuntimeError('platform reclaimed OFFBOARD after external takeover')

    def confirm_takeover(self):
        """Record fresh real PX4 mode confirmation, independently of a service ACK."""
        now = time.monotonic()
        if self.injected is None:
            return False
        mode = TAKEOVERS[self.name][0]
        status = self.latest.get('/flight_status')
        status_receipt = self.receipts.get('/flight_status', 0.)
        ros_now = self.node.get_clock().now().nanoseconds
        if fresh_owned_state(self.latest.get('/uav_state'),
                             self.receipts.get('/uav_state', 0.),
                             ros_now, now, mode) and fresh_status_mode(
                                 status, status_receipt, ros_now, now, mode):
            source = status.header.stamp.sec * 1000000000 + status.header.stamp.nanosec
            if source <= self.report['scenario']['injection_mode_source_ns']:
                return False
            if self.confirmed is None:
                self.confirmed = now
                self.report['scenario']['takeover_confirmed_steady'] = now
                self.report['scenario']['confirmed_mode_evidence'] = {
                    'source_ns': source, 'ros_age_s': (ros_now - source) * 1e-9,
                    'observer_receipt_age_s': now - status_receipt,
                    'origin_receipt_age_s': status.receipt_age_s,
                    'mode': status.flight_mode_name, 'armed': status.armed,
                    'connected': status.connected, 'valid': status.valid,
                }
            return True
        return False

    def accept_terminal(self, value, wait):
        """Require precise true terminal, cancellation ACK, and ownership release."""
        self.terminal = True
        expected = (5 if self.name.startswith('cancel-') else
                    6 if self.name == 'loss-persistent' or self.name in TAKEOVERS else 4)
        if value.status != expected or value.result.success != (expected == 4):
            raise RuntimeError('scenario unexpected true terminal')
        if self.name != 'nominal' and self.injected is None:
            raise RuntimeError('scenario completed before requested injection')
        if self.cancel is not None:
            wait(self.cancel.done, 5)
            response = self.cancel.result()
            self.report['scenario']['cancel_ack_exact'] = exact_cancel(response, self.identity)
            if not exact_cancel(response, self.identity):
                raise RuntimeError('exact cancel was not confirmed')
        client = self.node.create_client(GetActionOwnership, '/precision_landing/ownership')
        try:
            wait(client.service_is_ready, 5)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                future = client.call_async(GetActionOwnership.Request(goal_id=self.identity))
                wait(future.done, 3)
                response = future.result()
                if (response is not None and response.goal_id == self.identity
                        and response.state == GetActionOwnership.Response.RELEASED):
                    self.report['scenario']['ownership_released_uuid'] = self.identity
                    break
            else:
                raise TimeoutError('precision ownership did not release')
        finally:
            self.node.destroy_client(client)
        if self.first_lost is not None:
            ended = loss_hold_end(self.report['precision_feedback'], self.identity,
                                  self.started, self.restored)
            self.report['scenario']['loss_hold_window'] = {
                'begin_steady': self.first_lost + .15, 'end_steady': ended,
                'sample_count': len([c for c in self.commands
                                     if self.first_lost + .15 <= c['steady'] <= ended])}
            self.report['scenario']['loss_hold_commands_valid'] = held_commands(
                self.commands, self.first_lost, ended)
            if not self.report['scenario']['loss_hold_commands_valid']:
                raise RuntimeError('lost target command hold evidence missing or drifted')
        if self.name == 'loss-recover':
            phases = [f['phase'] for f in self.report['precision_feedback']
                      if f['goal_uuid'] == self.identity and self.restored is not None
                      and f['elapsed_s'] + self.started >= self.restored]
            cursor = 0
            for phase in ('reacquire_hold', 'align', 'descend', 'land_handoff'):
                try:
                    cursor = phases.index(phase, cursor) + 1
                except ValueError as error:
                    raise RuntimeError(
                        'missing ordered reacquire/alignment/descent evidence') from error
        if self.name == 'loss-persistent':
            if self.first_lost is None or 'landing_target_' not in value.result.message:
                raise RuntimeError('not the intended persistent target loss failure')
            if self.land_statuses:
                raise RuntimeError('persistent target loss unexpectedly started Land')
        if self.name == 'cancel-handoff':
            wait(lambda: len(self.land_statuses) == 1 and
                 next(iter(self.land_statuses.values())) == 5, 5)
        if self.name in TAKEOVERS:
            if TAKEOVERS[self.name][1] == 'land_handoff':
                wait(lambda: len(self.land_statuses) == 1 and
                     next(iter(self.land_statuses.values())) == 6, 5)
                identity = next(iter(self.land_statuses))
                if set(self.report['scenario']['internal_land_at_injection']) != {identity}:
                    raise RuntimeError('internal Land identity changed after injection')
                child_client = self.node.create_client(
                    Land.Impl.GetResultService, '/land/_action/get_result')
                try:
                    wait(child_client.service_is_ready, 5)
                    request = Land.Impl.GetResultService.Request()
                    request.goal_id.uuid = list(bytes.fromhex(identity))
                    child = child_client.call_async(request)
                    wait(child.done, 5)
                    response = child.result()
                    if response is None or response.status != 6 or response.result.success:
                        raise RuntimeError('internal Land true abort result missing')
                    if 'external mode takeover during Land' not in response.result.message:
                        raise RuntimeError('internal Land failed for an unrelated reason')
                    self.report['scenario']['internal_land_result'] = {
                        'goal_uuid': identity, 'status': response.status,
                        'success': response.result.success, 'message': response.result.message,
                    }
                finally:
                    self.node.destroy_client(child_client)
            elif self.land_statuses:
                raise RuntimeError('descent takeover unexpectedly started internal Land')
            expected_reason = ('external mode takeover during Land' if
                               TAKEOVERS[self.name][1] == 'land_handoff' else
                               'flight evidence/control lost')
            if expected_reason not in value.result.message:
                raise RuntimeError('precision failed for an unrelated reason')
        self.report['scenario']['internal_land_statuses'] = self.land_statuses
        if expected != 4:
            began = time.monotonic()
            if self.name in TAKEOVERS:
                wait(self.mode_future.done, 5)
                response = self.mode_future.result()
                if response is None or not response.mode_sent:
                    raise RuntimeError('external mode command was not sent')
                self.report['scenario']['external_mode_sent'] = True
                # Legacy field is a MAVROS send response, not FCU COMMAND_ACK.
                self.report['scenario']['external_mode_ack'] = True
                self.report['scenario']['external_mode_ack_semantics'] = (
                    'MAVROS SET_MODE sent; not FCU COMMAND_ACK')
                if self.confirmed is None:
                    wait(self.confirm_takeover, 5)
                wait(lambda: time.monotonic() - began >= 2.5, 4)
                late_commands = sum(c['steady'] >= self.confirmed + .5 for c in self.commands)
                late_outputs = sum(t >= self.confirmed + 1.5 for t in self.outputs)
                self.report['scenario']['takeover_stream_check'] = {
                    'confirmed_steady': self.confirmed, 'observed_until_steady': time.monotonic(),
                    'late_platform_commands': late_commands,
                    'late_downstream_outputs': late_outputs}
                if late_commands or late_outputs:
                    raise RuntimeError('platform setpoints continued after external takeover')
            else:
                wait(lambda: time.monotonic() - began >= .6, 2)
                if not fresh_owned_state(self.latest.get('/uav_state'),
                                         self.receipts.get('/uav_state', 0.),
                                         self.node.get_clock().now().nanoseconds,
                                         time.monotonic(), 'OFFBOARD'):
                    raise RuntimeError('cancel/loss did not retain trusted OFFBOARD hold')
                state = self.latest['/uav_state']
                source = state.header.stamp.sec * 1000000000 + state.header.stamp.nanosec
                self.report['scenario']['post_terminal_state'] = {
                    'source_ns': source, 'mode': state.flight_mode_name, 'armed': state.armed,
                    'connected': state.connected, 'pose_valid': state.pose_valid,
                    'ros_age_s': (self.node.get_clock().now().nanoseconds - source) * 1e-9,
                    'receipt_age_s': time.monotonic() - self.receipts['/uav_state'],
                    'position': [state.position_x, state.position_y, state.position_z]}
            self.report['scenario']['passed'] = True
            self.report['scenario']['negative_terminal_expected'] = True
            raise ScenarioComplete()
        self.report['scenario']['passed'] = True

    def destroy(self):
        """Dispose probe entities after the owned simulation has stopped."""
        for subscription in self.subscriptions:
            self.node.destroy_subscription(subscription)
        if self.relay is not None:
            self.node.destroy_publisher(self.relay)
        if self.mode_client is not None:
            self.node.destroy_client(self.mode_client)
