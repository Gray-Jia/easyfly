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

"""Primitive-only upright fixture ground clearance, independent of tag data."""

import math
from pathlib import Path
import xml.etree.ElementTree as ET

from .geometry import apply, attitude


def numbers(text, count):
    """Parse exact finite numeric vectors, never replace malformed values."""
    try:
        values = [float(value) for value in text.split()]
    except (AttributeError, ValueError) as error:
        raise ValueError("finite SDF numeric values required") from error
    if len(values) != count or not all(math.isfinite(value) for value in values):
        raise ValueError("finite SDF vector with exact dimension required")
    return values


def pose(element):
    """Absent poses use the SDF parent-frame zero convention."""
    poses = element.findall("pose")
    if len(poses) > 1 or (poses and poses[0].attrib):
        raise ValueError("ambiguous or attributed pose unsupported")
    return numbers(poses[0].text, 6) if poses else [0.0] * 6


def read_model(model_sdf):
    """Read one explicit model without resolving paths from ambient environment."""
    if isinstance(model_sdf, (str, Path)):
        root = ET.parse(model_sdf).getroot()
    elif isinstance(model_sdf, ET.ElementTree):
        root = model_sdf.getroot()
    elif isinstance(model_sdf, ET.Element):
        root = model_sdf
    else:
        raise ValueError("SDF Path or XML root required")
    models = [root] if root.tag == "model" else root.findall("model") if root.tag == "sdf" else []
    if len(models) != 1:
        raise ValueError("one flat SDF model required")
    model = models[0]
    if model.find("scale") is not None or "scale" in model.attrib:
        raise ValueError("model scale unsupported")
    if model.findall(".//model") or model.findall(".//frame"):
        raise ValueError("inline nested models/frames unsupported")
    for element in model.iter():
        if any(
            key in element.attrib
            for key in ("relative_to", "frame", "attached_to", "expressed_in", "placement_frame")
        ):
            raise ValueError("explicit SDF frame references unsupported")
    return model


def compose(position, rotation, local):
    """Compose a parent transform and a local SDF RPY pose."""
    offset = apply(rotation, local[:3])
    new_position = tuple(position[i] + offset[i] for i in range(3))
    local_rotation = attitude(*local[3:])
    new_rotation = tuple(
        tuple(
            sum(rotation[row][k] * local_rotation[k][column] for k in range(3))
            for column in range(3)
        )
        for row in range(3)
    )
    return new_position, new_rotation


def collision_geometry(model, position, rotation, includes, stack=()):
    """Recursively enumerate explicit primitive geometry with composed poses."""
    if len(stack) > 16:
        raise ValueError("include recursion exceeds bounded depth")
    names = [link.get("name") for link in model.findall("link")]
    if any(not name for name in names) or len(set(names)) != len(names):
        raise ValueError("unique named links required")
    for link in model.findall("link"):
        link_position, link_rotation = compose(position, rotation, pose(link))
        for collision in link.findall("collision"):
            center, collision_rotation = compose(link_position, link_rotation, pose(collision))
            yield center[2], collision_rotation, collision.findall("geometry")
    for include in model.findall("include"):
        if include.attrib or any(
            child.tag not in ("uri", "pose", "name", "static") for child in include
        ):
            raise ValueError("include override/scale/frame options unsupported")
        uris = include.findall("uri")
        if len(uris) != 1 or not uris[0].text or uris[0].text not in includes:
            raise ValueError("include requires an explicit URI-to-model mapping")
        uri = uris[0].text
        if uri in stack:
            raise ValueError("cyclic include graph")
        child = read_model(includes[uri])
        if pose(child) != [0.0] * 6:
            raise ValueError("nonzero included model pose has ambiguous override semantics")
        child_position, child_rotation = compose(position, rotation, pose(include))
        yield from collision_geometry(
            child, child_position, child_rotation, includes, stack + (uri,)
        )


def fixture_ground_z(model_sdf, include_models=None):
    """
    Return upright base_link rest z = minus lowest collision z.

    Accept Path/string, ElementTree or XML root plus an explicit include URI map.
    The top base_link pose must be zero; included models may have no collisions.
    No tag, visual geometry, ambient model search or dynamic ground contact is used.
    """
    model = read_model(model_sdf)
    pose(model)  # Validate, but model world placement does not change base-relative extents.
    links = model.findall("link")
    names = [link.get("name") for link in links]
    if (
        any(not name for name in names)
        or len(set(names)) != len(names)
        or names.count("base_link") != 1
    ):
        raise ValueError("unique named links and one base_link required")
    if any(pose(link) != [0.0] * 6 for link in links if link.get("name") == "base_link"):
        raise ValueError("nonzero base_link pose unsupported")
    lowest = math.inf
    for center_z, rotation, geometry in collision_geometry(
        model, (0.0, 0.0, 0.0), attitude(0.0, 0.0, 0.0), include_models or {}
    ):
        if len(geometry) != 1 or len(geometry[0]) != 1:
            raise ValueError("one collision primitive required")
        primitive = geometry[0][0]
        if geometry[0].attrib or primitive.attrib:
            raise ValueError("attributed geometry unsupported")
        if primitive.tag == "box" and [item.tag for item in primitive] == ["size"]:
            dimensions = numbers(primitive.findtext("size"), 3)
            extent = sum(abs(rotation[2][i]) * dimensions[i] / 2 for i in range(3))
        elif primitive.tag == "cylinder" and sorted(item.tag for item in primitive) == [
            "length",
            "radius",
        ]:
            radius = numbers(primitive.findtext("radius"), 1)[0]
            length = numbers(primitive.findtext("length"), 1)[0]
            dimensions = [radius, length]
            axis = abs(rotation[2][2])
            extent = length * axis / 2 + radius * math.sqrt(max(0.0, 1 - axis * axis))
        elif primitive.tag == "sphere" and [item.tag for item in primitive] == ["radius"]:
            dimensions = numbers(primitive.findtext("radius"), 1)
            extent = dimensions[0]
        else:
            raise ValueError("unsupported collision geometry")
        if any(value <= 0 for value in dimensions):
            raise ValueError("positive collision dimensions required")
        if not math.isfinite(center_z) or not math.isfinite(extent):
            raise ValueError("nonfinite collision projection")
        lowest = min(lowest, center_z - extent)
    if not math.isfinite(lowest) or lowest >= 0:
        raise ValueError("collision geometry must extend below base_link origin")
    return -lowest
