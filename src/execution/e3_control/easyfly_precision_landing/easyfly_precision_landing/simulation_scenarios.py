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
from pathlib import Path
import time

from action_msgs.msg import GoalStatusArray
from easyfly_msgs.srv import GetActionOwnership
from mavros_msgs.msg import PositionTarget
from mavros_msgs.srv import SetMode
from rclpy.qos import qos_profile_sensor_data, DurabilityPolicy, QoSProfile
from sensor_msgs.msg import Image


SCENARIOS = ('nominal', 'loss-recover', 'loss-persistent', 'cancel-descent',
             'cancel-handoff', 'external-takeover')


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
        self.relay = (node.create_publisher(Image, '/d5_test/image_raw', qos_profile_sensor_data)
                      if name.startswith('loss-') else None)
        self.mode_client = (node.create_client(SetMode, '/mavros/set_mode')
                            if name == 'external-takeover' else None)
        self.subscriptions = [node.create_subscription(
            PositionTarget, '/mavros/setpoint_raw/local',
            lambda m: self.outputs.append(time.monotonic()), qos_profile_sensor_data)]
        self.subscriptions.append(node.create_subscription(
            GoalStatusArray, '/land/_action/status', self.land_status,
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)))
        report['scenario'] = {'name': name, 'injected': False}
        report['scenario']['command_samples'] = self.commands
        report['scenario']['downstream_steady_samples'] = self.outputs

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
            trigger = 'land_handoff' if self.name == 'cancel-handoff' else 'descend'
            if phase != trigger or not phase_fresh:
                return
            if self.name == 'cancel-handoff':
                fresh = fresh_owned_state(state, receipt, ros_now, now, 'AUTO.LAND')
            if not fresh:
                return
            self.injected = now
            self.report['scenario'].update(injected=True, injected_steady=now,
                                           goal_uuid=self.identity, trigger_phase=phase,
                                           state_mode=state.flight_mode_name,
                                           state_z=state.position_z)
            if self.name.startswith('loss-'):
                self.images_enabled = False
            elif self.name.startswith('cancel-'):
                self.cancel = self.handle.cancel_goal_async()
            elif self.name == 'external-takeover':
                if not self.mode_client.service_is_ready():
                    raise RuntimeError('external takeover service unavailable; no retry')
                self.mode_future = self.mode_client.call_async(
                    SetMode.Request(custom_mode='AUTO.LAND'))
        if self.name.startswith('loss-'):
            if phase == 'lost_hold' and self.first_lost is None:
                self.first_lost = now
                self.report['scenario']['first_lost_steady'] = now
            if (self.name == 'loss-recover' and self.first_lost is not None
                    and now - self.first_lost >= .6 and self.restored is None):
                self.images_enabled = True
                self.restored = now
                self.report['scenario']['restored_steady'] = now
        if self.name == 'external-takeover' and self.mode_future is not None:
            if self.mode_future.done() and not self.mode_future.result().mode_sent:
                raise RuntimeError('external mode request rejected')
            if not self.confirm_takeover() and self.confirmed is not None and fresh:
                raise RuntimeError('platform reclaimed OFFBOARD after external takeover')

    def confirm_takeover(self):
        """Record fresh real PX4 mode confirmation, independently of a service ACK."""
        now = time.monotonic()
        if fresh_owned_state(self.latest.get('/uav_state'),
                             self.receipts.get('/uav_state', 0.),
                             self.node.get_clock().now().nanoseconds, now, 'AUTO.LAND'):
            if self.confirmed is None:
                self.confirmed = now
                self.report['scenario']['takeover_confirmed_steady'] = now
            return True
        return False

    def accept_terminal(self, value, wait):
        """Require precise true terminal, cancellation ACK, and ownership release."""
        self.terminal = True
        expected = (5 if self.name.startswith('cancel-') else
                    6 if self.name in ('loss-persistent', 'external-takeover') else 4)
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
        self.report['scenario']['internal_land_statuses'] = self.land_statuses
        if expected != 4:
            began = time.monotonic()
            if self.name == 'external-takeover':
                wait(self.mode_future.done, 5)
                if not self.mode_future.result().mode_sent:
                    raise RuntimeError('external mode command was not acknowledged')
                self.report['scenario']['external_mode_ack'] = True
                if self.confirmed is None:
                    wait(self.confirm_takeover, 5)
                wait(lambda: time.monotonic() - began >= 2.5, 4)
                if (any(c['steady'] >= self.confirmed + .5 for c in self.commands)
                        or any(t >= self.confirmed + 1.5 for t in self.outputs)):
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
