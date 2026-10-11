# Copyright 2026 EasyFly Project
#
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

"""Real DDS burst/reader stall tests; no flight, simulator or image publishers."""

import json
import math
from pathlib import Path
import signal
import subprocess
import sys
import time

from easyfly_msgs.msg import LandingGuidanceTarget, LandingTarget, UAVState
from easyfly_msgs.srv import GetCapabilities
import pytest
import rclpy
from std_msgs.msg import Float64, String
from rosgraph_msgs.msg import Clock


@pytest.mark.parametrize("diagnostics", [False, True])
@pytest.mark.parametrize("count,delay,slow_clock", [
    (1, 0.45, False), (8, 0.18, False), (1, 0.45, True),
])
def test_reader_queue_age_and_burst(count, delay, slow_clock, diagnostics, tmp_path):
    """Separate real queue delay from transport and reject expired sources."""
    rclpy.init()
    fixture = rclpy.create_node(f"timing_queue_{count}")
    targets = fixture.create_publisher(LandingTarget, "/landing_target", 10)
    states = fixture.create_publisher(UAVState, "/uav_state", 10)
    clock_pub = fixture.create_publisher(Clock, "/clock", 10)
    capability = fixture.create_client(
        GetCapabilities, "/platform/precision_observation/capabilities"
    )
    origin = time.monotonic()

    def simulated_now():
        return 10000000000 + int((time.monotonic() - origin) * 0.1 * 1000000000)
    blocker = fixture.create_publisher(Float64, "/timing/block", 1)
    markers, outputs = [], []
    fixture.create_subscription(String, "/timing/block_state", markers.append, 10)
    fixture.create_subscription(
        LandingGuidanceTarget, "/landing/guidance_target", outputs.append, 10
    )
    stream = (tmp_path / "node.log").open("w")
    root = math.sqrt(0.5)
    process = subprocess.Popen([
        sys.executable, str(Path(__file__).with_name("timing_queue_fixture.py")),
        "--ros-args", "-r", f"__node:=timing_reader_{count}",
        "-p", "configured:=true", "-p", "diagnostics:=" + str(diagnostics).lower(),
        "-p", "use_sim_time:=" + str(slow_clock).lower(),
        "-p", "selected_tag_id:=7", "-p", "tag_size_m:=0.2",
        "-p", "landing_plane_z_m:=0.0",
        "-p", f"camera_quaternion_xyzw:=[{root}, {-root}, 0.0, 0.0]",
    ], stdout=stream, stderr=subprocess.STDOUT)
    inputs, publish_times, readiness_sources = [], [], []
    baseline_confirmed = []
    readiness_last_sent = [0.0]

    def pump(predicate, budget=3):
        deadline = time.monotonic() + budget
        while time.monotonic() < deadline and process.poll() is None:
            if slow_clock:
                clock = Clock()
                clock.clock.sec, clock.clock.nanosec = divmod(simulated_now(), 1000000000)
                clock_pub.publish(clock)
            rclpy.spin_once(fixture, timeout_sec=0.005)
            if predicate():
                return
        assert predicate(), "timing evidence deadline"

    def send():
        source = simulated_now() if slow_clock else fixture.get_clock().now().nanoseconds
        state = UAVState()
        state.header.frame_id = "odom"
        state.header.stamp.sec, state.header.stamp.nanosec = divmod(source, 1000000000)
        state.connected = state.pose_valid = state.attitude_valid = True
        state.position_z = 1.0
        states.publish(state)
        target = LandingTarget()
        target.header.stamp = state.header.stamp
        target.header.frame_id = "camera_down_optical_frame"
        target.tag_id, target.tag_size_m, target.valid = 7, 0.2, True
        target.pose.position.z = target.optical_depth_m = 1.0
        target.pose.orientation.w = 1.0
        started = time.monotonic()
        targets.publish(target)
        publish_times.append(time.monotonic() - started)
        return source

    try:
        pump(lambda: all(p.get_subscription_count() > 0 for p in (targets, states, blocker)))
        if slow_clock:
            # Discovery does not prove the child has consumed its first /clock.
            # Prove that precondition before sending the one-shot baseline.
            pump(capability.service_is_ready)
            request = [None]

            def clock_ready():
                if request[0] is None:
                    request[0] = capability.call_async(GetCapabilities.Request())
                if not request[0].done():
                    return False
                response = request[0].result()
                assert response is not None
                if response.header.stamp.sec >= 10:
                    return True
                request[0] = None
                return False

            pump(clock_ready)

        def baseline_ready():
            # Graph discovery is not one-shot delivery proof for a best-effort
            # reader. Establish a live fresh stream before the measured stall;
            # the fault injection below still sends exactly count samples.
            if time.monotonic() - readiness_last_sent[0] >= 0.02:
                readiness_sources.append(send())
                readiness_last_sent[0] = time.monotonic()
            return any(m.valid and m.header.stamp.sec * 1000000000
                       + m.header.stamp.nanosec in readiness_sources for m in outputs)

        pump(baseline_ready)
        baseline_confirmed = [m.header.stamp.sec * 1000000000 + m.header.stamp.nanosec
                              for m in outputs if m.valid]
        outputs.clear()
        blocker.publish(Float64(data=delay))
        pump(lambda: any(m.data == "started" for m in markers))
        inputs = [send() for _ in range(count)]
        pump(lambda: any(m.data == "finished" for m in markers))
        if count == 1:
            pump(lambda: any(not m.valid and m.reason in (
                "receiver_processing_gap", "source_invalid_or_replayed")
                             for m in outputs))
            assert not any(m.valid and m.header.stamp.sec * 1000000000
                           + m.header.stamp.nanosec in inputs for m in outputs)
        else:
            pump(lambda: any(m.valid and m.header.stamp.sec * 1000000000
                             + m.header.stamp.nanosec == inputs[-1] for m in outputs))
            valid_sources = [m.header.stamp.sec * 1000000000 + m.header.stamp.nanosec
                             for m in outputs if m.valid]
            assert valid_sources == sorted(set(valid_sources))
        fresh_sources, last_sent = [], [0.0]

        def recovered():
            # Behave like a fresh sensor stream while volatile endpoints rematch;
            # do not resend an old stamp or retry any flight action.
            if time.monotonic() - last_sent[0] >= 0.02:
                fresh_sources.append(send())
                last_sent[0] = time.monotonic()
            return any(m.valid and m.header.stamp.sec * 1000000000
                       + m.header.stamp.nanosec in fresh_sources for m in outputs)

        pump(recovered)
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
            pytest.fail("owned observation process forced termination")
        stream.close()
        log = (tmp_path / "node.log").read_text()
        traces = [json.loads(line.split("timing_take ", 1)[1])
                  for line in log.splitlines() if "timing_take " in line]
        evidence = {"count": count, "stall_s": delay, "inputs": inputs,
                    "readiness_sources": readiness_sources,
                    "baseline_confirmed_sources": baseline_confirmed,
                    "slow_clock": slow_clock,
                    "diagnostics": diagnostics,
                    "publish_wall_s": publish_times, "takes": traces,
                    "outputs": [{"stamp_ns": m.header.stamp.sec * 1000000000
                                 + m.header.stamp.nanosec, "valid": m.valid,
                                 "reason": m.reason} for m in outputs],
                    "exit": process.returncode}
        (tmp_path / "evidence.json").write_text(json.dumps(evidence, indent=2))
        print("TIMING_QUEUE_EVIDENCE " + str(tmp_path / "evidence.json"))
        print(json.dumps(evidence))
        fixture.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        assert process.returncode == 0, log
    stalled = [t for t in traces if t["source_ns"] in inputs]
    if count == 1:
        assert "receiver_processing_gap:" in log
        assert not any(m.valid and m.header.stamp.sec * 1000000000
                       + m.header.stamp.nanosec in inputs for m in outputs)
    else:
        assert [t["source_ns"] for t in stalled] == [inputs[-1]]
        assert [m.header.stamp.sec * 1000000000 + m.header.stamp.nanosec
                for m in outputs if m.valid and m.header.stamp.sec * 1000000000
                + m.header.stamp.nanosec in inputs] == [inputs[-1]]
        if diagnostics:
            assert max(t["rmw"]["receive_to_take_ms"] for t in stalled) > delay * 1000 - 80
