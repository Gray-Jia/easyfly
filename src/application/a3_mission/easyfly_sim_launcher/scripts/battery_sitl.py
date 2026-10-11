#!/usr/bin/env python3
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

"""Explicit bounded battery sampling diagnosis; no fabricated input or automatic recovery."""

import argparse
import hashlib
import json
from pathlib import Path
import runpy
import time

from easyfly_msgs.action import ExecuteMission
from mavros_msgs.msg import SysStatus
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import BatteryState

SIBLING = Path(__file__).with_name('navigation_sitl.py')
if not SIBLING.is_file():
    SIBLING = Path(__file__).with_name('navigation_sitl')
LIBRARY = runpy.run_path(str(SIBLING), run_name='navigation_sitl_library')


class BatteryProbe(LIBRARY['Probe']):
    """Observe original PX4 publishers while running explicitly declared formal tasks."""

    def receive(self, name, msg):
        """Keep the base observations and capture read-only thread states on battery loss."""
        super().receive(name, msg)
        if name == '/uav_state' and msg.armed and not msg.battery_valid and \
                'battery_failure_threads' not in self.report:
            records = []
            for pid, identity in self.owned.items():
                if identity['executable'] != self.report['staging']['binary']:
                    continue
                base = Path(f'/proc/{pid}')
                try:
                    if base.joinpath('stat').read_text().rsplit(')', 1)[1].split()[19] != \
                            identity['start_ticks']:
                        continue
                    for task in base.joinpath('task').iterdir():
                        records.append({'pid': pid, 'tid': task.name,
                                        'name': task.joinpath('comm').read_text().strip(),
                                        'wchan': task.joinpath('wchan').read_text().strip(),
                                        'stat': task.joinpath('stat').read_text().strip()})
                except (FileNotFoundError, ProcessLookupError):
                    continue
            self.report['battery_failure_threads'] = {
                'steady': time.monotonic(), 'state': self.state(), 'threads': records}

    def sys_status(self, msg):
        """Retain the independent raw system status without using it as a battery fallback."""
        self.report['sys_status_samples'].append({
            'steady': time.monotonic(),
            'source_ns': msg.header.stamp.sec * 1000000000 + msg.header.stamp.nanosec,
            'voltage_battery': msg.voltage_battery, 'battery_remaining': msg.battery_remaining,
            'sensors_health': msg.sensors_health})

    def run(self):
        """Run at most three takeoff/hold/Land tasks, stopping immediately on a true failure."""
        self.report.update(battery_samples=[], sys_status_samples=[], cycles_completed=0,
                           battery_probe_sha256=hashlib.sha256(
                               Path(__file__).read_bytes()).hexdigest())
        self.node.create_subscription(BatteryState, '/mavros/battery', self.battery,
                                      qos_profile_sensor_data)
        self.node.create_subscription(SysStatus, '/mavros/sys_status', self.sys_status,
                                      qos_profile_sensor_data)
        self.start()
        for cycle in range(self.args.cycles):
            fixture = self.directory / f'battery-cycle-{cycle + 1}.yaml'
            fixture.write_text(
                'schema_version: 1\nframe_id: odom\n'
                'units: {position: m, angle: rad, time: s}\nfailure_policy: abort\nsteps:\n'
                '  - {type: takeoff, altitude: 1.5, climb_speed: 0.3, timeout: 75}\n'
                '  - {type: hover, duration: 20, timeout: 30}\n'
                '  - {type: land, timeout: 90}\n')
            action = self.send('/execute_mission', ExecuteMission,
                               ExecuteMission.Goal(mission_file=str(fixture)))
            self.finish(action, seconds=210)
            self.wait(lambda: self.ready(False), 15)
            self.report['cycles_completed'] = cycle + 1
            self.report['final_disarmed_state'] = self.state()
        if 'battery_failure_threads' in self.report:
            raise RuntimeError('armed battery validity loss observed; inspect original evidence')


def main():
    """Require new evidence, local simulation ports and an explicitly bounded cycle count."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--px4-dir', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--domain', required=True, type=int)
    parser.add_argument('--gazebo-port', required=True, type=int)
    parser.add_argument('--cycles', type=int, choices=(1, 2, 3), default=1)
    parser.add_argument('--semantic-capture-shutdown', action='store_true',
                        help='Opt-in semantic-only stack capture; diagnostic, not normal timing.')
    args = parser.parse_args()
    if not 0 <= args.domain <= 232 or not 1024 <= args.gazebo_port <= 65535:
        parser.error('invalid explicit domain or local port')
    args.strategy, args.scenario = 'combined', 'battery-cycles'
    probe = BatteryProbe(args)
    try:
        probe.run()
    except (Exception, KeyboardInterrupt) as error:
        probe.report['error'] = type(error).__name__ + ': ' + str(error)
        print(probe.report['error'], flush=True)
    finally:
        probe.close()
    print(json.dumps({'passed': probe.report['passed'],
                      'result': str(probe.directory / 'result.json')}), flush=True)
    raise SystemExit(0 if probe.report['passed'] else 1)


if __name__ == '__main__':
    main()
