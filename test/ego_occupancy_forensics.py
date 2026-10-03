#!/usr/bin/env python3
"""Offline, read-only evidence for a GridMap trusted-cloud collision sample.

This intentionally does not replay ROS callbacks.  It reads the recorded
topics, applies the small trusted-cloud part of GridMap that can be checked
from a bag, and labels the result as offline evidence.  The bag therefore
cannot prove that the live planner received or accepted the same frame.

Example (the defaults match the r24 launch/log):

  python3 test/ego_occupancy_forensics.py test-results-v219/g8-v219-r24-bag \
      --terminal 7.227 -2.777 1.488 --wall-time 1790982588.948611348 \
      --log test-results-v219/g8-v219-r24.log

ROS Python packages are imported only after argument parsing so ``--help``
works on a machine without a sourced ROS workspace.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass


PREDICTION_STRICT_TOL = 1.0e-5


@dataclass(frozen=True)
class Config:
    origin: tuple[float, float, float] = (-40.0, -12.5, 0.5)
    size: tuple[float, float, float] = (80.0, 25.0, 5.0)
    resolution: float = 0.1
    local_range: tuple[float, float, float] = (8.0, 8.0, 3.0)
    xy_inflation_cells: int = 8
    z_inflation_cells: int = 4
    aging_frames: int = 20
    virtual_ceiling: float = 2.0
    max_points: int = 200_000
    prediction_horizon: float = 1.5
    prediction_steps: int = 8
    prediction_footprint: int = 9
    prediction_min_half: tuple[float, float] = (0.2, 0.2)
    prediction_uncertainty_growth: float = 0.1
    prediction_max_uncertainty: float = 0.5
    prediction_max_bbox: tuple[float, float, float] = (2.5, 2.5, 2.5)
    prediction_max_speed: float = 5.0


@dataclass
class Record:
    record_s: float
    stamp_s: float | None
    msg: object


@dataclass
class CloudSummary:
    index: int
    record_s: float
    stamp_s: float | None
    frame: str
    points: int = 0
    local_points: int = 0
    direct_hits: int = 0
    direct_examples: list[tuple[int, tuple[float, float, float], str]] | None = None
    prediction_count: int = 0
    prediction_hits: int = 0
    prediction_examples: list[tuple[int, int, float, tuple[float, float, float]]] | None = None
    occupied_after: bool = False
    terminal_age: int | None = None
    pose: tuple[float, float, float] | None = None
    obstacle_stamp_s: float | None = None
    prediction_provenance: str = "none"
    prediction_tail_start: int | None = None
    prediction_tail_max_error: float | None = None
    reason: str = "accepted"

    def __post_init__(self) -> None:
        if self.direct_examples is None:
            self.direct_examples = []
        if self.prediction_examples is None:
            self.prediction_examples = []


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Read a ROS2 sqlite bag and inspect the 20 clouds before a terminal "
            "collision coordinate; no ROS graph or external network is used."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("bag", help="rosbag2 directory (sqlite3; metadata.yaml optional)")
    p.add_argument(
        "--terminal", nargs=3, type=float, required=True, metavar=("X", "Y", "Z"),
        help="terminal sample in the GridMap frame (normally odom)",
    )
    tg = p.add_mutually_exclusive_group()
    tg.add_argument(
        "--ros-time", "--ros", type=float,
        help="terminal ROS/header timestamp in seconds",
    )
    tg.add_argument(
        "--wall-time", "--wall", type=float,
        help="terminal bag-record timestamp in seconds (wall-time surrogate)",
    )
    p.add_argument("--log", help="optional startup log; matching GridMap/tracker lines are shown")
    p.add_argument("--clouds", type=int, default=20, help="number of preceding clouds to print")
    p.add_argument("--obstacle-slop", type=float, default=0.5, help="nearest /obstacles stamp tolerance")
    p.add_argument(
        "--neighborhood-seconds", type=float, default=1.0,
        help="look-back window for nearby /obstacles cluster churn",
    )
    p.add_argument(
        "--neighborhood-radius", type=float, default=3.0,
        help="XY radius around current dynamic cluster for churn output",
    )
    p.add_argument(
        "--prediction-match-tol", type=float, default=0.08,
        help="distance used to label a cloud point as prediction-like",
    )
    p.add_argument(
        "--origin", nargs=3, type=float, metavar=("X", "Y", "Z"),
        default=Config.origin, help="GridMap map origin; override if this run differed",
    )
    p.add_argument(
        "--map-size", nargs=3, type=float, metavar=("X", "Y", "Z"),
        default=Config.size, help="GridMap map size",
    )
    p.add_argument("--resolution", type=float, default=Config.resolution)
    p.add_argument(
        "--local-range", nargs=3, type=float, metavar=("X", "Y", "Z"),
        default=Config.local_range, help="strict cloud-to-odom local update range",
    )
    p.add_argument("--xy-inflation-cells", type=int, default=Config.xy_inflation_cells)
    p.add_argument("--z-inflation-cells", type=int, default=Config.z_inflation_cells)
    p.add_argument("--aging-frames", type=int, default=Config.aging_frames)
    p.add_argument("--virtual-ceiling", type=float, default=Config.virtual_ceiling)
    return p


def _stamp(value: object) -> float | None:
    if value is None:
        return None
    sec = getattr(value, "sec", None)
    nsec = getattr(value, "nanosec", None)
    if sec is None or nsec is None:
        return None
    result = float(sec) + float(nsec) * 1.0e-9
    return result if math.isfinite(result) and result > 0.0 else None


def _header_stamp(msg: object) -> float | None:
    return _stamp(getattr(getattr(msg, "header", None), "stamp", None))


def _header_identity(msg: object) -> tuple[int, int, str] | None:
    header = getattr(msg, "header", None)
    stamp = getattr(header, "stamp", None)
    sec = getattr(stamp, "sec", None)
    nsec = getattr(stamp, "nanosec", None)
    if sec is None or nsec is None:
        return None
    return int(sec), int(nsec), str(getattr(header, "frame_id", ""))


def _finite_xyz(value: object) -> tuple[float, float, float] | None:
    try:
        point = tuple(float(value[i]) for i in range(3))
    except (IndexError, TypeError, ValueError):
        return None
    return point if all(math.isfinite(v) for v in point) else None


def _point_iter(msg: object):
    """Yield (x, y, z), preserving NaNs so an invalid frame is visible."""
    from sensor_msgs_py import point_cloud2

    for raw in point_cloud2.read_points(
        msg, field_names=("x", "y", "z"), skip_nans=False
    ):
        point = _finite_xyz(raw)
        yield point if point is not None else (math.nan, math.nan, math.nan)


def _load_bag(path: str):
    try:
        import rosbag2_py
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
    except ImportError as exc:
        raise RuntimeError(
            "ROS Python imports unavailable; source install/setup.bash before reading a bag"
        ) from exc

    reader = rosbag2_py.SequentialReader()
    try:
        reader.open(
            rosbag2_py.StorageOptions(uri=os.fspath(path), storage_id="sqlite3"),
            rosbag2_py.ConverterOptions("", ""),
        )
    except Exception as exc:
        raise RuntimeError(f"cannot open rosbag2 sqlite directory: {path}: {exc}") from exc

    topic_types = {meta.name: meta.type for meta in reader.get_all_topics_and_types()}
    required = {
        "/pointcloud_nonground",
        "/obstacles",
        "/uav_state",
        "/clock",
    }
    missing = sorted(required - topic_types.keys())
    if missing:
        raise RuntimeError(f"bag is missing required topics: {', '.join(missing)}")
    msg_types = {name: get_message(topic_types[name]) for name in required}
    clouds: list[Record] = []
    obstacles: list[Record] = []
    states: list[Record] = []
    clocks: list[Record] = []
    while reader.has_next():
        topic, data, record_ns = reader.read_next()
        if topic not in required:
            continue
        msg = deserialize_message(data, msg_types[topic])
        record_s = float(record_ns) * 1.0e-9
        item = Record(record_s, _header_stamp(msg), msg)
        if topic == "/pointcloud_nonground":
            clouds.append(item)
        elif topic == "/obstacles":
            obstacles.append(item)
        elif topic == "/uav_state":
            states.append(item)
        else:
            item.stamp_s = _stamp(getattr(msg, "clock", None))
            clocks.append(item)
    return clouds, obstacles, states, clocks


def _pose(record: Record | None) -> tuple[float, float, float] | None:
    if record is None:
        return None
    msg = record.msg
    values = (getattr(msg, "position_x", math.nan), getattr(msg, "position_y", math.nan),
              getattr(msg, "position_z", math.nan))
    try:
        values = tuple(float(value) for value in values)
    except (TypeError, ValueError):
        return None
    return values if all(math.isfinite(value) for value in values) else None


def _state_for(cloud: Record, states: list[Record]) -> Record | None:
    # Bag record order models callback arrival better than header order.  The
    # topic is high-rate; the latest state already recorded before this cloud
    # is the least surprising offline proxy for GridMap's odom sample.
    prior = [item for item in states if item.record_s <= cloud.record_s + 1.0e-9]
    return prior[-1] if prior else None


def _obstacle_for(cloud: Record, obstacles: list[Record], slop: float) -> Record | None:
    if not obstacles:
        return None
    target = cloud.stamp_s if cloud.stamp_s is not None else cloud.record_s
    scored = []
    for item in obstacles:
        key = item.stamp_s if item.stamp_s is not None else item.record_s
        scored.append((abs(key - target), item))
    distance, item = min(scored, key=lambda pair: pair[0])
    return item if distance <= max(0.0, slop) else None


def _cell(point: tuple[float, float, float], cfg: Config) -> tuple[int, int, int]:
    resolution_inv = 1.0 / cfg.resolution
    return tuple(math.floor((point[i] - cfg.origin[i]) * resolution_inv)
                 for i in range(3))  # type: ignore[return-value]


def _in_map_cell(cell: tuple[int, int, int], cfg: Config) -> bool:
    count = tuple(int(math.ceil(cfg.size[i] / cfg.resolution)) for i in range(3))
    return all(0 <= cell[i] < count[i] for i in range(3))


def _in_map_point(point: tuple[float, float, float], cfg: Config) -> bool:
    # Match GridMap::isInMap's strict boundary guard, not just its index test.
    return all(
        cfg.origin[i] + 1.0e-4 <= point[i] <= cfg.origin[i] + cfg.size[i] - 1.0e-4
        for i in range(3)
    )


def _local(point: tuple[float, float, float], pose: tuple[float, float, float], cfg: Config) -> bool:
    return all(abs(point[i] - pose[i]) < cfg.local_range[i] for i in range(3))


def _can_mark_terminal(
    point: tuple[float, float, float], terminal_cell: tuple[int, int, int], cfg: Config
) -> bool:
    # Mirror GridMap's actual loop: add the metric offset first, then apply
    # floor((p + offset - origin) * resolution_inv).  Computing one base cell
    # and adding integer offsets is almost equivalent, but differs at floating
    # boundaries and would hide the exact source of a forensic hit.
    resolution_inv = 1.0 / cfg.resolution
    x_offsets = [offset for offset in range(-cfg.xy_inflation_cells, cfg.xy_inflation_cells + 1)
                 if math.floor((point[0] + offset * cfg.resolution - cfg.origin[0]) *
                               resolution_inv) == terminal_cell[0]]
    y_offsets = [offset for offset in range(-cfg.xy_inflation_cells, cfg.xy_inflation_cells + 1)
                 if math.floor((point[1] + offset * cfg.resolution - cfg.origin[1]) *
                               resolution_inv) == terminal_cell[1]]
    z_offsets = [offset for offset in range(-cfg.z_inflation_cells, cfg.z_inflation_cells + 1)
                 if math.floor((point[2] + offset * cfg.resolution - cfg.origin[2]) *
                               resolution_inv) == terminal_cell[2]]
    return bool(x_offsets and y_offsets and z_offsets)


def _predictions(obstacle_record: Record | None, pose: tuple[float, float, float] | None,
                 cfg: Config) -> list[tuple[int, int, float, tuple[float, float, float]]]:
    if obstacle_record is None:
        return []
    dynamic = []
    for obstacle in getattr(obstacle_record.msg, "obstacles", []):
        try:
            center = (float(obstacle.center_x), float(obstacle.center_y), float(obstacle.center_z))
            size = (float(obstacle.size_x), float(obstacle.size_y), float(obstacle.size_z))
            velocity = (float(obstacle.velocity_x), float(obstacle.velocity_y), float(obstacle.velocity_z))
            obstacle_id = int(obstacle.obstacle_id)
            is_dynamic = bool(obstacle.is_dynamic)
        except (AttributeError, TypeError, ValueError):
            continue
        if not is_dynamic or not all(math.isfinite(v) for v in center + size + velocity):
            continue
        if any(size[i] < 0.0 or size[i] > cfg.prediction_max_bbox[i] for i in range(3)):
            continue
        if math.sqrt(sum(v * v for v in velocity)) > cfg.prediction_max_speed:
            continue
        dynamic.append((obstacle_id, center, size, velocity))
    if not dynamic:
        return []
    ref = pose if pose is not None else (0.0, 0.0, 0.0)
    dynamic.sort(key=lambda item: sum((item[1][i] - ref[i]) ** 2 for i in range(3)))
    total_steps = 256 // cfg.prediction_footprint
    base, remainder = divmod(total_steps, len(dynamic))
    points = []
    footprint = ((0.0, 0.0), (-1.0, 0.0), (1.0, 0.0), (0.0, -1.0),
                 (0.0, 1.0), (-1.0, -1.0), (-1.0, 1.0), (1.0, -1.0), (1.0, 1.0))
    for rank, (obstacle_id, center, size, velocity) in enumerate(dynamic):
        steps = min(cfg.prediction_steps, base + (1 if rank < remainder else 0))
        for step in range(1, steps + 1):
            t = cfg.prediction_horizon * step / cfg.prediction_steps
            uncertainty = min(cfg.prediction_max_uncertainty,
                              cfg.prediction_uncertainty_growth * t)
            half_x = max(size[0] * 0.5, cfg.prediction_min_half[0]) + uncertainty
            half_y = max(size[1] * 0.5, cfg.prediction_min_half[1]) + uncertainty
            cx = center[0] + velocity[0] * t
            cy = center[1] + velocity[1] * t
            cz = center[2] + velocity[2] * t
            for fx, fy in footprint:
                points.append((obstacle_id, step, t, (cx + fx * half_x, cy + fy * half_y, cz)))
    return points


def _obstacle_geometry(obstacle: object):
    try:
        center = (float(obstacle.center_x), float(obstacle.center_y), float(obstacle.center_z))
        size = (float(obstacle.size_x), float(obstacle.size_y), float(obstacle.size_z))
        velocity = (float(obstacle.velocity_x), float(obstacle.velocity_y),
                    float(obstacle.velocity_z))
        return (int(obstacle.obstacle_id), center, size, velocity, bool(obstacle.is_dynamic))
    except (AttributeError, TypeError, ValueError):
        return None


def _print_neighborhood(
    final_cloud: Record, final_obstacle: Record | None, obstacles: list[Record],
    terminal: tuple[float, float, float], seconds: float, radius: float,
) -> None:
    if final_obstacle is None:
        print("NEIGHBORHOOD unavailable: no /obstacles frame near terminal cloud")
        return
    current_stamp = final_cloud.stamp_s or final_cloud.record_s
    current = [_obstacle_geometry(item) for item in getattr(final_obstacle.msg, "obstacles", [])]
    current = [item for item in current if item is not None]
    dynamic_current = [item for item in current if item[4]]
    targets = [item[1] for item in dynamic_current]
    if not targets and current:
        targets = [min(current, key=lambda item: math.hypot(
            item[1][0] - terminal[0], item[1][1] - terminal[1]))[1]]
    print("NEIGHBORHOOD current_stamp=%.9f window=%.2fs radius=%.2fm" %
          (current_stamp, max(0.0, seconds), max(0.0, radius)))
    for obstacle_id, center, size, velocity, is_dynamic in dynamic_current:
        print("  CURRENT id=%d center=(%.6f,%.6f,%.6f) size=(%.6f,%.6f,%.6f) "
              "velocity=(%.6f,%.6f,%.6f) dynamic=%s" %
              (obstacle_id, *center, *size, *velocity, is_dynamic))
    if not targets:
        print("  CURRENT no valid obstacle boxes")
        return
    lower = current_stamp - max(0.0, seconds)
    for record in obstacles:
        stamp = record.stamp_s
        if stamp is None or stamp < lower - 1.0e-9 or stamp > current_stamp + 1.0e-9:
            continue
        nearby = []
        for obstacle in getattr(record.msg, "obstacles", []):
            geometry = _obstacle_geometry(obstacle)
            if geometry is None:
                continue
            if min(math.hypot(geometry[1][0] - target[0], geometry[1][1] - target[1])
                   for target in targets) <= max(0.0, radius):
                nearby.append(geometry)
        if not nearby:
            continue
        print("  FRAME ros=%.9f clusters=%d" % (stamp, len(nearby)))
        for obstacle_id, center, size, velocity, is_dynamic in nearby:
            print("    id=%d center=(%.6f,%.6f,%.6f) size=(%.6f,%.6f,%.6f) "
                  "dynamic=%s" % (obstacle_id, *center, *size, is_dynamic))


def _simulate_cloud(
    index: int, cloud: Record, state: Record | None, obstacle: Record | None,
    terminal_cell: tuple[int, int, int], terminal: tuple[float, float, float],
    occupied: bool, terminal_age: int | None, cfg: Config, match_tol: float,
) -> tuple[CloudSummary, bool, int | None]:
    msg = cloud.msg
    summary = CloudSummary(index, cloud.record_s, cloud.stamp_s,
                           str(getattr(getattr(msg, "header", None), "frame_id", "")))
    pose = _pose(state)
    summary.pose = pose
    summary.obstacle_stamp_s = obstacle.stamp_s if obstacle else None
    width = int(getattr(msg, "width", 0))
    height = int(getattr(msg, "height", 0))
    summary.points = max(0, width * height)
    if summary.frame != "odom":
        return _clear(summary, "frame_id is not odom")
    if summary.points <= 0 or summary.points > cfg.max_points:
        return _clear(summary, "empty/over-limit cloud")
    if pose is None or not _in_map_point(pose, cfg):
        return _clear(summary, "no finite in-map /uav_state pose")

    predictions = _predictions(obstacle, pose, cfg)
    summary.prediction_count = len(predictions)
    prediction_hit = [item for item in predictions
                      if _local(item[3], pose, cfg) and
                      _can_mark_terminal(item[3], terminal_cell, cfg)]
    summary.prediction_hits = len(prediction_hit)
    summary.prediction_examples.extend(prediction_hit[:8])
    tail_start = summary.points - len(predictions) if predictions else None
    summary.prediction_tail_start = tail_start if tail_start is not None and tail_start >= 0 else None
    tail_points: list[tuple[float, float, float]] = []
    hit_indices: list[int] = []

    if occupied:
        if terminal_age is None:
            terminal_age = 0
        terminal_age += 1
        if terminal_age >= cfg.aging_frames:
            occupied = False
            terminal_age = None

    try:
        for point_index, point in enumerate(_point_iter(msg)):
            if not all(math.isfinite(value) for value in point):
                return _clear(summary, "non-finite point")
            if tail_start is not None and point_index >= tail_start:
                tail_points.append(point)
            if not _local(point, pose, cfg):
                continue
            summary.local_points += 1
            if not _can_mark_terminal(point, terminal_cell, cfg):
                continue
            occupied = True
            terminal_age = 0
            summary.direct_hits += 1
            hit_indices.append(point_index)
            if len(summary.direct_examples) < 12:
                summary.direct_examples.append((point_index, point, "raw/unknown"))
    except Exception as exc:  # sensor_msgs_py gives varying numpy/python row types
        return _clear(summary, f"PointCloud2 decode failed: {exc}")

    strict_errors: list[float] = []
    same_header = (
        obstacle is not None and
        _header_identity(msg) is not None and
        _header_identity(msg) == _header_identity(obstacle.msg)
    )
    strict_full = bool(predictions) and same_header and len(tail_points) == len(predictions)
    if strict_full:
        strict_errors = [math.dist(actual, expected)
                         for actual, expected in zip(tail_points, (item[3] for item in predictions))]
        strict_full = all(error <= PREDICTION_STRICT_TOL for error in strict_errors)
        summary.prediction_tail_max_error = max(strict_errors, default=0.0)
    tail_hit = bool(tail_start is not None and any(index >= tail_start for index in hit_indices))
    if predictions and summary.direct_hits:
        summary.prediction_provenance = (
            "prediction-tail-confirmed" if strict_full and tail_hit else "prediction-like"
        )
    for example_index, (point_index, point, _) in enumerate(summary.direct_examples):
        nearest = min(predictions, key=lambda item: math.dist(point, item[3]), default=None)
        nearest_distance = math.dist(point, nearest[3]) if nearest is not None else math.inf
        label = "raw/unknown"
        if (summary.prediction_provenance == "prediction-tail-confirmed" and
                tail_start is not None and point_index >= tail_start and nearest is not None):
            label = (f"prediction-tail-confirmed id={nearest[0]} step={nearest[1]} "
                     f"t={nearest[2]:.3f}s")
        elif nearest is not None and nearest_distance <= match_tol:
            label = f"prediction-like id={nearest[0]} step={nearest[1]} t={nearest[2]:.3f}s"
        summary.direct_examples[example_index] = (point_index, point, label)
    summary.occupied_after = occupied
    summary.terminal_age = terminal_age
    return summary, occupied, terminal_age


def _clear(summary: CloudSummary, reason: str):
    summary.reason = reason
    summary.occupied_after = False
    summary.terminal_age = None
    return summary, False, None


def _log_lines(path: str | None) -> list[str]:
    if not path:
        return []
    try:
        with open(path, encoding="utf-8", errors="replace") as stream:
            return [line.rstrip() for line in stream
                    if "GridMap trusted cloud:" in line or "动态障碍跟踪:" in line]
    except OSError as exc:
        print(f"[warn] cannot read --log {path}: {exc}", file=sys.stderr)
        return []


def _fmt_time(value: float | None) -> str:
    return "-" if value is None else f"{value:.9f}"


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    terminal = tuple(args.terminal)
    cfg = Config(tuple(args.origin), tuple(args.map_size), args.resolution,
                 tuple(args.local_range), args.xy_inflation_cells,
                 args.z_inflation_cells, args.aging_frames, args.virtual_ceiling)
    if cfg.resolution <= 0.0 or cfg.aging_frames <= 0:
        _parser().error("resolution and aging-frames must be positive")
    terminal_cell = _cell(terminal, cfg)
    in_map = _in_map_point(terminal, cfg) and _in_map_cell(terminal_cell, cfg)
    ceiling = cfg.virtual_ceiling > -0.5 and terminal[2] >= cfg.virtual_ceiling
    print(f"BAG {args.bag}")
    print(f"terminal xyz=({terminal[0]:.6f},{terminal[1]:.6f},{terminal[2]:.6f}) "
          f"cell={terminal_cell} in_map={in_map} ceiling_block={ceiling}")
    print("CONFIG offline proxy: origin=(%.3f,%.3f,%.3f) size=(%.1f,%.1f,%.1f) "
          "res=%.3f local_range=(%.1f,%.1f,%.1f) xy_inflation=±%dcells "
          "z_inflation=±%dcells aging=%d virtual_ceiling=%.2f" %
          (*cfg.origin, *cfg.size, cfg.resolution, *cfg.local_range,
           cfg.xy_inflation_cells, cfg.z_inflation_cells, cfg.aging_frames,
           cfg.virtual_ceiling))
    for line in _log_lines(args.log):
        print("LOG " + line)
    try:
        clouds, obstacles, states, clocks = _load_bag(args.bag)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"topics: clouds={len(clouds)} obstacles={len(obstacles)} "
          f"uav_state={len(states)} clock={len(clocks)}")
    if clocks:
        print("clock ROS range=%.9f..%.9f (bag-record %.9f..%.9f)" %
              (clocks[0].stamp_s or 0.0, clocks[-1].stamp_s or 0.0,
               clocks[0].record_s, clocks[-1].record_s))
    if not clouds:
        print("error: no /pointcloud_nonground messages", file=sys.stderr)
        return 2

    if args.ros_time is not None:
        ref_kind, ref = "ros", args.ros_time
        selected = [c for c in clouds if (c.stamp_s or c.record_s) <= ref + 1.0e-6]
    elif args.wall_time is not None:
        ref_kind, ref = "bag-record", args.wall_time
        selected = [c for c in clouds if c.record_s <= ref + 1.0e-6]
    else:
        ref_kind, ref = "latest", clouds[-1].stamp_s or clouds[-1].record_s
        selected = list(clouds)
    if not selected:
        print(f"error: no cloud at/before {ref_kind}={ref:.9f}", file=sys.stderr)
        return 2
    selected_ids = {id(item) for item in selected[-max(1, args.clouds):]}
    occupied = False
    terminal_age: int | None = None
    summaries: list[CloudSummary] = []
    for index, cloud in enumerate(selected, 1):
        state = _state_for(cloud, states)
        obstacle = _obstacle_for(cloud, obstacles, args.obstacle_slop)
        summary, occupied, terminal_age = _simulate_cloud(
            index, cloud, state, obstacle, terminal_cell, terminal,
            occupied, terminal_age, cfg, args.prediction_match_tol)
        if id(cloud) in selected_ids:
            summaries.append(summary)
    print(f"reference {ref_kind}={ref:.9f}; clouds_before={len(selected)}; "
          f"showing_last={len(summaries)}")
    for item in summaries:
        pose = "-" if item.pose is None else "(" + ",".join(f"{v:.3f}" for v in item.pose) + ")"
        print("cloud#%d ros=%s record=%.9f obs=%s frame=%s points=%d local=%d "
              "direct=%d pred=%d pred_hit=%d provenance=%s tail_start=%s "
              "tail_max_err=%s occupied=%s age=%s pose=%s reason=%s" %
              (item.index, _fmt_time(item.stamp_s), item.record_s,
               _fmt_time(item.obstacle_stamp_s), item.frame,
               item.points, item.local_points, item.direct_hits,
               item.prediction_count, item.prediction_hits, item.prediction_provenance,
               "-" if item.prediction_tail_start is None else str(item.prediction_tail_start),
               "-" if item.prediction_tail_max_error is None else f"{item.prediction_tail_max_error:.3g}",
               item.occupied_after,
               "-" if item.terminal_age is None else str(item.terminal_age), pose,
               item.reason))
        for point_index, point, label in item.direct_examples:
            print("  HIT point_index=%d point=(%.6f,%.6f,%.6f) source=%s" %
                  (point_index, *point, label))
        for obstacle_id, step, time_s, point in item.prediction_examples:
            print("  PRED_HIT id=%d step=%d t=%.3f point=(%.6f,%.6f,%.6f)" %
                  (obstacle_id, step, time_s, *point))
    final_cloud = selected[-1]
    _print_neighborhood(
        final_cloud, _obstacle_for(final_cloud, obstacles, args.obstacle_slop), obstacles,
        terminal, args.neighborhood_seconds, args.neighborhood_radius)
    print(f"FINAL terminal_cell={terminal_cell} occupied={occupied} "
          f"terminal_age={'-' if terminal_age is None else terminal_age}")
    print("LIMIT: this is a deterministic bag/header-stamp geometry check. It cannot "
          "prove live planner callback arrival, ROS-clock freshness, executor ordering, "
          "or that a cloud was accepted by GridMap. prediction-tail-confirmed means the "
          "entire serialized cloud tail matched same-header /obstacles prediction points "
          f"within {PREDICTION_STRICT_TOL:g}m; it still is not live callback provenance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
