"""Behavior tests for the bounded, evidence-supported E3/E4 local goal."""

import math

try:
    from ego_local_goal_admission import (
        LOCAL_GOAL_OCCUPIED_THRESHOLD,
        LOCAL_GOAL_REQUIRED_CLEARANCE_M,
        LOCAL_GOAL_MIN_TRAVEL_M,
        admit_occupancy_grid_evidence,
        occupancy_grid_path_is_safe,
        observed_support_bounds,
        select_local_safe_goal,
        validate_occupancy_grid_metadata,
        xy_obstacle_clearance,
    )
except ModuleNotFoundError:
    from test.ego_local_goal_admission import (
        LOCAL_GOAL_OCCUPIED_THRESHOLD,
        LOCAL_GOAL_REQUIRED_CLEARANCE_M,
        LOCAL_GOAL_MIN_TRAVEL_M,
        admit_occupancy_grid_evidence,
        occupancy_grid_path_is_safe,
        observed_support_bounds,
        select_local_safe_goal,
        validate_occupancy_grid_metadata,
        xy_obstacle_clearance,
    )


def _r19_obstacles():
    # The first box's right edge is 27.1m: it models the observed forward
    # extent in r19, not a free-space promise beyond that edge.  The second
    # box gives the local evidence a realistic lateral extent.
    return [
        (26.5, 3.0, 1.2, 6.0),
        (20.0, -4.5, 10.0, 2.0),
    ]


def _sampled_path_clearance(origin, goal, obstacles, samples=32):
    values = []
    for index in range(samples + 1):
        fraction = index / float(samples)
        x = origin[0] + (goal[0] - origin[0]) * fraction
        y = origin[1] + (goal[1] - origin[1]) * fraction
        values.append(min(
            xy_obstacle_clearance(x, y, obstacle)
            for obstacle in obstacles))
    return min(values)


def _grid(*, value=0, origin=(-10.0, -10.0), width=200, height=200,
          resolution=0.2, blocked=()):
    data = [int(value)] * (width * height)
    ox, oy = origin
    for x, y, cell_value in blocked:
        col = int(math.floor((x - ox) / resolution))
        row = int(math.floor((y - oy) / resolution))
        if 0 <= row < height and 0 <= col < width:
            data[row * width + col] = int(cell_value)
    return {
        "frame_id": "odom",
        "resolution": resolution,
        "width": width,
        "height": height,
        "origin_x": ox,
        "origin_y": oy,
        "origin_z": 0.0,
        "origin_qx": 0.0,
        "origin_qy": 0.0,
        "origin_qz": 0.0,
        "origin_qw": 1.0,
        "data": data,
    }


def _diag(*, age=0.1, arrival=99.9, frame="odom", stamp=(10, 0)):
    return {
        "stamp_valid": True,
        "stamp_sec": stamp[0],
        "stamp_nanosec": stamp[1],
        "age": age,
        "arrival_mono": arrival,
        "frame_id": frame,
        "clock_type": "ROS_TIME",
        "clock_mismatch": False,
        "clock_error": None,
        "node_ros_ns": 10000000000,
    }


def test_r19_does_not_admit_blind_x31_goal_and_keeps_hover_height():
    origin = (25.0, -2.0)
    obstacles = _r19_obstacles()
    bounds = observed_support_bounds(origin, obstacles)
    assert bounds is not None
    assert bounds[1] < 27.1

    candidate = select_local_safe_goal(
        origin, obstacles, 1.5, occupancy_grid=_grid())
    assert candidate is not None
    assert candidate[0] < 27.1
    assert not math.isclose(candidate[0], 30.9, abs_tol=0.5)
    assert candidate[2] == 1.5


def test_r19_candidate_has_minimum_motion_and_strict_segment_clearance():
    origin = (25.0, -2.0)
    obstacles = _r19_obstacles()
    candidate = select_local_safe_goal(
        origin, obstacles, 1.5, occupancy_grid=_grid())
    assert candidate is not None
    travel = math.hypot(candidate[0] - origin[0], candidate[1] - origin[1])
    assert travel >= LOCAL_GOAL_MIN_TRAVEL_M
    assert _sampled_path_clearance(origin, candidate, obstacles) > \
        LOCAL_GOAL_REQUIRED_CLEARANCE_M


def test_local_goal_fails_closed_without_evidence_or_valid_hover():
    origin = (25.0, -2.0)
    assert select_local_safe_goal(
        origin, [], 1.5, occupancy_grid=_grid()) is None
    assert select_local_safe_goal(
        origin, _r19_obstacles(), float("nan"), occupancy_grid=_grid()) is None
    assert select_local_safe_goal(origin, _r19_obstacles(), 1.5) is None


def test_grid_pair_requires_fresh_same_frame_and_clock_domain():
    grid = _grid()
    grid["diag"] = _diag()
    accepted, reasons = admit_occupancy_grid_evidence(
        grid, _diag(), _diag(), 100.0, now_ros_ns=10000000000)
    assert accepted, reasons

    stale = dict(grid)
    stale["diag"] = _diag(age=1.01, stamp=(8, 990000000))
    accepted, reasons = admit_occupancy_grid_evidence(
        stale, _diag(), _diag(), 100.0, now_ros_ns=10000000000)
    assert not accepted and "grid_stale" in reasons

    wrong_frame = dict(grid)
    wrong_frame["diag"] = _diag(frame="map")
    accepted, reasons = admit_occupancy_grid_evidence(
        wrong_frame, _diag(), _diag(), 100.0, now_ros_ns=10000000000)
    assert not accepted and "grid_frame_mismatch" in reasons

    future = dict(grid)
    future["diag"] = _diag(age=-0.21, stamp=(10, 210000000))
    accepted, reasons = admit_occupancy_grid_evidence(
        future, _diag(), _diag(), 100.0, now_ros_ns=10000000000)
    assert not accepted and "grid_future" in reasons


def test_grid_metadata_and_origin_must_be_normalized():
    grid = _grid()
    malformed = dict(grid)
    malformed["data"] = malformed["data"][:-1]
    assert not validate_occupancy_grid_metadata(malformed)[0]

    malformed = dict(grid)
    malformed["origin_qz"] = 0.2
    assert not validate_occupancy_grid_metadata(malformed)[0]

    malformed = dict(grid)
    malformed["resolution"] = float("nan")
    assert not validate_occupancy_grid_metadata(malformed)[0]


def test_grid_unknown_occupied_and_out_of_bounds_fail_closed():
    origin = (25.0, -2.0)
    target = (28.0, -2.0)
    assert occupancy_grid_path_is_safe(origin, target, _grid())
    assert not occupancy_grid_path_is_safe(
        origin, target, _grid(blocked=((26.0, -2.0, LOCAL_GOAL_OCCUPIED_THRESHOLD),)))
    assert not occupancy_grid_path_is_safe(
        origin, target, _grid(blocked=((26.0, -2.0, 50),)))
    assert not occupancy_grid_path_is_safe(
        origin, target, _grid(blocked=((26.0, -2.0, -1),)))
    edge = _grid(origin=(20.0, -5.0), width=50, height=50)
    assert not occupancy_grid_path_is_safe((29.8, -2.0), (30.1, -2.0), edge)


def test_grid_adaptive_samples_detect_a_fine_cell_between_coarse_samples():
    # With only one requested sample, resolution/2 adaptation still visits
    # the occupied center cell instead of skipping over a thin obstacle.
    fine = _grid(blocked=((26.0, -2.0, LOCAL_GOAL_OCCUPIED_THRESHOLD),))
    assert not occupancy_grid_path_is_safe(
        (25.0, -2.0), (28.0, -2.0), fine, path_samples=1)


def test_r19_semantic_grid_inflation_fixture_keeps_candidate_in_observed_corridor():
    # semantic_map's current horizontal inflation is 0.7m.  Model the
    # resulting occupied cells around the forward pillar, while leaving the
    # conservative west corridor available to the AABB >0.8m gate.
    inflated = _grid()
    ox, oy = inflated["origin_x"], inflated["origin_y"]
    res = inflated["resolution"]
    for x in [25.9 + 0.1 * i for i in range(14)]:
        for y in [-0.7 + 0.1 * i for i in range(76)]:
            col = int(math.floor((x - ox) / res))
            row = int(math.floor((y - oy) / res))
            if 0 <= row < inflated["height"] and 0 <= col < inflated["width"]:
                inflated["data"][row * inflated["width"] + col] = 100
    assert occupancy_grid_path_is_safe((25.0, -2.0), (25.0, -2.0), inflated)
    candidate = select_local_safe_goal(
        (25.0, -2.0), _r19_obstacles(), 1.5, occupancy_grid=inflated)
    assert candidate is not None
    assert candidate[2] == 1.5
    assert math.hypot(candidate[0] - 25.0, candidate[1] + 2.0) >= 3.5
    assert occupancy_grid_path_is_safe(
        (25.0, -2.0), candidate[:2], inflated)


def test_required_clearance_cannot_be_relaxed_below_0_8m():
    assert select_local_safe_goal(
        (25.0, -2.0), _r19_obstacles(), 1.5, required_clearance=0.79,
        occupancy_grid=_grid()) is None
