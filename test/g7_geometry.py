"""纯 Python 的 G7 几何验收辅助函数。

保持这里无 ROS 依赖，便于在没有 SITL 的环境中验证 N2 的安全距离计算。
"""

import math
from dataclasses import dataclass


def obstacle_observation_rejection_reason(
        observation, vehicle_xy, min_distance, max_distance, max_size,
        min_visible_height=0.15):
    """Return the reason an obstacle observation is unsafe to anchor on.

    The vertical extent is the visible slice of an obstacle, not its presumed
    full height.  A 0.15m floor admits the observed MID-360 pillar slices
    while finite values, distance, and horizontal-size bounds remain strict.
    ``None`` means the observation is a valid candidate.
    """
    try:
        values = tuple(float(value) for value in observation)
        vehicle = tuple(float(value) for value in vehicle_xy)
    except (TypeError, ValueError):
        return "nonfinite"
    if len(values) != 5 or len(vehicle) != 2:
        return "nonfinite"
    if not all(math.isfinite(value) for value in values + vehicle):
        return "nonfinite"
    center_x, center_y, size_x, size_y, size_z = values
    distance = math.hypot(center_x - vehicle[0], center_y - vehicle[1])
    if not (min_distance <= distance <= max_distance):
        return "distance"
    if not (0.05 <= size_x <= max_size and 0.05 <= size_y <= max_size):
        return "xy_size"
    if size_z < min_visible_height:
        return "visible_height"
    return None


def signed_clearance_to_aabb(x, y, center_x, center_y, size_x, size_y,
                             inflate_radius):
    """返回点到膨胀 AABB 的有符号距离（外部为正、内部为负）。"""
    half_x = max(0.0, float(size_x)) / 2.0 + max(0.0, float(inflate_radius))
    half_y = max(0.0, float(size_y)) / 2.0 + max(0.0, float(inflate_radius))
    dx = abs(float(x) - float(center_x)) - half_x
    dy = abs(float(y) - float(center_y)) - half_y
    if dx <= 0.0 and dy <= 0.0:
        return -min(-dx, -dy)
    return math.hypot(max(dx, 0.0), max(dy, 0.0))


def min_clearance_to_aabb(samples, center_x, center_y, size_x, size_y,
                          inflate_radius):
    """计算轨迹点和相邻线段到膨胀 AABB 的最小有符号间距。"""
    distances = [
        signed_clearance_to_aabb(x, y, center_x, center_y,
                                 size_x, size_y, inflate_radius)
        for x, y in samples
    ]
    return min(distances + [
        segment_clearance_to_aabb(
            samples[i], samples[i + 1], center_x, center_y,
            size_x, size_y, inflate_radius)
        for i in range(len(samples) - 1)
    ]) if distances else float("nan")


def _point_segment_distance(point, first, second):
    """返回二维点到线段的欧氏距离。"""
    px, py = point
    ax, ay = first
    bx, by = second
    vx, vy = bx - ax, by - ay
    length_sq = vx * vx + vy * vy
    if length_sq <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / length_sq))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def _segments_intersect(first, second, third, fourth):
    """判断二维闭线段是否相交（含端点）。"""
    def cross(a, b, c):
        return ((b[0] - a[0]) * (c[1] - a[1]) -
                (b[1] - a[1]) * (c[0] - a[0]))

    def on_segment(a, b, point):
        return (min(a[0], b[0]) - 1e-9 <= point[0] <= max(a[0], b[0]) + 1e-9 and
                min(a[1], b[1]) - 1e-9 <= point[1] <= max(a[1], b[1]) + 1e-9)

    values = (cross(first, second, third), cross(first, second, fourth),
              cross(third, fourth, first), cross(third, fourth, second))
    if (values[0] * values[1] < 0.0 and values[2] * values[3] < 0.0):
        return True
    return ((abs(values[0]) <= 1e-9 and on_segment(first, second, third)) or
            (abs(values[1]) <= 1e-9 and on_segment(first, second, fourth)) or
            (abs(values[2]) <= 1e-9 and on_segment(third, fourth, first)) or
            (abs(values[3]) <= 1e-9 and on_segment(third, fourth, second)))


def _segment_segment_distance(first, second, third, fourth):
    if _segments_intersect(first, second, third, fourth):
        return 0.0
    return min(_point_segment_distance(first, third, fourth),
               _point_segment_distance(second, third, fourth),
               _point_segment_distance(third, first, second),
               _point_segment_distance(fourth, first, second))


def segment_clearance_to_aabb(first, second, center_x, center_y, size_x, size_y,
                              inflate_radius):
    """返回线段到膨胀 AABB 的有符号最小 clearance。

    线段穿过足迹时返回负值；否则返回线段到四条足迹边的精确二维距离，
    不会因稀疏 UAV 位置采样漏掉中间的穿越。
    """
    half_x = max(0.0, float(size_x)) / 2.0 + max(0.0, float(inflate_radius))
    half_y = max(0.0, float(size_y)) / 2.0 + max(0.0, float(inflate_radius))
    min_x, max_x = float(center_x) - half_x, float(center_x) + half_x
    min_y, max_y = float(center_y) - half_y, float(center_y) + half_y
    edges = [
        ((min_x, min_y), (max_x, min_y)),
        ((max_x, min_y), (max_x, max_y)),
        ((max_x, max_y), (min_x, max_y)),
        ((min_x, max_y), (min_x, min_y)),
    ]
    if any(signed_clearance_to_aabb(x, y, center_x, center_y,
                                    size_x, size_y, inflate_radius) < 0.0
           for x, y in (first, second)):
        # Both endpoints inside is already a violation; a segment that starts
        # outside and enters is caught by the edge intersection below.
        return -1e-9
    if any(_segments_intersect(first, second, edge[0], edge[1]) for edge in edges):
        return -1e-9
    return min(_segment_segment_distance(first, second, edge[0], edge[1])
               for edge in edges)


def min_trajectory_clearance_to_aabb(samples, center_x, center_y, size_x, size_y,
                                     inflate_radius):
    """Explicit name for continuous trajectory clearance checking."""
    return min_clearance_to_aabb(
        samples, center_x, center_y, size_x, size_y, inflate_radius)


@dataclass
class ObstacleCluster:
    """纯数据的障碍时序聚类，供 N2 验收和离线回归使用。

    同一消息不会把两个障碍合并；跨消息只有在较细的关联半径内才会
    合并。尺寸取 max 而不是平均值，避免偶发小尺寸观测低估膨胀足迹。
    """

    count: int = 0
    sum_x: float = 0.0
    sum_y: float = 0.0
    max_size_x: float = 0.0
    max_size_y: float = 0.0
    max_size_z: float = 0.0
    last_sequence: int = -1

    @property
    def center_x(self):
        return self.sum_x / self.count if self.count else float("nan")

    @property
    def center_y(self):
        return self.sum_y / self.count if self.count else float("nan")

    def add(self, observation, sequence):
        cx, cy, sx, sy, sz = (float(v) for v in observation)
        self.count += 1
        self.sum_x += cx
        self.sum_y += cy
        self.max_size_x = max(self.max_size_x, sx)
        self.max_size_y = max(self.max_size_y, sy)
        self.max_size_z = max(self.max_size_z, sz)
        self.last_sequence = sequence


def update_obstacle_clusters(clusters, observations, sequence,
                             association_radius=0.6):
    """将一个新鲜障碍消息并入 clusters 并返回同一列表。

    ``observations`` 元素为 ``(center_x, center_y, size_x, size_y, size_z)``。
    同一 sequence 不复用同一个 cluster，从而保留相邻独立障碍；关联半径
    小于旧版 1.5m 网格尺度，抗抖与分离之间的取舍可在单元测试中验证。
    """
    for observation in observations:
        if not all(math.isfinite(float(v)) for v in observation):
            continue
        cx, cy = float(observation[0]), float(observation[1])
        candidates = [
            (math.hypot(cx - c.center_x, cy - c.center_y), i)
            for i, c in enumerate(clusters)
            if c.last_sequence != sequence and
            math.hypot(cx - c.center_x, cy - c.center_y) <= association_radius
        ]
        if candidates:
            _, index = min(candidates)
            clusters[index].add(observation, sequence)
        else:
            cluster = ObstacleCluster()
            cluster.add(observation, sequence)
            clusters.append(cluster)
    return clusters


@dataclass
class JumpGuardModel:
    """与 C++ jumpGuard 相同安全契约的纯逻辑模型。

    测试重点是 dt 来自相邻观测且拒绝帧也推进观测时钟，而位移始终
    对比最后接受位置。
    """

    max_target_speed: float = 3.0
    max_target_jump: float = 2.0
    jump_guard_margin: float = 0.5
    max_observation_gap: float = 1.0

    def __post_init__(self):
        self.accepted = {}
        self.observed_at = {}

    def observe(self, track_id, position, timestamp):
        position = tuple(float(v) for v in position)
        previous = self.observed_at.get(track_id)
        dt = 0.1 if previous is None else float(timestamp) - previous
        if not math.isfinite(dt) or dt < 0.01:
            dt = 0.01
        dt = min(dt, max(0.01, self.max_observation_gap))
        # 更新发生在判定之前，故拒绝帧也会影响下一帧相邻周期。
        self.observed_at[track_id] = float(timestamp)
        if not all(math.isfinite(v) for v in position):
            return False
        if track_id not in self.accepted:
            self.accepted[track_id] = position
            return True
        step = math.dist(position, self.accepted[track_id])
        allowed = min(self.max_target_jump,
                      self.max_target_speed * dt + self.jump_guard_margin)
        if step > allowed:
            return False
        self.accepted[track_id] = position
        return True


class WaypointLifecycleModel:
    """用于回归测试的最小 child-goal 生命周期状态机。"""

    IDLE = "IDLE"
    SENDING = "SENDING"
    ACTIVE = "ACTIVE"
    CANCELING = "CANCELING"

    def __init__(self):
        self.state = self.IDLE

    def start_send(self):
        if self.state != self.IDLE:
            return False
        self.state = self.SENDING
        return True

    def resolve_send(self, accepted):
        if self.state != self.SENDING:
            return False
        self.state = self.ACTIVE if accepted else self.IDLE
        return True

    def request_cancel(self):
        if self.state == self.SENDING:
            # pending send 不能丢 future；等待解析后再进入 ACTIVE/CANCELING。
            return True
        if self.state == self.ACTIVE:
            self.state = self.CANCELING
            return True
        return self.state == self.CANCELING

    def terminal(self):
        if self.state != self.CANCELING:
            return False
        self.state = self.IDLE
        return True

    @property
    def may_issue(self):
        return self.state == self.IDLE
