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

"""Isolate the actual nested admission routine, never start processes or ROS."""

import ast
from pathlib import Path
from types import SimpleNamespace

from easyfly_precision_landing import simulation
from easyfly_msgs.msg import UAVState
from gazebo_msgs.srv import GetEntityState
import pytest


def test_precision_start_follows_successful_reference_in_the_actual_entry():
    """Check straight-line ordering: a raised admission cannot reach precision start."""
    syntax = ast.parse(Path(simulation.__file__).read_text())
    main = next(item for item in syntax.body
                if isinstance(item, ast.FunctionDef) and item.name == "main")
    body = next(item.body for item in main.body if isinstance(item, ast.Try)
                and any(isinstance(statement, ast.Assign) and isinstance(statement.value, ast.Call)
                        and isinstance(statement.value.func, ast.Name)
                        and statement.value.func.id == "calibrate_ground_reference"
                        for statement in item.body))
    admission = next(index for index, statement in enumerate(body)
                     if isinstance(statement, ast.Assign) and isinstance(statement.value, ast.Call)
                     and isinstance(statement.value.func, ast.Name)
                     and statement.value.func.id == "calibrate_ground_reference")
    precision = next(index for index, statement in enumerate(body)
                     if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call)
                     and isinstance(statement.value.func, ast.Name)
                     and statement.value.func.id == "start"
                     and statement.value.args[0].value == "precision")
    assert admission < precision


@pytest.mark.parametrize("fault", ["armed", "disconnected", "moving", "timeout", "rewind"])
def test_bad_latest_reference_never_returns_an_admission(fault):
    """Exercise production sampling/cleanup with old good and latest bad evidence."""
    syntax = ast.parse(Path(simulation.__file__).read_text())
    routine = next(item for item in ast.walk(syntax)
                   if isinstance(item, ast.FunctionDef)
                   and item.name == "calibrate_ground_reference")
    good = UAVState(connected=True, pose_valid=True, attitude_valid=True,
                    velocity_valid=True, position_z=0.14)
    good.header.frame_id = "odom"
    good.header.stamp.sec = 10
    latest = UAVState(connected=True, pose_valid=True, attitude_valid=True,
                      velocity_valid=True, position_z=0.14)
    latest.header.frame_id = "odom"
    latest.header.stamp.sec = 10
    if fault == "armed":
        latest.armed = True
    elif fault == "disconnected":
        latest.connected = False
    elif fault == "moving":
        latest.velocity_z = 0.1
    entity = GetEntityState.Response(success=True)
    entity.header.frame_id = "world"
    entity.header.stamp.sec = 10
    entity.state.pose.position.z = 0.1
    cleaned = []
    future = SimpleNamespace(done=lambda: fault != "timeout", result=lambda: entity)
    client = SimpleNamespace(service_is_ready=lambda: True, call_async=lambda request: future,
                             remove_pending_request=lambda request: cleaned.append("pending"))
    clocks = iter([10000000000, 9900000000 if fault == "rewind" else 10000000000])
    clock = SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=next(clocks)))
    node = SimpleNamespace(create_client=lambda *args: client, get_clock=lambda: clock,
                           destroy_client=lambda item: cleaned.append("client"))

    def wait(predicate, budget):
        if not predicate():
            raise TimeoutError("synthetic read-only query timeout")

    namespace = dict(simulation.__dict__)
    namespace.update(node=node, report={}, ground_states=[(good, 100.0), (latest, 100.0)],
                     board_face_world_z=0.038, wait=wait,
                     expected_ground_z=0.1,
                     time=SimpleNamespace(monotonic=lambda: 100.0))
    exec(compile(ast.Module(body=[routine], type_ignores=[]), "<actual admission>", "exec"),
         namespace)
    with pytest.raises((ValueError, RuntimeError, TimeoutError)):
        namespace["calibrate_ground_reference"]()
    assert "ground_reference" not in namespace["report"]
    assert cleaned[-1] == "client"
    assert ("pending" in cleaned) is (fault == "timeout")
