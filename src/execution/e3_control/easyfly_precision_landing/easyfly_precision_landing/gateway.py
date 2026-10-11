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

"""Accepted-only compatibility entrance; full lifecycle uses PrecisionLand."""

import math
import threading
import time
import uuid

from easyfly_msgs.action import PrecisionLand
from easyfly_msgs.srv import (
    GetActionOwnership,
    GetCapabilities,
    TriggerLanding,
)
from rcl_interfaces.msg import ParameterDescriptor
import rclpy
from rclpy.action import ActionClient
from rclpy.callback_groups import (
    MutuallyExclusiveCallbackGroup,
    ReentrantCallbackGroup,
)
from rclpy.clock import Clock, ClockType
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.impl.implementation_singleton import rclpy_implementation
from rclpy.node import Node
from unique_identifier_msgs.msg import UUID


def compatible(request):
    """Reject unsupported XY/speed instead of silently ignoring them."""
    return (
        math.isnan(request.landing_x)
        and math.isnan(request.landing_y)
        and math.isfinite(request.landing_speed)
        and request.landing_speed == 0.0
    )


class LandingGateway(Node):
    """Keep unknown admission/recursive ownership locked until real evidence."""

    def __init__(self):
        super().__init__("landing_gateway")
        descriptor = ParameterDescriptor(read_only=True)
        self.tag_id = self.declare_parameter(
            "selected_tag_id", -1, descriptor
        ).value
        self.budget = self.declare_parameter(
            "operation_timeout_s", 120.0, descriptor
        ).value
        self.admission_budget = self.declare_parameter(
            "admission_timeout_s", 3.0, descriptor
        ).value
        if (
            not math.isfinite(self.budget)
            or not 0 < self.budget <= 3600
            or not math.isfinite(self.admission_budget)
            or not 0 < self.admission_budget <= 10
        ):
            raise ValueError("invalid compatibility gateway timeouts")
        self.lock = threading.RLock()
        self.identity = ""
        self.terminal = False
        self.query = None
        self.query_deadline = 0.0
        self.backend = None
        self.backend_receipt = 0.0
        self.backend_query = None
        self.backend_query_deadline = 0.0
        self.clients_group = ReentrantCallbackGroup()
        self.services_group = MutuallyExclusiveCallbackGroup()
        self.action = ActionClient(
            self,
            PrecisionLand,
            "/precision_land",
            callback_group=self.clients_group,
        )
        self.owner = self.create_client(
            GetActionOwnership,
            "/precision_landing/ownership",
            callback_group=self.clients_group,
        )
        self.backend_client = self.create_client(
            GetCapabilities,
            "/platform/precision_landing/capabilities",
            callback_group=self.clients_group,
        )
        self.service = self.create_service(
            TriggerLanding,
            "/trigger_landing",
            self.trigger,
            callback_group=self.services_group,
        )
        self.capability = self.create_service(
            GetCapabilities,
            "/platform/landing_trigger/capabilities",
            self.capabilities,
            callback_group=self.clients_group,
        )
        self.timer = self.create_timer(
            0.1,
            self.poll_release,
            clock=Clock(clock_type=ClockType.STEADY_TIME),
            callback_group=self.clients_group,
        )

    def trigger(self, request, response):
        """Return actual admission, never landing success or a timeout fiction."""
        if not compatible(request):
            response.message = (
                "unsupported: both XY must be NaN and landing_speed must be 0"
            )
            return response
        with self.lock:
            if self.identity or self.tag_id < 0:
                response.message = "busy_or_tag_not_configured"
                return response
            if (
                not self.action.server_is_ready()
                or not self.owner.service_is_ready()
            ):
                response.message = "precision_backend_unavailable"
                return response
            identity = uuid.uuid4()
            self.identity = identity.hex
            self.terminal = False
            goal = PrecisionLand.Goal(tag_id=self.tag_id, timeout=self.budget)
            try:
                future = self.action.send_goal_async(
                    goal, goal_uuid=UUID(uuid=list(identity.bytes))
                )
                future.add_done_callback(self.admitted)
            except Exception as error:
                # A send exception cannot establish that no remote goal exists.
                response.message = (
                    "admission_unknown:" + identity.hex + ":" + str(error)
                )
                return response
        deadline = time.monotonic() + self.admission_budget
        while (
            rclpy.ok(context=self.context)
            and not future.done()
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        if not future.done():
            response.message = (
                "admission_pending:"
                + identity.hex
                + "; use PrecisionLand/ownership"
            )
            return response
        try:
            handle = future.result()
            response.accepted = handle is not None and handle.accepted
            response.message = (
                "accepted_not_landed:" if response.accepted else "rejected:"
            ) + identity.hex
        except Exception as error:
            response.message = (
                "admission_unknown:" + identity.hex + ":" + str(error)
            )
        return response

    def admitted(self, future):
        """Record a real rejection or subscribe to the exact accepted result."""
        with self.lock:
            try:
                handle = future.result()
                if handle is None or not handle.accepted:
                    self.identity = ""
                    return
                handle.get_result_async().add_done_callback(self.completed)
            except Exception:
                pass  # Unknown remote state remains locked, not locally released.

    def completed(self, future):
        """Start ownership polling on a public result without releasing the lock."""
        with self.lock:
            try:
                if future.result() is not None:
                    self.terminal = True
            except Exception:
                pass

    def poll_release(self):
        """Require the exact UUID RELEASED response even after a public terminal."""
        with self.lock:
            wall = time.monotonic()
            if self.backend_query is not None:
                if self.backend_query.done():
                    try:
                        self.backend = self.backend_query.result()
                        self.backend_receipt = wall
                    except Exception:
                        self.backend = None
                    self.backend_query = None
                elif wall > self.backend_query_deadline:
                    self.backend_client.remove_pending_request(
                        self.backend_query
                    )
                    self.backend_query = None
                    self.backend = None
            elif self.backend_client.service_is_ready():
                self.backend_query = self.backend_client.call_async(
                    GetCapabilities.Request()
                )
                self.backend_query_deadline = wall + 0.5
            if not self.identity or not self.terminal:
                return
            if self.query is not None:
                if self.query.done():
                    try:
                        response = self.query.result()
                        if (
                            response is not None
                            and response.goal_id == self.identity
                            and response.state
                            == GetActionOwnership.Response.RELEASED
                        ):
                            self.identity = ""
                    except Exception:
                        pass
                    self.query = None
                elif time.monotonic() > self.query_deadline:
                    self.owner.remove_pending_request(self.query)
                    self.query = None
                return
            if self.owner.service_is_ready():
                self.query = self.owner.call_async(
                    GetActionOwnership.Request(goal_id=self.identity)
                )
                self.query_deadline = time.monotonic() + 1.0

    def capabilities(self, _request, response):
        """Readiness refers to admission capability, not landing completion."""
        with self.lock:
            response.header.stamp = self.get_clock().now().to_msg()
            response.names = ["precision_landing_trigger"]
            response.implemented = [True]
            backend_ready = False
            if (
                self.backend is not None
                and time.monotonic() - self.backend_receipt <= 0.5
            ):
                for name, ready in zip(self.backend.names, self.backend.ready):
                    backend_ready |= name == "precision_landing" and ready
            response.ready = [
                not self.identity
                and self.tag_id >= 0
                and backend_ready
                and self.action.server_is_ready()
                and self.owner.service_is_ready()
            ]
            response.details = [
                "accepted only; use /precision_land for feedback/cancel/result; "
                "pending_uuid=" + self.identity
            ]
        return response


def main(args=None):
    """Use separate executor callbacks while the bounded service waits."""
    rclpy.init(args=args)
    node = None
    executor = MultiThreadedExecutor(num_threads=3)
    try:
        node = LandingGateway()
        executor.add_node(node)
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    except rclpy_implementation.RCLError:
        if rclpy.ok():
            raise
    finally:
        executor.shutdown(timeout_sec=2.0)
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
