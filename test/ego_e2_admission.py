"""Pure, ROS-free admission rules for the G8 E2 clearance measurement.

The dynamic acceptance test must never turn a stale or cross-clock sample into
evidence of safe clearance.  Keeping these rules independent of rclpy makes
the negative cases executable in a plain pytest environment as well as in the
ROS acceptance script.
"""

import math


E2_REQUIRED_FRAME = "odom"
# These are deliberately explicit acceptance limits.  Message age is measured
# in the node ROS clock; arrival age is measured in process monotonic time.
E2_MAX_MESSAGE_AGE_S = 1.0
E2_FUTURE_TOLERANCE_S = 0.2
E2_MAX_ARRIVAL_AGE_S = 1.5
# E3/E4 use a synchronized state/obstacle snapshot, not merely two samples
# that happen to be fresh.  ROS stamps are compared in their common ROS clock
# domain; process-monotonic arrivals are compared separately so sim time is
# supported without converting it to wall time.
E2_MAX_PAIR_STAMP_S = 0.5
E2_MAX_PAIR_ARRIVAL_S = 0.5


def _finite(value):
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _stamp_nonzero(diag):
    if not bool(diag.get("stamp_valid", False)):
        return False
    try:
        sec = int(diag.get("stamp_sec"))
        nanosec = int(diag.get("stamp_nanosec"))
    except (TypeError, ValueError, OverflowError):
        return False
    return sec > 0 or nanosec > 0


def _stamp_seconds(diag):
    if not isinstance(diag, dict) or not _stamp_nonzero(diag):
        return None
    try:
        sec = float(diag.get("stamp_sec"))
        nanosec = float(diag.get("stamp_nanosec"))
    except (TypeError, ValueError, OverflowError):
        return None
    if (not math.isfinite(sec) or not math.isfinite(nanosec) or
            nanosec < 0.0 or nanosec >= 1e9):
        return None
    value = sec + nanosec * 1e-9
    return value if math.isfinite(value) and value > 0.0 else None


def _safe_pair_limit(value, fallback):
    # A caller may tighten the contract, but malformed or unreasonably loose
    # limits fail closed to the documented conservative default.
    return (float(value) if _finite(value) and 0.0 < float(value) <= 5.0
            else fallback)


def _append_unique(reasons, reason):
    if reason not in reasons:
        reasons.append(reason)


def _current_message_age(diag, now_ros_ns):
    """Recompute ROS age at admission time, never from callback-time cache."""
    if _finite(now_ros_ns):
        stamp = _stamp_seconds(diag)
        if stamp is not None:
            try:
                return float(now_ros_ns) * 1e-9 - stamp
            except (TypeError, ValueError, OverflowError):
                return float("nan")
    return diag.get("age", float("nan")) if isinstance(diag, dict) else float("nan")


def _check_message(diag, prefix, now_mono, expected_frame, now_ros_ns=None):
    reasons = []
    if not isinstance(diag, dict):
        return [prefix + "_missing"]

    if not _stamp_nonzero(diag):
        _append_unique(reasons, prefix + "_timestamp_invalid")
    else:
        age = _current_message_age(diag, now_ros_ns)
        if not _finite(age):
            _append_unique(reasons, prefix + "_timestamp_invalid")
        elif float(age) < -E2_FUTURE_TOLERANCE_S:
            _append_unique(reasons, prefix + "_future")
        elif float(age) > E2_MAX_MESSAGE_AGE_S:
            _append_unique(reasons, prefix + "_stale")

    arrival = diag.get("arrival_mono")
    if not _finite(arrival) or not _finite(now_mono):
        _append_unique(reasons, prefix + "_arrival_invalid")
    else:
        arrival_age = float(now_mono) - float(arrival)
        if arrival_age < 0.0:
            _append_unique(reasons, prefix + "_arrival_future")
        elif arrival_age > E2_MAX_ARRIVAL_AGE_S:
            _append_unique(reasons, prefix + "_arrival_stale")

    if bool(diag.get("clock_mismatch", False)) or diag.get("clock_error"):
        _append_unique(reasons, "clock_mismatch")

    frame = str(diag.get("frame_id", "") or "")
    if frame != expected_frame:
        _append_unique(reasons, "frame_mismatch")

    clock_type = str(diag.get("clock_type", "") or "")
    if not clock_type or clock_type == "unknown":
        _append_unique(reasons, "clock_mismatch")
    if not _finite(diag.get("node_ros_ns")):
        _append_unique(reasons, "clock_mismatch")

    return reasons


def admit_e2_pair(state_fields, state_diag, obstacles_diag, now_mono,
                  expected_frame=E2_REQUIRED_FRAME,
                  max_pair_stamp_s=E2_MAX_PAIR_STAMP_S,
                  max_pair_arrival_s=E2_MAX_PAIR_ARRIVAL_S,
                  now_ros_ns=None):
    """Return ``(accepted, reason_codes)`` for one state/obstacle pair.

    ``state_fields`` is a small dict extracted from ``UAVState`` so callers and
    tests do not need to construct ROS messages.  Both messages must have a
    nonzero timestamp in the same clock domain, satisfy message and arrival
    freshness limits, and be synchronized with each other by both ROS stamp
    and monotonic arrival time.  UAV state must additionally be connected and
    have a valid finite pose.
    """
    reasons = []
    max_pair_stamp_s = _safe_pair_limit(
        max_pair_stamp_s, E2_MAX_PAIR_STAMP_S)
    max_pair_arrival_s = _safe_pair_limit(
        max_pair_arrival_s, E2_MAX_PAIR_ARRIVAL_S)
    if not isinstance(state_fields, dict):
        reasons.append("state_missing")
    else:
        if state_fields.get("connected") is not True:
            reasons.append("state_disconnected")
        if state_fields.get("pose_valid") is not True:
            reasons.append("state_pose_invalid")
        pose = (state_fields.get("position_x"),
                state_fields.get("position_y"),
                state_fields.get("position_z"))
        if not all(_finite(value) for value in pose):
            reasons.append("state_nonfinite")

    for reason in _check_message(state_diag, "state", now_mono,
                                 expected_frame, now_ros_ns):
        _append_unique(reasons, reason)
    for reason in _check_message(obstacles_diag, "obstacles", now_mono,
                                 expected_frame, now_ros_ns):
        _append_unique(reasons, reason)

    if isinstance(state_diag, dict) and isinstance(obstacles_diag, dict):
        state_clock = str(state_diag.get("clock_type", "") or "")
        obstacles_clock = str(obstacles_diag.get("clock_type", "") or "")
        if (not state_clock or state_clock == "unknown" or
                not obstacles_clock or obstacles_clock == "unknown" or
                state_clock != obstacles_clock):
            _append_unique(reasons, "clock_mismatch")
        state_stamp = _stamp_seconds(state_diag)
        obstacles_stamp = _stamp_seconds(obstacles_diag)
        if state_stamp is not None and obstacles_stamp is not None:
            if abs(state_stamp - obstacles_stamp) > max_pair_stamp_s:
                _append_unique(reasons, "pair_stamp_unsynchronized")

        state_arrival = state_diag.get("arrival_mono")
        obstacles_arrival = obstacles_diag.get("arrival_mono")
        if (_finite(state_arrival) and _finite(obstacles_arrival) and
                abs(float(state_arrival) - float(obstacles_arrival)) >
                max_pair_arrival_s):
            _append_unique(reasons, "pair_arrival_unsynchronized")

    return not reasons, tuple(reasons)
