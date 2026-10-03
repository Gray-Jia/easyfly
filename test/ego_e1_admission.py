"""ROS-free geometry/admission rules for the G8 E1 static bypass.

E1 deliberately asks EGO to cross the obstacle's side-to-side plane so the
planner has to produce a real bypass.  The terminal point is nevertheless
selected from the current, paired obstacle snapshot rather than from a
world-coordinate fixture.  Keeping this small helper independent of rclpy
lets geometry regressions run in the normal pytest environment.
"""

from __future__ import annotations

import math


E1_REQUIRED_CLEARANCE_M = 0.8
# The terminal point is beyond the anchor in the origin->anchor direction.
# Four metres leaves room for the inflated pillar and the spline's terminal
# control points; it is a geometry margin, not a relaxed clearance threshold.
E1_MIN_OPPOSITE_OFFSET_M = 4.0
E1_TERMINAL_MARGIN_M = 0.4
E1_ANCHOR_MATCH_TOLERANCE_M = 1.0
E1_HOVER_ALTITUDE_M = 1.5
E1_HOVER_ALTITUDE_TOLERANCE_M = 0.35
# perception_demo pillar_1 is observed at roughly odom z=2.36m (world top
# 3.0m with the r21 ground/odom offset).  The local planner launch uses a
# hard 2.0m virtual ceiling, leaving ~0.36m below that top and ~0.5m above
# the nominal hover.  A small telemetry tolerance is for controller tracking
# only; it remains below the observed pillar top and does not alter the 0.8m
# horizontal clearance contract.
E1_MAX_PLANNER_ALTITUDE_M = 2.0
E1_MAX_POSE_ALTITUDE_TOLERANCE_M = 0.15


def _finite(value):
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def admitted_hover_altitude(
    altitude,
    expected=E1_HOVER_ALTITUDE_M,
    tolerance=E1_HOVER_ALTITUDE_TOLERANCE_M,
):
    """Return a stable hover altitude or ``None`` (fail closed).

    E1/E2 are horizontal bypass tests.  Sending a point one metre above the
    map floor while the vehicle is hovering at 1.5m creates an avoidable
    vertical descent and lets the optimizer enter the ground/vertical
    inflation band.  The altitude is taken from the current hover state, but
    an implausible or non-finite state is rejected instead of guessed.
    """
    if not (_finite(altitude) and _finite(expected) and _finite(tolerance)):
        return None
    altitude = float(altitude)
    expected = float(expected)
    tolerance = float(tolerance)
    if tolerance <= 0.0 or abs(altitude - expected) > tolerance:
        return None
    return altitude


def e1_pose_height_within_policy(
    altitude,
    max_altitude=E1_MAX_PLANNER_ALTITUDE_M,
    telemetry_tolerance=E1_MAX_POSE_ALTITUDE_TOLERANCE_M,
):
    """Accept only a finite E1 pose below the fixed-height bypass ceiling.

    The planner's continuous hard ceiling is checked in GridMap.  This
    helper is the independent flight telemetry contract: a controller
    overshoot above the ceiling's bounded tolerance is still a failed E1,
    rather than evidence that the vehicle successfully flew over the pillar.
    """
    if not (_finite(altitude) and _finite(max_altitude) and
            _finite(telemetry_tolerance)):
        return False
    max_altitude = float(max_altitude)
    telemetry_tolerance = float(telemetry_tolerance)
    return telemetry_tolerance >= 0.0 and float(altitude) <= (
        max_altitude + telemetry_tolerance)


def _obstacle_values(obstacle):
    """Extract ``(cx, cy, sx, sy)`` from a ROS-free tuple/list/dict."""
    try:
        if isinstance(obstacle, dict):
            values = (obstacle["center_x"], obstacle["center_y"],
                      obstacle["size_x"], obstacle["size_y"])
        else:
            values = (obstacle[0], obstacle[1], obstacle[2], obstacle[3])
    except (KeyError, IndexError, TypeError):
        return None
    if not all(_finite(value) for value in values):
        return None
    values = tuple(float(value) for value in values)
    if values[2] < 0.0 or values[3] < 0.0:
        return None
    return values


def xy_obstacle_clearance(x, y, obstacle):
    """Distance outside an obstacle's XY AABB, with a finite floor extent."""
    values = _obstacle_values(obstacle)
    if values is None or not (_finite(x) and _finite(y)):
        return float("-inf")
    cx, cy, sx, sy = values
    hx = max(0.15, sx * 0.5)
    hy = max(0.15, sy * 0.5)
    dx = max(abs(float(x) - cx) - hx, 0.0)
    dy = max(abs(float(y) - cy) - hy, 0.0)
    return math.hypot(dx, dy)


def _point_segment_distance(point, start, end):
    try:
        px, py = (float(point[0]), float(point[1]))
        x0, y0 = (float(start[0]), float(start[1]))
        x1, y1 = (float(end[0]), float(end[1]))
    except (IndexError, TypeError, ValueError, OverflowError):
        return float("inf")
    if not all(_finite(value) for value in (px, py, x0, y0, x1, y1)):
        return float("inf")
    dx, dy = x1 - x0, y1 - y0
    denom = dx * dx + dy * dy
    if denom <= 1.0e-12:
        return math.hypot(px - x0, py - y0)
    t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / denom))
    return math.hypot(px - (x0 + t * dx), py - (y0 + t * dy))


def select_e1_opposite_goal(
    origin_xy,
    anchor_xy,
    obstacles,
    required_clearance=E1_REQUIRED_CLEARANCE_M,
    min_opposite_offset=E1_MIN_OPPOSITE_OFFSET_M,
    terminal_margin=E1_TERMINAL_MARGIN_M,
    anchor_tolerance=E1_ANCHOR_MATCH_TOLERANCE_M,
):
    """Select a terminal-safe goal that still requires bypassing ``anchor``.

    ``obstacles`` is a sequence of ``(cx, cy, sx, sy)`` tuples (or matching
    dicts).  The nearest fresh obstacle must match the sampled anchor, and the
    returned point must be beyond that anchor in the origin-to-anchor
    direction.  Candidates are generated from observed obstacle extent and
    checked against *all* current obstacles; no absolute world coordinate is
    used.  A direct candidate is preferred so the segment crosses the anchor
    AABB and cannot silently turn this into a no-obstacle test.
    """
    try:
        ox, oy = float(origin_xy[0]), float(origin_xy[1])
        ax, ay = float(anchor_xy[0]), float(anchor_xy[1])
        clearance = float(required_clearance)
        min_offset = float(min_opposite_offset)
        terminal_margin = float(terminal_margin)
        anchor_tolerance = float(anchor_tolerance)
    except (IndexError, TypeError, ValueError, OverflowError):
        return None
    if not all(_finite(value) for value in (
            ox, oy, ax, ay, clearance, min_offset, terminal_margin,
            anchor_tolerance)):
        return None
    if clearance <= 0.0 or min_offset <= 0.0 or terminal_margin < 0.0 or \
            anchor_tolerance <= 0.0:
        return None
    vx, vy = ax - ox, ay - oy
    distance = math.hypot(vx, vy)
    if not math.isfinite(distance) or distance <= 0.5:
        return None
    ux, uy = vx / distance, vy / distance

    valid_obstacles = []
    for obstacle in obstacles or ():
        values = _obstacle_values(obstacle)
        if values is not None:
            valid_obstacles.append(values)
    if not valid_obstacles:
        return None
    anchor_obstacle = min(
        valid_obstacles,
        key=lambda obstacle: math.hypot(obstacle[0] - ax, obstacle[1] - ay))
    anchor_distance = math.hypot(anchor_obstacle[0] - ax,
                                 anchor_obstacle[1] - ay)
    if anchor_distance > anchor_tolerance:
        return None
    anchor_hx = max(0.15, anchor_obstacle[2] * 0.5)
    anchor_hy = max(0.15, anchor_obstacle[3] * 0.5)
    # Projection of the observed AABB on the travel direction.  This keeps
    # the offset tied to the current obstacle extent while preserving a hard
    # minimum that is independent of incidental point-cloud coordinates.
    extent_along = abs(ux) * anchor_hx + abs(uy) * anchor_hy
    base_offset = max(min_offset,
                      extent_along + clearance + terminal_margin)
    if not math.isfinite(base_offset):
        return None

    # Direct, progressively farther candidates.  Each segment contains the
    # anchor center, so the requested route necessarily has to go around it.
    # A farther candidate is used only if another current obstacle occupies
    # the first terminal point.
    for extra in (0.0, 1.0, 2.0):
        offset = base_offset + extra
        goal = (ax + ux * offset, ay + uy * offset)
        if not all(_finite(value) for value in goal):
            continue
        terminal_clearance = min(
            (xy_obstacle_clearance(goal[0], goal[1], obstacle)
             for obstacle in valid_obstacles),
            default=float("-inf"))
        # Keep the segment's required-bypass invariant explicit.  The anchor
        # center is on the segment for these collinear candidates.
        if _point_segment_distance((ax, ay), (ox, oy), goal) > 1.0e-6:
            continue
        if terminal_clearance > clearance:
            return goal[0], goal[1], terminal_clearance, base_offset
    return None
