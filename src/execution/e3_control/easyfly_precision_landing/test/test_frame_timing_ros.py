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

"""Controlled upstream/downstream delivery delay; no flight or simulator."""

import json
import math
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time

from ament_index_python.packages import get_package_prefix
from easyfly_msgs.msg import LandingGuidanceTarget, LandingTarget, UAVState
from easyfly_msgs.srv import GetCapabilities
from easyfly_precision_landing.simulation_setup import freeze_fastdds
import pytest
import rclpy
from rosgraph_msgs.msg import Clock


def trace_snapshots(path):
    """Retain raw bounded snapshots, including absent/unknown timing fields."""
    snapshots = [
        json.loads(line.split("landing_diag ", 1)[1])
        for line in path.read_text().splitlines()
        if "landing_diag " in line
    ]
    events = []
    unique = set()
    for snapshot in snapshots:
        for event in snapshot.get("events", []):
            identity = (event["stage"], event["source_ns"], event["steady_s"])
            if identity not in unique:
                unique.add(identity)
                events.append(event)
    return snapshots, events


@pytest.mark.parametrize("experiment", ["upstream_batches", "collector_delay"])
def test_frame_stage_timing_separates_delivery_from_processing(
    experiment, monkeypatch
):
    """Keep the original two timing experiments as explicit regression cases."""
    run_frame_experiment(experiment, monkeypatch)


def run_frame_experiment(
    experiment,
    monkeypatch,
    *,
    reader_depth=100,
    diagnostics=True,
    pause_duration=0.25,
    freeze_profile=False,
    publication_limit_s=0.05,
    expect_no_reset=True,
):
    """Correlate original source with native, pair, publication and downstream time."""
    monkeypatch.setenv("ROS_DOMAIN_ID", "207")
    workspace = Path(__file__).resolve().parents[5]
    artifacts = workspace / "artifacts/d5-frame-timing-20261006"
    artifacts.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix=experiment + "-", dir=artifacts))
    report = {
        "experiment": experiment,
        "diagnostics": diagnostics,
        "reader_depth": reader_depth,
        "pause_duration_s": pause_duration,
        "inputs": [],
        "outputs": [],
        "producer_errors": [],
    }
    if freeze_profile:
        profile = freeze_fastdds(
            Path(__file__).resolve().parents[1] / "config/d5_fastdds.xml",
            directory / "fastdds.xml",
        )
        report["profile"] = profile
        for key, value in profile["env"].items():
            monkeypatch.setenv(key, value)
    rclpy.init()
    peer = rclpy.create_node("frame_trace_peer_" + experiment)
    targets = peer.create_publisher(LandingTarget, "/landing_target", 1)
    states = peer.create_publisher(UAVState, "/uav_state", 10)
    clocks = peer.create_publisher(Clock, "/clock", 10)
    capabilities = peer.create_client(
        GetCapabilities, "/platform/precision_observation/capabilities"
    )
    origin = time.monotonic()
    base = 100000000000
    current_clock = [base]

    def received(message):
        arrival = time.monotonic()
        source = (
            message.header.stamp.sec * 1000000000
            + message.header.stamp.nanosec
        )
        report["outputs"].append(
            {
                "source_ns": source,
                "valid": message.valid,
                "reason": message.reason,
                "arrival_steady_s": arrival,
                "clock_ns": current_clock[0],
                "ros_age_s": (current_clock[0] - source) * 1e-9
                if source
                else None,
            }
        )

    subscriber = peer.create_subscription(
        LandingGuidanceTarget,
        "/landing/guidance_target",
        received,
        reader_depth,
    )
    report["reader_qos"] = {
        "depth": subscriber.qos_profile.depth,
        "reliability": subscriber.qos_profile.reliability.name,
        "durability": subscriber.qos_profile.durability.name,
    }
    log_path = directory / "node.log"
    log = log_path.open("w")
    root = math.sqrt(0.5)
    binary = (
        get_package_prefix("easyfly_precision_landing")
        + "/lib/easyfly_precision_landing/landing_transform_node"
    )
    process = subprocess.Popen(
        [
            binary,
            "--ros-args",
            "-r",
            "__node:=frame_trace_transform_" + experiment,
            "-p",
            "use_sim_time:=true",
            "-p",
            "configured:=true",
            "-p",
            "diagnostics:=" + str(diagnostics).lower(),
            "-p",
            "selected_tag_id:=7",
            "-p",
            "tag_size_m:=0.2",
            "-p",
            "landing_plane_z_m:=0.0",
            "-p",
            f"camera_quaternion_xyzw:=[{root}, {-root}, 0.0, 0.0]",
        ],
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    stopped = threading.Event()
    feeder = None

    def publish_target(source, scheduled):
        message = LandingTarget(
            tag_id=7,
            tag_size_m=0.2,
            valid=True,
            optical_depth_m=1.0,
            reprojection_error_px=0.2,
        )
        message.header.frame_id = "camera_down_optical_frame"
        message.header.stamp.sec, message.header.stamp.nanosec = divmod(
            source, 1000000000
        )
        message.pose.position.z = message.pose.orientation.w = 1.0
        sent = time.monotonic()
        targets.publish(message)
        report["inputs"].append(
            {
                "source_ns": source,
                "publish_steady_s": sent,
                "scheduled_s": scheduled,
                "clock_ns": current_clock[0],
                "source_age_before_delivery_s": (current_clock[0] - source)
                * 1e-9,
            }
        )

    def produce():
        next_state = next_clock = 0.0
        next_target = 0.5
        batch = []
        try:
            while not stopped.is_set():
                elapsed = time.monotonic() - origin
                continuous = base + round(elapsed * 1e9)
                if elapsed >= next_clock:
                    current_clock[0] = continuous
                    message = Clock()
                    message.clock.sec, message.clock.nanosec = divmod(
                        continuous, 1000000000
                    )
                    clocks.publish(message)
                    next_clock += 0.1
                if elapsed >= next_state:
                    message = UAVState(
                        connected=True,
                        pose_valid=True,
                        attitude_valid=True,
                        position_z=1.0,
                    )
                    message.header.frame_id = "odom"
                    (
                        message.header.stamp.sec,
                        message.header.stamp.nanosec,
                    ) = divmod(continuous, 1000000000)
                    states.publish(message)
                    next_state += 0.05
                if experiment == "collector_delay":
                    if elapsed >= next_target and elapsed <= 3.0:
                        publish_target(continuous - 20000000, elapsed)
                        next_target += 1 / 30
                else:
                    if elapsed >= next_target and next_target < 2.3:
                        anchor = base + round(next_target * 1e9)
                        batch.extend(
                            (
                                next_target + index * 0.008,
                                anchor - round(age * 1e9),
                            )
                            for index, age in enumerate((0.28, 0.21, 0.14))
                        )
                        next_target += 0.34
                    if batch and elapsed >= batch[0][0]:
                        scheduled, source = batch.pop(0)
                        publish_target(source, scheduled)
                stopped.wait(0.002)
        except Exception as error:
            report["producer_errors"].append(repr(error))

    def spin(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            assert process.poll() is None
            rclpy.spin_once(peer, timeout_sec=0.005)

    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            message = Clock()
            message.clock.sec = 100
            clocks.publish(message)
            spin(0.02)
            if (
                targets.get_subscription_count()
                and states.get_subscription_count()
                and clocks.get_subscription_count()
                and capabilities.service_is_ready()
            ):
                break
        assert (
            targets.get_subscription_count()
            and states.get_subscription_count()
        )
        # Start a continuous publisher independently of the downstream executor.
        origin = time.monotonic()
        feeder = threading.Thread(target=produce, daemon=True)
        feeder.start()
        spin(1.0)
        assert any(m["valid"] for m in report["outputs"])
        if experiment == "collector_delay":
            report["pause_start_steady_s"] = time.monotonic()
            time.sleep(
                pause_duration
            )  # ONLY the collector pauses; source and transform continue.
            report["pause_end_steady_s"] = time.monotonic()
        spin(max(0.0, 4.1 - (time.monotonic() - origin)))
        assert not report["producer_errors"]
        if experiment == "upstream_batches":
            transitions = []
            for message in report["outputs"]:
                if not transitions or transitions[-1] != message["valid"]:
                    transitions.append(message["valid"])
            report["validity_transitions"] = transitions
            assert sum(transitions) >= 3 and transitions.count(False) >= 3
            assert any(
                m["reason"] == "expired_or_clock_invalid"
                for m in report["outputs"]
            )
    except Exception as error:
        report["error"] = repr(error)
        raise
    finally:
        stopped.set()
        if feeder is not None:
            feeder.join(timeout=2.0)
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
        forced = False
        try:
            process.wait(timeout=4.0)
        except subprocess.TimeoutExpired:
            forced = True
            process.kill()
            process.wait(timeout=3.0)
        log.close()
        snapshots, events = trace_snapshots(log_path)
        report["snapshots"] = snapshots
        report["events"] = events
        report["exit"] = process.returncode
        report["forced"] = forced
        (directory / "evidence.json").write_text(json.dumps(report, indent=2))
        print("frame_timing_evidence " + str(directory), flush=True)
        peer.destroy_node()
        rclpy.shutdown()
        assert not forced and process.returncode == 0
    # Validate the exact event schema after cleanup so failure evidence persists.
    if not diagnostics:
        assert not snapshots and not events
        original = {sample["source_ns"]: sample for sample in report["inputs"]}
        report["analysis"] = {
            "internal_stages": None,
            "observer_from_input_delivery_ms": [
                (
                    sample["arrival_steady_s"]
                    - original[sample["source_ns"]]["publish_steady_s"]
                )
                * 1000
                for sample in report["outputs"]
                if sample["valid"]
            ],
        }
        assert len(report["analysis"]["observer_from_input_delivery_ms"]) >= 50
        if reader_depth >= 10:
            assert (
                max(report["analysis"]["observer_from_input_delivery_ms"])
                >= 150
            )
        (directory / "evidence.json").write_text(json.dumps(report, indent=2))
        return report
    assert events, "built production trace schema is required"
    assert all(len(snapshot["events"]) <= 256 for snapshot in snapshots)
    if expect_no_reset:
        assert all(
            snapshot["reset_count"] == 0 for snapshot in snapshots
        ), "no processing blackout is part of these experiments"
    assert all(
        isinstance(snapshot["dropped_events"], int)
        and snapshot["dropped_events"] >= 0
        for snapshot in snapshots
    )
    assert [snapshot["dropped_events"] for snapshot in snapshots] == sorted(
        snapshot["dropped_events"] for snapshot in snapshots
    )
    completed = []
    for output in report["outputs"]:
        if not output["valid"]:
            continue
        source = output["source_ns"]
        associated = [
            event
            for event in events
            if event["source_ns"] == source
            and (
                event["stage"] != "native_take"
                or event.get("topic") == "/landing_target"
            )
            and (
                event["stage"] not in ("publish_start", "publish_end")
                or event.get("valid") is True
            )
            and (
                event["stage"] != "publish_end"
                or event.get("succeeded") is True
            )
        ]
        relevant = {
            "native_take",
            "target_entry",
            "pair_selected",
            "publish_start",
            "publish_end",
        }
        stages = {}
        for event in associated:
            if event["stage"] in relevant:
                assert (
                    event["stage"] not in stages
                ), "ambiguous repeated stage for unique source"
                stages[event["stage"]] = event
        if (
            not {
                "native_take",
                "target_entry",
                "pair_selected",
                "publish_start",
                "publish_end",
            }
            <= stages.keys()
        ):
            continue
        assert (
            stages["native_take"]["steady_s"]
            <= stages["target_entry"]["steady_s"]
            <= stages["pair_selected"]["steady_s"]
        )
        assert (
            stages["pair_selected"]["steady_s"]
            <= stages["publish_start"]["steady_s"]
            <= stages["publish_end"]["steady_s"]
        )
        assert (
            stages["publish_start"]["steady_s"] <= output["arrival_steady_s"]
        )
        assert (
            stages["pair_selected"]["first_receipt_steady_s"]
            == stages["target_entry"]["receipt_steady_s"]
        )
        assert 0 <= stages["pair_selected"]["wait_s"] <= 0.3
        assert 0 <= stages["pair_selected"]["pair_gap_s"] <= 0.1
        publication = (
            stages["publish_end"]["steady_s"]
            - stages["publish_start"]["steady_s"]
        )
        assert publication >= 0
        if publication_limit_s is not None:
            assert publication < publication_limit_s
        completed.append((output, stages))
    assert (
        len(completed) >= 3
    ), "need complete source-correlated event chains, not aggregate maxima"
    if experiment == "upstream_batches":
        measured_native = [
            stages["native_take"]["receive_to_take_ms"]
            for _, stages in completed
            if stages["native_take"]["receive_to_take_ms"] is not None
        ]
        assert (
            measured_native
        ), "native queue timing unknown, cannot attribute delivery delay"
        assert all(0 <= value < 50 for value in measured_native)
        assert any(
            (stages["target_entry"]["clock_ns"] - output["source_ns"]) * 1e-9
            >= 0.1
            for output, stages in completed
        )
        assert all(
            stages["publish_end"]["steady_s"]
            - stages["target_entry"]["steady_s"]
            < 0.1
            for _, stages in completed
        )
    elif reader_depth >= 10:
        delayed = [
            (output, stages)
            for output, stages in completed
            if stages["publish_end"]["steady_s"] < report["pause_end_steady_s"]
            and output["arrival_steady_s"] >= report["pause_end_steady_s"]
        ]
        assert any(
            output["arrival_steady_s"] - stages["publish_end"]["steady_s"]
            >= 0.15
            and output["ros_age_s"]
            - (stages["publish_start"]["clock_ns"] - output["source_ns"])
            * 1e-9
            >= 0.1
            for output, stages in delayed
        ), "collector age must be distinguished from transform publication age"
    report["analysis"] = {
        "complete_chains": len(completed),
        "dropped_events": snapshots[-1]["dropped_events"],
        "samples": [
            {
                "source_ns": output["source_ns"],
                "native_receive_to_take_ms": stages["native_take"][
                    "receive_to_take_ms"
                ],
                "entry_source_age_s": (
                    stages["target_entry"]["clock_ns"] - output["source_ns"]
                )
                * 1e-9,
                "pair_wait_s": stages["pair_selected"]["wait_s"],
                "native_transport_ms": stages["native_take"]["transport_ms"],
                "take_to_entry_ms": (
                    stages["target_entry"]["steady_s"]
                    - stages["native_take"]["steady_s"]
                )
                * 1000,
                "paired_state_source_ns": stages["pair_selected"][
                    "state_source_ns"
                ],
                "paired_state_receipt_steady_s": stages["pair_selected"][
                    "state_receipt_steady_s"
                ],
                "first_receipt_steady_s": stages["pair_selected"][
                    "first_receipt_steady_s"
                ],
                "publication_ms": (
                    stages["publish_end"]["steady_s"]
                    - stages["publish_start"]["steady_s"]
                )
                * 1000,
                "transform_publish_source_age_s": (
                    stages["publish_start"]["clock_ns"] - output["source_ns"]
                )
                * 1e-9,
                "observer_source_age_s": output["ros_age_s"],
                "consumer_after_publish_ms": (
                    output["arrival_steady_s"]
                    - stages["publish_end"]["steady_s"]
                )
                * 1000,
            }
            for output, stages in completed
        ],
    }
    (directory / "evidence.json").write_text(json.dumps(report, indent=2))
    print(
        "frame_timing_analysis "
        + json.dumps(
            {
                "complete_chains": len(completed),
                "dropped_events": report["analysis"]["dropped_events"],
            }
        ),
        flush=True,
    )
    return report
