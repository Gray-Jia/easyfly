#!/usr/bin/env python3
"""Repeatable manual G4-style OFFBOARD hover check; run with PX4/Gazebo/MAVROS up."""

import argparse
import json
import math
import time

import rclpy
from geometry_msgs.msg import PoseStamped
from mavros_msgs.msg import ExtendedState, RCOut, State
from mavros_msgs.srv import CommandBool, SetMode
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy


class FlightCheck(Node):
    def __init__(self, hover_seconds):
        super().__init__("easyfly_v2_10_flight_check")
        self.hover_seconds = hover_seconds
        self.publisher = self.create_publisher(
            PoseStamped, "/mavros/setpoint_position/local", 10
        )
        self.create_subscription(State, "/mavros/state", self._on_state, 10)
        self.create_subscription(
            ExtendedState, "/mavros/extended_state", self._on_extended_state, 10
        )
        pose_qos = QoSProfile(
            depth=10, reliability=QoSReliabilityPolicy.BEST_EFFORT
        )
        self.create_subscription(
            PoseStamped, "/mavros/local_position/pose", self._on_pose, pose_qos
        )
        self.create_subscription(RCOut, "/mavros/rc/out", self._on_rc, 10)
        self.mode_client = self.create_client(SetMode, "/mavros/set_mode")
        self.arm_client = self.create_client(CommandBool, "/mavros/cmd/arming")
        self.state = None
        self.extended_state = None
        self.pose = None
        self.rc_outputs = []
        self.target_z = 1.5
        self.phase = "preflight"
        self.start = time.monotonic()
        self.last_publish = 0.0
        self.send_setpoints = True
        self.last_sample = 0.0
        self.last_mode = None
        self.last_armed = None
        self.transitions = []
        self.unsafe_count = 0
        self.abort_reason = None
        self.extrema = {
            key: [float("inf"), float("-inf")]
            for key in ("x", "y", "z", "roll_deg", "pitch_deg", "yaw_deg")
        }

    @staticmethod
    def _pose_values(msg):
        p, q = msg.pose.position, msg.pose.orientation
        roll = math.degrees(
            math.atan2(2 * (q.w * q.x + q.y * q.z), 1 - 2 * (q.x**2 + q.y**2))
        )
        sin_pitch = 2 * (q.w * q.y - q.z * q.x)
        pitch = math.degrees(
            math.copysign(math.pi / 2, sin_pitch)
            if abs(sin_pitch) >= 1
            else math.asin(sin_pitch)
        )
        yaw = math.degrees(
            math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y**2 + q.z**2))
        )
        return {
            "x": p.x,
            "y": p.y,
            "z": p.z,
            "roll_deg": roll,
            "pitch_deg": pitch,
            "yaw_deg": yaw,
        }

    def _on_state(self, msg):
        self.state = msg
        if msg.mode != self.last_mode or msg.armed != self.last_armed:
            self.transitions.append(
                {
                    "t_s": round(time.monotonic() - self.start, 2),
                    "phase": self.phase,
                    "mode": msg.mode,
                    "armed": msg.armed,
                    "connected": msg.connected,
                }
            )
            self.last_mode, self.last_armed = msg.mode, msg.armed

    def _on_extended_state(self, msg):
        self.extended_state = msg

    def _on_pose(self, msg):
        self.pose = msg
        values = self._pose_values(msg)
        if self.phase != "hover":
            return
        for key, value in values.items():
            self.extrema[key][0] = min(self.extrema[key][0], value)
            self.extrema[key][1] = max(self.extrema[key][1], value)
        unsafe = (
            abs(values["roll_deg"]) > 50
            or abs(values["pitch_deg"]) > 50
            or abs(values["x"]) > 3
            or abs(values["y"]) > 3
            or values["z"] < -0.8
        )
        self.unsafe_count = self.unsafe_count + 1 if unsafe else 0
        if self.unsafe_count >= 10 and self.abort_reason is None:
            self.abort_reason = {
                key: round(value, 3) for key, value in values.items()
            }

    def _on_rc(self, msg):
        self.rc_outputs = list(msg.channels)

    def _publish_setpoint(self):
        msg = PoseStamped()
        msg.pose.position.z = self.target_z
        msg.pose.orientation.w = 1.0
        self.publisher.publish(msg)

    def _step(self):
        now = time.monotonic()
        if self.send_setpoints and now - self.last_publish >= 0.05:
            self._publish_setpoint()
            self.last_publish = now
        rclpy.spin_once(self, timeout_sec=0.005)
        now = time.monotonic()
        if now - self.last_sample >= 1.0:
            self._sample(now)
            self.last_sample = now

    def _sample(self, now):
        if self.pose is None:
            return
        values = self._pose_values(self.pose)
        state = self.state
        print(
            "SAMPLE "
            + json.dumps(
                {
                    "phase": self.phase,
                    "t_s": round(now - self.start, 1),
                    "mode": state.mode if state else None,
                    "armed": state.armed if state else None,
                    "xyz": [round(values[key], 3) for key in ("x", "y", "z")],
                    "rpy_deg": [
                        round(values[key], 2)
                        for key in ("roll_deg", "pitch_deg", "yaw_deg")
                    ],
                    "rc_out": self.rc_outputs[:4],
                },
                separators=(",", ":"),
            ),
            flush=True,
        )

    def _pump(self, duration, stop_if_unsafe=False):
        start = time.monotonic()
        while time.monotonic() - start < duration and rclpy.ok():
            self._step()
            if stop_if_unsafe and self.abort_reason:
                return False
        return True

    def _call(self, client, request, name, timeout=12.0):
        if not client.wait_for_service(timeout_sec=timeout):
            raise RuntimeError(f"service unavailable: {name}")
        future = client.call_async(request)
        deadline = time.monotonic() + timeout
        while not future.done() and time.monotonic() < deadline and rclpy.ok():
            self._step()
        if not future.done():
            raise RuntimeError(f"service timeout: {name}")
        return future.result()

    def _set_mode(self, mode):
        request = SetMode.Request()
        request.base_mode = 0
        request.custom_mode = mode
        return self._call(self.mode_client, request, "/mavros/set_mode")

    def _arm(self, value):
        request = CommandBool.Request()
        request.value = value
        return self._call(self.arm_client, request, "/mavros/cmd/arming")

    def run(self):
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline and rclpy.ok():
            self._step()
            if self.state and self.state.connected and self.pose:
                break
        if not self.state or not self.state.connected or not self.pose:
            raise RuntimeError("MAVROS FCU or local pose not ready")
        p = self.pose.pose.position
        print(
            "PRECHECK "
            + json.dumps(
                {
                    "connected": self.state.connected,
                    "armed": self.state.armed,
                    "mode": self.state.mode,
                    "xyz": [round(p.x, 3), round(p.y, 3), round(p.z, 3)],
                },
                separators=(",", ":"),
            ),
            flush=True,
        )

        # Allow the SITL EKF and power/arming checks to finish startup before
        # requesting OFFBOARD or arming. The previous attempt raced this and
        # PX4 rejected the arm command while reporting missing health data.
        self._pump(10.0)
        print(
            "PREFLIGHT_SETTLED "
            + json.dumps(
                {
                    "mode": self.state.mode if self.state else None,
                    "armed": self.state.armed if self.state else None,
                    "connected": self.state.connected if self.state else None,
                },
                separators=(",", ":"),
            ),
            flush=True,
        )

        self.phase = "prestream"
        self._pump(4)
        mode_result = self._set_mode("OFFBOARD")
        self._pump(2)
        if not mode_result.mode_sent or self.state.mode != "OFFBOARD":
            raise RuntimeError(f"PX4 did not enter OFFBOARD: {self.state.mode}")
        arm_result = None
        for attempt in range(1, 4):
            arm_result = self._arm(True)
            self._pump(2)
            print(
                "ARM_REPLY "
                + json.dumps(
                    {
                        "attempt": attempt,
                        "success": arm_result.success,
                        "result": arm_result.result,
                        "armed": self.state.armed if self.state else None,
                    },
                    separators=(",", ":"),
                ),
                flush=True,
            )
            if arm_result.success and self.state and self.state.armed:
                break
            if attempt < 3:
                self._pump(3.0)
        if not arm_result or not arm_result.success or not self.state.armed:
            # The vehicle is still disarmed, so leave OFFBOARD cleanly rather
            # than stopping the setpoint stream while the mode is active.
            self._set_mode("AUTO.LOITER")
            self._pump(1.0)
            self.send_setpoints = False
            raise RuntimeError("PX4 did not arm after preflight retries")

        self.phase = "hover"
        hover_start = time.monotonic()
        stable = self._pump(self.hover_seconds, stop_if_unsafe=True)
        print(
            "HOVER_END "
            + json.dumps(
                {
                    "duration_s": round(time.monotonic() - hover_start, 2),
                    "stable_window_completed": stable,
                    "abort_pose": self.abort_reason,
                    "extrema": {
                        key: [round(lo, 3), round(hi, 3)]
                        if math.isfinite(lo)
                        else None
                        for key, (lo, hi) in self.extrema.items()
                    },
                    "mode": self.state.mode,
                    "armed": self.state.armed,
                    "rc_out": self.rc_outputs[:4],
                },
                separators=(",", ":"),
            ),
            flush=True,
        )
        if not stable:
            return False

        self.phase = "landing"
        land_start = time.monotonic()
        land_mode = self._set_mode("AUTO.LAND")
        mode_deadline = time.monotonic() + 5.0
        while (
            time.monotonic() < mode_deadline
            and rclpy.ok()
            and self.state
            and self.state.mode != "AUTO.LAND"
        ):
            self._step()
        landed_mode = bool(
            land_mode.mode_sent and self.state and self.state.mode == "AUTO.LAND"
        )
        print(
            "LAND_MODE "
            + json.dumps(
                {
                    "mode_sent": land_mode.mode_sent,
                    "mode": self.state.mode if self.state else None,
                    "accepted": landed_mode,
                },
                separators=(",", ":"),
            ),
            flush=True,
        )
        if landed_mode:
            # Stop the OFFBOARD stream only after PX4 has accepted the native
            # landing mode, avoiding an unintended OFFBOARD-loss failsafe.
            self.send_setpoints = False
            landed_by = time.monotonic() + 45
            while time.monotonic() < landed_by and rclpy.ok():
                self._step()
                if (
                    self.state
                    and not self.state.armed
                    and self.extended_state
                    and self.extended_state.landed_state
                    == ExtendedState.LANDED_STATE_ON_GROUND
                ):
                    break
        else:
            # If AUTO.LAND is rejected, keep control in OFFBOARD and descend to
            # ground rather than dropping the setpoint stream in the air.
            self.target_z = 0.0
            landed_by = time.monotonic() + 20
            while time.monotonic() < landed_by and rclpy.ok():
                self._step()
                if self.state and not self.state.armed:
                    break
            if self.state and self.state.armed:
                # Re-request the native landing task before the runner exits.
                # Do not issue a blind disarm command while PX4 may be airborne.
                self._set_mode("AUTO.LAND")
                self._pump(2.0)
                if self.state and self.state.mode == "AUTO.LAND":
                    self.send_setpoints = False
                    landed_by = time.monotonic() + 45
                    while landed_by > time.monotonic() and rclpy.ok():
                        self._step()
                        if (
                            self.state
                            and not self.state.armed
                            and self.extended_state
                            and self.extended_state.landed_state
                            == ExtendedState.LANDED_STATE_ON_GROUND
                        ):
                            break
        print(
            "LAND_END "
            + json.dumps(
                {
                    "duration_s": round(time.monotonic() - land_start, 2),
                    "mode": self.state.mode if self.state else None,
                    "armed": self.state.armed if self.state else None,
                    "landed_state": self.extended_state.landed_state
                    if self.extended_state
                    else None,
                    "xyz": [
                        round(self.pose.pose.position.x, 3),
                        round(self.pose.pose.position.y, 3),
                        round(self.pose.pose.position.z, 3),
                    ]
                    if self.pose
                    else None,
                },
                separators=(",", ":"),
            ),
            flush=True,
        )
        print(
            "FINAL "
            + json.dumps(
                {
                    "mode": self.state.mode if self.state else None,
                    "armed": self.state.armed if self.state else None,
                    "transitions": self.transitions,
                    "landed_state": self.extended_state.landed_state
                    if self.extended_state
                    else None,
                    "rc_out": self.rc_outputs[:4],
                },
                separators=(",", ":"),
            ),
            flush=True,
        )
        return bool(
            self.state
            and not self.state.armed
            and self.extended_state
            and self.extended_state.landed_state == ExtendedState.LANDED_STATE_ON_GROUND
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hover-seconds", type=float, default=44.0)
    args = parser.parse_args()
    rclpy.init()
    node = FlightCheck(args.hover_seconds)
    try:
        passed = node.run()
        return 0 if passed else 2
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
