"""ROS-free admission rules for short E3/E4 local goals.

Obstacle AABBs are useful as a conservative *candidate-range cap*, but they
are not evidence that the rectangle around them is observed free space.  The
final admission therefore requires a fresh, synchronized 2-D occupancy-grid
record and checks the center cell at every dense path sample.  The semantic
map's grid is already inflated; the independent obstacle geometry gate keeps
the strict 0.8m clearance requirement.
The helper deliberately accepts only the semantic-map values 0 (free
projection) and 100 (occupied); unknown cells and malformed values fail
closed.  A value of 0 is not described as sensor-observed free space here: it
is only one layer of the occupancy-projection evidence used together with
the obstacle clearance and EGO's local-window limit.
"""

from __future__ import annotations

import math

try:
    from ego_e2_admission import (
        E2_FUTURE_TOLERANCE_S,
        E2_MAX_ARRIVAL_AGE_S,
        E2_MAX_MESSAGE_AGE_S,
        E2_MAX_PAIR_ARRIVAL_S,
        E2_MAX_PAIR_STAMP_S,
    )
except ModuleNotFoundError:
    from test.ego_e2_admission import (
        E2_FUTURE_TOLERANCE_S,
        E2_MAX_ARRIVAL_AGE_S,
        E2_MAX_MESSAGE_AGE_S,
        E2_MAX_PAIR_ARRIVAL_S,
        E2_MAX_PAIR_STAMP_S,
    )


LOCAL_GOAL_REQUIRED_CLEARANCE_M = 0.8
# EasyFly's current local_planner.launch.py uses an 8m local-update half
# window.  Keep the acceptance candidate deliberately conservative at 4m;
# this is an explicit cap, not a derivation from the old upstream 5.5m value.
LOCAL_GOAL_LOCAL_UPDATE_HALF_M = 8.0
LOCAL_GOAL_MIN_TRAVEL_M = 3.5
LOCAL_GOAL_UPDATE_RESERVE_M = 4.0
LOCAL_GOAL_MAX_TRAVEL_M = (
    LOCAL_GOAL_LOCAL_UPDATE_HALF_M - LOCAL_GOAL_UPDATE_RESERVE_M)
LOCAL_GOAL_OBSERVED_EDGE_MARGIN_M = 0.25
LOCAL_GOAL_PATH_SAMPLES = 16
LOCAL_GOAL_OCCUPANCY_FRAME = "odom"
LOCAL_GOAL_OCCUPIED_THRESHOLD = 100
LOCAL_GOAL_MAX_GRID_CELLS = 2000000
LOCAL_GOAL_MAX_GRID_DIMENSION = 10000
LOCAL_GOAL_MAX_PATH_SAMPLES = 4096
# Keep the centre of every candidate inside the explicit 4m conservative cap
# around the current pose, well inside the actual 8m EGO update half-window.
LOCAL_GOAL_LOCAL_CENTER_HALF_M = (
    LOCAL_GOAL_LOCAL_UPDATE_HALF_M - LOCAL_GOAL_UPDATE_RESERVE_M)


def _finite(value):
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _stamp_seconds(diag):
    """Return a finite positive timestamp from a callback diagnostic."""
    if not isinstance(diag, dict) or not bool(diag.get("stamp_valid", False)):
        return None
    try:
        sec = int(diag.get("stamp_sec"))
        nanosec = int(diag.get("stamp_nanosec"))
    except (TypeError, ValueError, OverflowError):
        return None
    if sec < 0 or nanosec < 0 or nanosec >= 1000000000:
        return None
    value = float(sec) + float(nanosec) * 1.0e-9
    return value if _finite(value) and value > 0.0 else None


def _grid_field(grid, name, default=None):
    """Read a field from either the flat test record or ROS-like ``info``."""
    if not isinstance(grid, dict):
        return default
    if name in grid:
        return grid.get(name)
    info = grid.get("info")
    if isinstance(info, dict):
        aliases = {
            "resolution": "resolution",
            "width": "width",
            "height": "height",
            "origin_x": "origin_x",
            "origin_y": "origin_y",
            "origin_z": "origin_z",
            "origin_qx": "origin_qx",
            "origin_qy": "origin_qy",
            "origin_qz": "origin_qz",
            "origin_qw": "origin_qw",
        }
        key = aliases.get(name, name)
        if key in info:
            return info.get(key)
        origin = info.get("origin")
        if isinstance(origin, dict):
            if name in ("origin_x", "origin_y", "origin_z"):
                position = origin.get("position", origin)
                if isinstance(position, dict):
                    return position.get(name[-1], default)
            if name in ("origin_qx", "origin_qy", "origin_qz", "origin_qw"):
                orientation = origin.get("orientation", origin)
                if isinstance(orientation, dict):
                    return orientation.get(name[-2:], default)
    return default


def _grid_diag(grid):
    if not isinstance(grid, dict):
        return None
    diag = grid.get("diag")
    if isinstance(diag, dict):
        return diag
    # A plain diagnostic dictionary is accepted for small ROS-free tests.
    return grid if ("stamp_valid" in grid or "stamp_sec" in grid) else None


def _grid_metadata(grid):
    """Return normalized metadata or ``None`` for malformed grid records."""
    if not isinstance(grid, dict):
        return None
    try:
        resolution = float(_grid_field(grid, "resolution"))
        width_raw = _grid_field(grid, "width")
        height_raw = _grid_field(grid, "height")
        width = int(width_raw)
        height = int(height_raw)
        origin_raw = tuple(_grid_field(grid, name) for name in (
            "origin_x", "origin_y", "origin_z", "origin_qx",
            "origin_qy", "origin_qz", "origin_qw"))
    except (TypeError, ValueError, OverflowError):
        return None
    if (isinstance(width_raw, bool) or isinstance(height_raw, bool) or
            not isinstance(width_raw, (int, float)) or
            not isinstance(height_raw, (int, float)) or
            not _finite(width_raw) or not _finite(height_raw) or
            float(width) != float(width_raw) or
            float(height) != float(height_raw)):
        return None
    if (not all(isinstance(value, (int, float)) and
                not isinstance(value, bool) for value in origin_raw)):
        return None
    origin = tuple(float(value) for value in origin_raw)
    data = grid.get("data")
    if not isinstance(data, (list, tuple)):
        return None
    if (not _finite(resolution) or resolution <= 0.0 or
            width <= 0 or height <= 0 or
            width > LOCAL_GOAL_MAX_GRID_DIMENSION or
            height > LOCAL_GOAL_MAX_GRID_DIMENSION or
            width * height > LOCAL_GOAL_MAX_GRID_CELLS or
            len(data) != width * height or
            not all(not isinstance(value, bool) and
                    isinstance(value, (int, float)) and _finite(value) and
                    float(value).is_integer() and
                    -1.0 <= float(value) <= 100.0 for value in data)):
        return None
    if not all(_finite(value) for value in origin):
        return None
    qx, qy, qz, qw = origin[3:]
    qnorm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
    # OccupancyGrid origin must not rotate the axis-aligned cell lattice.  A
    # sign-flipped identity quaternion is equivalent and is accepted.
    if (not _finite(qnorm) or abs(qnorm - 1.0) > 1.0e-3 or
            abs(qx) > 1.0e-3 or abs(qy) > 1.0e-3 or abs(qz) > 1.0e-3 or
            abs(abs(qw) - 1.0) > 1.0e-3):
        return None
    return {
        "resolution": resolution,
        "width": width,
        "height": height,
        "origin_x": origin[0],
        "origin_y": origin[1],
        "origin_z": origin[2],
        "origin_qx": qx,
        "origin_qy": qy,
        "origin_qz": qz,
        "origin_qw": qw,
        "data": tuple(int(value) for value in data),
    }


def validate_occupancy_grid_metadata(grid):
    """Return ``(valid, reason_codes)`` for normalized grid metadata/data."""
    reasons = []
    if _grid_metadata(grid) is None:
        reasons.append("grid_metadata_invalid")
    return not reasons, tuple(reasons)


def _message_reasons(diag, prefix, now_mono, now_ros_ns,
                     expected_frame=LOCAL_GOAL_OCCUPANCY_FRAME):
    reasons = []
    if not isinstance(diag, dict):
        return [prefix + "_missing"]
    stamp = _stamp_seconds(diag)
    if stamp is None:
        reasons.append(prefix + "_timestamp_invalid")
    else:
        if _finite(now_ros_ns):
            age = float(now_ros_ns) * 1.0e-9 - stamp
        else:
            age = diag.get("age", float("nan"))
        if not _finite(age):
            reasons.append(prefix + "_timestamp_invalid")
        elif age < -E2_FUTURE_TOLERANCE_S:
            reasons.append(prefix + "_future")
        elif age > E2_MAX_MESSAGE_AGE_S:
            reasons.append(prefix + "_stale")
    arrival = diag.get("arrival_mono")
    if not _finite(arrival) or not _finite(now_mono):
        reasons.append(prefix + "_arrival_invalid")
    else:
        arrival_age = float(now_mono) - float(arrival)
        if arrival_age < 0.0:
            reasons.append(prefix + "_arrival_future")
        elif arrival_age > E2_MAX_ARRIVAL_AGE_S:
            reasons.append(prefix + "_arrival_stale")
    if (bool(diag.get("clock_mismatch", False)) or
            diag.get("clock_error") or
            str(diag.get("clock_type", "") or "") in ("", "unknown") or
            not _finite(diag.get("node_ros_ns"))):
        reasons.append("clock_mismatch")
    if str(diag.get("frame_id", "") or "") != expected_frame:
        reasons.append(prefix + "_frame_mismatch")
    return reasons


def _append_unique(reasons, values):
    for value in values:
        if value not in reasons:
            reasons.append(value)


def admit_occupancy_grid_evidence(grid, state_diag, obstacles_diag,
                                  now_mono, now_ros_ns=None,
                                  expected_frame=LOCAL_GOAL_OCCUPANCY_FRAME):
    """Gate one grid against freshness, clock/frame, and state/obstacle pair.

    ``state_diag`` and ``obstacles_diag`` are required deliberately: a grid
    that is fresh in isolation is not enough to establish that it describes
    the current UAV pose/obstacle snapshot.
    """
    reasons = []
    metadata = _grid_metadata(grid)
    if metadata is None:
        reasons.append("grid_metadata_invalid")
    diag = _grid_diag(grid)
    _append_unique(reasons, _message_reasons(
        diag, "grid", now_mono, now_ros_ns, expected_frame))
    if isinstance(grid, dict) and "frame_id" in grid and str(
            grid.get("frame_id") or "") != expected_frame:
        _append_unique(reasons, ("grid_frame_mismatch",))
    if isinstance(diag, dict) and str(diag.get("frame_id", "") or "") != expected_frame:
        _append_unique(reasons, ("grid_frame_mismatch",))
    if not isinstance(state_diag, dict):
        reasons.append("state_missing")
    else:
        _append_unique(reasons, _message_reasons(
            state_diag, "state", now_mono, now_ros_ns, expected_frame))
    if not isinstance(obstacles_diag, dict):
        reasons.append("obstacles_missing")
    else:
        _append_unique(reasons, _message_reasons(
            obstacles_diag, "obstacles", now_mono, now_ros_ns,
            expected_frame))
    if isinstance(diag, dict) and isinstance(state_diag, dict):
        if str(diag.get("clock_type", "") or "") != str(
                state_diag.get("clock_type", "") or ""):
            reasons.append("clock_mismatch")
        gs, ss = _stamp_seconds(diag), _stamp_seconds(state_diag)
        if gs is not None and ss is not None and abs(gs - ss) > E2_MAX_PAIR_STAMP_S:
            reasons.append("grid_state_stamp_unsynchronized")
        ga, sa = diag.get("arrival_mono"), state_diag.get("arrival_mono")
        if (_finite(ga) and _finite(sa) and
                abs(float(ga) - float(sa)) > E2_MAX_PAIR_ARRIVAL_S):
            reasons.append("grid_state_arrival_unsynchronized")
    if isinstance(diag, dict) and isinstance(obstacles_diag, dict):
        if str(diag.get("clock_type", "") or "") != str(
                obstacles_diag.get("clock_type", "") or ""):
            reasons.append("clock_mismatch")
        gs, os = _stamp_seconds(diag), _stamp_seconds(obstacles_diag)
        if gs is not None and os is not None and abs(gs - os) > E2_MAX_PAIR_STAMP_S:
            reasons.append("grid_obstacles_stamp_unsynchronized")
        ga, oa = diag.get("arrival_mono"), obstacles_diag.get("arrival_mono")
        if (_finite(ga) and _finite(oa) and
                abs(float(ga) - float(oa)) > E2_MAX_PAIR_ARRIVAL_S):
            reasons.append("grid_obstacles_arrival_unsynchronized")
    return not reasons, tuple(dict.fromkeys(reasons))


def _grid_cell_index(meta, x, y):
    if not (_finite(x) and _finite(y)):
        return None
    try:
        col = math.floor((float(x) - meta["origin_x"]) / meta["resolution"])
        row = math.floor((float(y) - meta["origin_y"]) / meta["resolution"])
    except (OverflowError, ValueError, ZeroDivisionError):
        return None
    if col < 0 or row < 0 or col >= meta["width"] or row >= meta["height"]:
        return None
    return int(row), int(col)


def _grid_center_cell_is_free(meta, x, y):
    """Check the cell containing the path centre point.

    ``semantic_map`` already applies its configured horizontal inflation
    before publishing the grid.  Expanding another 0.8m disk here would
    double-count that safety layer and can reject valid local corridors.
    Unknown, occupied, probabilistic/nonzero, and out-of-bounds cells all
    fail closed.
    """
    index = _grid_cell_index(meta, x, y)
    if index is None:
        return False
    row, col = index
    value = meta["data"][row * meta["width"] + col]
    return value == 0


def occupancy_grid_path_is_safe(
    origin_xy, target_xy, grid, path_samples=LOCAL_GOAL_PATH_SAMPLES,
    local_center_half=LOCAL_GOAL_LOCAL_CENTER_HALF_M,
):
    """Check dense path bounds and every resolution/2 center-cell sample.

    The grid is already inflated by semantic_map.  The obstacle AABB check in
    ``select_local_safe_goal`` is the separate strict ``>0.8m`` clearance
    gate.
    """
    meta = _grid_metadata(grid)
    if meta is None:
        return False
    try:
        ox, oy = float(origin_xy[0]), float(origin_xy[1])
        tx, ty = float(target_xy[0]), float(target_xy[1])
        requested_samples = int(path_samples)
        local_half = float(local_center_half)
    except (TypeError, ValueError, IndexError, OverflowError):
        return False
    if (not all(_finite(value) for value in (ox, oy, tx, ty, local_half)) or
            local_half <= 0.0 or requested_samples < 1 or
            requested_samples > LOCAL_GOAL_MAX_PATH_SAMPLES):
        return False
    distance = math.hypot(tx - ox, ty - oy)
    sample_spacing = meta["resolution"] * 0.5
    if (not _finite(distance) or not _finite(sample_spacing) or
            sample_spacing <= 0.0):
        return False
    try:
        required_samples = max(1, int(math.ceil(distance / sample_spacing)))
    except (OverflowError, ValueError):
        return False
    samples = max(requested_samples, required_samples)
    # A pathological tiny resolution must not turn a malformed grid into an
    # unbounded CPU loop.  Failing closed preserves the safety contract.
    if samples > LOCAL_GOAL_MAX_PATH_SAMPLES:
        return False
    for index in range(samples + 1):
        fraction = index / float(samples)
        x = ox + (tx - ox) * fraction
        y = oy + (ty - oy) * fraction
        if (abs(x - ox) > local_half or abs(y - oy) > local_half or
                not _grid_center_cell_is_free(meta, x, y)):
            return False
    return True


# Short alias kept intentionally explicit for contract/test callers.
validate_occupancy_grid_path = occupancy_grid_path_is_safe


def _obstacle_values(obstacle):
    try:
        if isinstance(obstacle, dict):
            values = (obstacle["center_x"], obstacle["center_y"],
                      obstacle["size_x"], obstacle["size_y"])
        else:
            values = (obstacle.center_x, obstacle.center_y,
                      obstacle.size_x, obstacle.size_y)
    except (AttributeError, KeyError, TypeError, IndexError):
        try:
            values = tuple(obstacle[index] for index in range(4))
        except (TypeError, IndexError, KeyError):
            return None
    if not all(_finite(value) for value in values):
        return None
    values = tuple(float(value) for value in values)
    if values[2] < 0.0 or values[3] < 0.0:
        return None
    return values


def xy_obstacle_clearance(x, y, obstacle):
    """Return XY distance outside one obstacle AABB."""
    values = _obstacle_values(obstacle)
    if values is None or not (_finite(x) and _finite(y)):
        return float("-inf")
    cx, cy, sx, sy = values
    hx = max(0.15, sx * 0.5)
    hy = max(0.15, sy * 0.5)
    dx = max(abs(float(x) - cx) - hx, 0.0)
    dy = max(abs(float(y) - cy) - hy, 0.0)
    return math.hypot(dx, dy)


def observed_support_bounds(origin_xy, obstacles,
                            edge_margin=LOCAL_GOAL_OBSERVED_EDGE_MARGIN_M):
    """Return a contracted obstacle-derived candidate-range cap.

    This rectangle is only a conservative limit proxy derived from obstacle
    extents and the directly observed vehicle position.  It is *not* a proof
    that points inside or outside the rectangle are free.  Final path safety
    is decided by ``occupancy_grid_path_is_safe`` and the obstacle clearance
    check in ``select_local_safe_goal``.
    """
    try:
        ox, oy = float(origin_xy[0]), float(origin_xy[1])
        margin = float(edge_margin)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if not all(_finite(value) for value in (ox, oy, margin)) or margin < 0.0:
        return None
    valid = [_obstacle_values(obstacle) for obstacle in obstacles or ()]
    valid = [values for values in valid if values is not None]
    if not valid:
        return None

    x_min = min([ox] + [cx - sx * 0.5 for cx, _, sx, _ in valid])
    x_max = max([ox] + [cx + sx * 0.5 for cx, _, sx, _ in valid])
    y_min = min([oy] + [cy - sy * 0.5 for _, cy, _, sy in valid])
    y_max = max([oy] + [cy + sy * 0.5 for _, cy, _, sy in valid])

    lower_x, upper_x = x_min + margin, x_max - margin
    lower_y, upper_y = y_min + margin, y_max - margin
    if lower_x > upper_x or lower_y > upper_y:
        return None
    # Keep the directly observed vehicle position inside the support box even
    # when it lies within the edge margin of an obstacle-derived extent.
    lower_x = min(lower_x, ox)
    upper_x = max(upper_x, ox)
    lower_y = min(lower_y, oy)
    upper_y = max(upper_y, oy)
    return lower_x, upper_x, lower_y, upper_y


def _inside(bounds, x, y):
    return (bounds[0] <= x <= bounds[1] and
            bounds[2] <= y <= bounds[3])


def select_local_safe_goal(
    origin_xy,
    obstacles,
    hover_z,
    required_clearance=LOCAL_GOAL_REQUIRED_CLEARANCE_M,
    min_travel=LOCAL_GOAL_MIN_TRAVEL_M,
    max_travel=LOCAL_GOAL_MAX_TRAVEL_M,
    edge_margin=LOCAL_GOAL_OBSERVED_EDGE_MARGIN_M,
    path_samples=LOCAL_GOAL_PATH_SAMPLES,
    occupancy_grid=None,
):
    """Return ``(x, y, hover_z)`` for the shortest admitted local goal.

    A candidate is admitted only when its endpoint and complete sampled
    segment pass the fresh occupancy-grid inflated-centerline gate, stay inside the
    local update window, and retain strict obstacle clearance.  The obstacle
    rectangle is only an additional conservative range cap.  No occupancy
    evidence, malformed evidence, invalid hover height, or lack of a
    meaningful local move returns ``None``.
    """
    try:
        ox, oy, z = (float(origin_xy[0]), float(origin_xy[1]),
                     float(hover_z))
        clearance = float(required_clearance)
        min_distance = float(min_travel)
        max_distance = float(max_travel)
        samples = int(path_samples)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if not all(_finite(value) for value in (
            ox, oy, z, clearance, min_distance, max_distance)):
        return None
    if (z < 0.5 or clearance < LOCAL_GOAL_REQUIRED_CLEARANCE_M or
            min_distance <= 0.0 or
            max_distance < min_distance or
            max_distance > LOCAL_GOAL_LOCAL_UPDATE_HALF_M -
            LOCAL_GOAL_UPDATE_RESERVE_M or samples < 2):
        return None

    if not validate_occupancy_grid_metadata(occupancy_grid)[0]:
        return None

    bounds = observed_support_bounds((ox, oy), obstacles, edge_margin)
    if bounds is None or not _inside(bounds, ox, oy):
        return None

    diagonal = 1.0 / math.sqrt(2.0)
    directions = (
        (1.0, 0.0), (0.0, 1.0), (0.0, -1.0), (-1.0, 0.0),
        (diagonal, diagonal), (diagonal, -diagonal),
        (-diagonal, diagonal), (-diagonal, -diagonal),
    )
    # Distance is the primary key: E3/E4 should spend only a short, observed
    # segment in flight, while still producing meaningful command progress.
    distances = tuple(sorted(set((min_distance, min_distance + 0.5,
                                  max_distance))))
    for distance in distances:
        if distance < min_distance or distance > max_distance:
            continue
        for ux, uy in directions:
            goal_x = ox + ux * distance
            goal_y = oy + uy * distance
            if not _inside(bounds, goal_x, goal_y):
                continue
            path_clearance = float("inf")
            safe = True
            for index in range(samples + 1):
                fraction = index / float(samples)
                x = ox + (goal_x - ox) * fraction
                y = oy + (goal_y - oy) * fraction
                if not _inside(bounds, x, y):
                    safe = False
                    break
                point_clearance = min(
                    (xy_obstacle_clearance(x, y, obstacle)
                     for obstacle in obstacles or ()),
                    default=float("-inf"))
                path_clearance = min(path_clearance, point_clearance)
                if point_clearance <= clearance:
                    safe = False
                    break
            # AABB bounds above are only a candidate cap.  The occupancy grid
            # is the final observed-space gate and checks its already-inflated
            # centerline cells; the independent AABB check above owns the
            # strict 0.8m geometric clearance contract.
            if (safe and path_clearance > clearance and
                    occupancy_grid_path_is_safe(
                        (ox, oy), (goal_x, goal_y), occupancy_grid,
                        path_samples=samples)):
                return goal_x, goal_y, z
    return None
