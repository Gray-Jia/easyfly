"""Query snapshots with explicit readiness, freshness and geometry validity."""
import copy
import math
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy
from rcl_interfaces.msg import ParameterDescriptor, SetParametersResult
from easyfly_msgs.msg import Target3DArray, ObstacleInfoArray, UAVState
from easyfly_msgs.srv import GetPerception, GetCapabilities


class PerceptionServices(Node):
    def __init__(self):
        super().__init__('easyfly_perception_srvs')
        readonly = ParameterDescriptor(read_only=True)
        self.declare_parameter('targets_topic', '/target_positions', readonly)
        self.declare_parameter('obstacles_topic', '/obstacles', readonly)
        self.declare_parameter('max_age', 1.0)
        result = self.validate_parameters([self.get_parameter('max_age')])
        if not result.successful:
            raise ValueError(result.reason)
        self.add_on_set_parameters_callback(self.validate_parameters)
        self.snapshots = {}
        self.state = None
        self.state_time = 0.0
        self.topics = {k: self.get_parameter(k + '_topic').value for k in ('targets', 'obstacles')}
        self.create_subscription(Target3DArray, self.topics['targets'],
                                 lambda m: self.receive('targets', m), 10)
        self.create_subscription(ObstacleInfoArray, self.topics['obstacles'],
                                 lambda m: self.receive('obstacles', m),
                                 QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.create_subscription(UAVState, '/uav_state', self.receive_state, 10)
        self.create_service(GetPerception, '/platform/perception/query', self.query)
        self.create_service(GetCapabilities, '/platform/perception/capabilities', self.capabilities)

    @staticmethod
    def validate_parameters(parameters):
        for p in parameters:
            if p.name != 'max_age' or type(p.value) is not float or not math.isfinite(p.value) or not 0.05 <= p.value <= 10:
                return SetParametersResult(successful=False, reason='only max_age(double, 0.05..10s) is writable')
        return SetParametersResult(successful=True)

    def receive(self, kind, message):
        self.snapshots[kind] = (message, time.monotonic())

    def receive_state(self, message):
        self.state, self.state_time = message, time.monotonic()

    def header_health(self, header, received):
        stamp = header.stamp
        if header.frame_id != 'odom' or stamp.sec < 0 or stamp.nanosec >= 1000000000 or (stamp.sec == 0 and stamp.nanosec == 0):
            return GetPerception.Response.INVALID, -1.0
        age = (self.get_clock().now().nanoseconds - stamp.sec * 1000000000 - stamp.nanosec) / 1e9
        if age < -0.2:
            return GetPerception.Response.INVALID, age
        if max(age, time.monotonic() - received) > self.get_parameter('max_age').value:
            return GetPerception.Response.STALE, age
        return GetPerception.Response.VALID, age

    def health(self, kind):
        if kind not in self.snapshots:
            return GetPerception.Response.NOT_READY, -1.0
        msg, received = self.snapshots[kind]
        status, age = self.header_health(msg.header, received)
        if status != GetPerception.Response.VALID:
            return status, age
        items = msg.targets if kind == 'targets' else msg.obstacles
        if len(items) > 10000:
            return GetPerception.Response.INVALID, age
        for item in items:
            h, _ = self.header_health(item.header, received)
            if h != GetPerception.Response.VALID:
                return h, age
            if kind == 'targets':
                valid = item.position_valid and all(math.isfinite(v) for v in (
                    item.position_x, item.position_y, item.position_z, item.confidence, item.distance))
                valid = valid and 0 <= item.confidence <= 1 and item.distance >= 0
            else:
                valid = all(math.isfinite(v) for v in (
                    item.center_x, item.center_y, item.center_z, item.size_x, item.size_y, item.size_z,
                    item.velocity_x, item.velocity_y, item.velocity_z))
                valid = valid and min(item.size_x, item.size_y, item.size_z) >= 0
            if not valid:
                return GetPerception.Response.INVALID, age
        return status, age

    def query(self, request, response):
        response.age_sec = -1.0
        if request.kind not in self.topics:
            response.status, response.message = response.UNSUPPORTED, 'supported kinds: targets, obstacles'
            return response
        response.source_topic = self.topics[request.kind]
        if not math.isfinite(request.range_limit) or request.range_limit > 10000:
            response.status, response.message = response.INVALID, 'invalid query range'
            return response
        response.status, response.age_sec = self.health(request.kind)
        response.message = {0: 'not_ready', 1: 'valid', 2: 'stale', 3: 'invalid'}[response.status]
        if request.kind in self.snapshots:
            response.observed_at = self.snapshots[request.kind][0].header.stamp
        if response.status != response.VALID:
            return response
        msg = copy.deepcopy(self.snapshots[request.kind][0])
        if request.range_limit > 0:
            if self.state is None:
                response.status, response.message = response.NOT_READY, 'range query requires UAVState'
                return response
            s = self.state
            state_status, _ = self.header_health(s.header, self.state_time)
            if state_status != response.VALID or not s.connected or not s.pose_valid or not all(
                    math.isfinite(v) for v in (s.position_x, s.position_y, s.position_z)):
                response.status = state_status if state_status != response.VALID else response.INVALID
                response.message = 'invalid or stale query origin'
                return response
            def within(item):
                xyz = (item.position_x, item.position_y, item.position_z) if request.kind == 'targets' else (
                    item.center_x, item.center_y, item.center_z)
                return math.dist(xyz, (s.position_x, s.position_y, s.position_z)) <= request.range_limit
            if request.kind == 'targets':
                msg.targets = [item for item in msg.targets if within(item)]
            else:
                msg.obstacles = [item for item in msg.obstacles if within(item)]
        if request.kind == 'targets':
            response.targets = msg
        else:
            response.obstacles = msg
        return response

    def capabilities(self, _request, response):
        response.header.stamp = self.get_clock().now().to_msg()
        response.header.frame_id = 'odom'
        response.names = ['targets', 'obstacles', 'landing_detection', 'precision_landing']
        response.implemented = [True, True, False, False]
        response.ready = [self.health(k)[0] == GetPerception.Response.VALID for k in ('targets', 'obstacles')] + [False, False]
        response.details = ['snapshot query; source may be absent', 'geometry snapshot; no motion commands',
                            'unsupported: planned D4', 'unsupported: planned D5']
        return response


def main():
    rclpy.init()
    node = PerceptionServices()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
