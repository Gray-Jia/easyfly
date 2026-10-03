"""Behavior-level tests for E2 sample admission.

These tests intentionally use plain dictionaries: the acceptance gate must
reject bad evidence before any ROS obstacle geometry is considered.
"""

try:
    from ego_e2_admission import (
        E2_FUTURE_TOLERANCE_S,
        E2_MAX_ARRIVAL_AGE_S,
        E2_MAX_MESSAGE_AGE_S,
        E2_MAX_PAIR_ARRIVAL_S,
        E2_MAX_PAIR_STAMP_S,
        admit_e2_pair,
    )
except ModuleNotFoundError:
    from test.ego_e2_admission import (
        E2_FUTURE_TOLERANCE_S,
        E2_MAX_ARRIVAL_AGE_S,
        E2_MAX_MESSAGE_AGE_S,
        E2_MAX_PAIR_ARRIVAL_S,
        E2_MAX_PAIR_STAMP_S,
        admit_e2_pair,
    )

try:
    from trajectory_admission import (
        GOAL_STATUS_ACCEPTED,
        GOAL_STATUS_EXECUTING,
        goal_command_progress,
        goal_is_active,
        is_new_goal_trajectory,
    )
except ModuleNotFoundError:
    from test.trajectory_admission import (
        GOAL_STATUS_ACCEPTED,
        GOAL_STATUS_EXECUTING,
        goal_command_progress,
        goal_is_active,
        is_new_goal_trajectory,
    )


NOW_MONO = 100.0


def _diag(*, age=0.1, arrival=NOW_MONO - 0.1, frame="odom",
          clock="ROS_TIME", stamp=(10, 1), stamp_valid=True):
    return {
        "stamp_valid": stamp_valid,
        "stamp_sec": stamp[0],
        "stamp_nanosec": stamp[1],
        "age": age,
        "arrival_mono": arrival,
        "frame_id": frame,
        "clock_type": clock,
        "clock_mismatch": False,
        "clock_error": None,
        "node_ros_ns": 10000000000,
    }


def _state(*, connected=True, pose_valid=True):
    return {
        "connected": connected,
        "pose_valid": pose_valid,
        "position_x": 1.0,
        "position_y": 2.0,
        "position_z": 1.0,
    }


def test_valid_fresh_same_clock_pair_is_admitted():
    accepted, reasons = admit_e2_pair(
        _state(), _diag(), _diag(), NOW_MONO)
    assert accepted
    assert reasons == ()


def test_stale_state_is_rejected_even_with_fresh_obstacles():
    accepted, reasons = admit_e2_pair(
        _state(), _diag(age=E2_MAX_MESSAGE_AGE_S + 0.01), _diag(), NOW_MONO)
    assert not accepted
    assert "state_stale" in reasons


def test_future_state_beyond_tolerance_is_rejected():
    accepted, reasons = admit_e2_pair(
        _state(), _diag(age=-(E2_FUTURE_TOLERANCE_S + 0.01)), _diag(),
        NOW_MONO)
    assert not accepted
    assert "state_future" in reasons


def test_future_obstacles_beyond_tolerance_are_rejected():
    accepted, reasons = admit_e2_pair(
        _state(), _diag(),
        _diag(age=-(E2_FUTURE_TOLERANCE_S + 0.01)), NOW_MONO)
    assert not accepted
    assert "obstacles_future" in reasons


def test_disconnected_state_is_rejected():
    accepted, reasons = admit_e2_pair(
        _state(connected=False), _diag(), _diag(), NOW_MONO)
    assert not accepted
    assert "state_disconnected" in reasons


def test_pose_invalid_state_is_rejected():
    accepted, reasons = admit_e2_pair(
        _state(pose_valid=False), _diag(), _diag(), NOW_MONO)
    assert not accepted
    assert "state_pose_invalid" in reasons


def test_zero_timestamp_is_rejected():
    accepted, reasons = admit_e2_pair(
        _state(), _diag(stamp=(0, 0), stamp_valid=False), _diag(), NOW_MONO)
    assert not accepted
    assert "state_timestamp_invalid" in reasons


def test_stale_arrival_is_rejected_even_when_ros_age_is_fresh():
    accepted, reasons = admit_e2_pair(
        _state(), _diag(arrival=NOW_MONO - E2_MAX_ARRIVAL_AGE_S - 0.01),
        _diag(), NOW_MONO)
    assert not accepted
    assert "state_arrival_stale" in reasons


def test_different_clock_domains_are_rejected():
    accepted, reasons = admit_e2_pair(
        _state(), _diag(clock="ROS_TIME"), _diag(clock="SYSTEM_TIME"),
        NOW_MONO)
    assert not accepted
    assert "clock_mismatch" in reasons


def test_separately_fresh_but_ros_stamps_unsynchronized_are_rejected():
    accepted, reasons = admit_e2_pair(
        _state(), _diag(stamp=(10, 0)), _diag(stamp=(10 + 1, 0)), NOW_MONO)
    assert not accepted
    assert "pair_stamp_unsynchronized" in reasons


def test_separately_fresh_but_arrivals_unsynchronized_are_rejected():
    accepted, reasons = admit_e2_pair(
        _state(), _diag(arrival=NOW_MONO - 0.1),
        _diag(arrival=NOW_MONO - 0.1 - E2_MAX_PAIR_ARRIVAL_S - 0.01),
        NOW_MONO)
    assert not accepted
    assert "pair_arrival_unsynchronized" in reasons


def test_pair_synchronization_limits_are_inclusive_and_parameterized():
    accepted, reasons = admit_e2_pair(
        _state(), _diag(stamp=(10, 0), arrival=NOW_MONO - 0.2),
        _diag(stamp=(10, int(E2_MAX_PAIR_STAMP_S * 1e9)),
              arrival=NOW_MONO - 0.2 - E2_MAX_PAIR_ARRIVAL_S),
        NOW_MONO)
    assert accepted
    assert reasons == ()


def test_emergency_stop_new_id_without_goal_progress_is_not_goal_start():
    # A stop spline can legitimately receive a fresh trajectory_id, but its
    # command remains at the stopped position and has no goal-directed motion.
    assert not is_new_goal_trajectory(
        10, 41, 11, 42, (0.0, 0.0, 1.0), (8.0, 0.0, 1.0),
        (0.0, 0.0, 1.0), (0.0, 0.0, 0.0))


def test_goal_trajectory_requires_finite_progress_and_motion():
    assert goal_command_progress(
        (0.0, 0.0, 1.0), (8.0, 0.0, 1.0), (1.0, 0.0, 1.0),
        (0.5, 0.0, 0.0))
    assert not goal_command_progress(
        (0.0, 0.0, 1.0), (8.0, 0.0, 1.0), (1.0, 0.0, 1.0),
        (0.0, 0.0, 0.0))
    assert not goal_command_progress(
        (0.0, 0.0, 1.0), (8.0, 0.0, 1.0), (float("nan"), 0.0, 1.0),
        (0.5, 0.0, 0.0))


def test_takeover_or_stream_cut_requires_goal_result_still_active():
    assert goal_is_active(True, False, None)
    assert goal_is_active(True, True, GOAL_STATUS_ACCEPTED)
    assert goal_is_active(True, True, GOAL_STATUS_EXECUTING)
    assert not goal_is_active(True, True, 4)   # SUCCEEDED
    assert not goal_is_active(True, True, 6)   # ABORTED
    assert not goal_is_active(False, False, None)
    assert not goal_is_active(True, True, None)


def test_message_age_is_recomputed_at_admission_time_after_callback_delay():
    state = _state()
    state_diag = _diag(stamp=(10, 0), age=0.01)
    obstacles_diag = _diag(stamp=(10, 0), age=0.01)
    accepted, reasons = admit_e2_pair(
        state, state_diag, obstacles_diag, NOW_MONO, now_ros_ns=10_000_000_000)
    assert accepted
    assert reasons == ()

    # The cached callback-time age remains fresh-looking, but the same
    # snapshot is stale when it is actually used 1.1s later.
    accepted, reasons = admit_e2_pair(
        state, state_diag, obstacles_diag, NOW_MONO + 1.1,
        now_ros_ns=11_100_000_000)
    assert not accepted
    assert "state_stale" in reasons
    assert "obstacles_stale" in reasons
