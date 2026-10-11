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

"""Pure fixture collisions, never tag-based heights or live aircraft physics."""

import importlib.util
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest


PACKAGE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "easyfly_precision_landing.collision_test_module",
    PACKAGE / "easyfly_precision_landing/simulation_collision.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def model(geometry, collision_pose="0 0 0 0 0 0", link_pose="0 0 0 0 0 0"):
    """Create only the supported SDF parent-frame collision layout."""
    return ET.fromstring(
        f'<sdf><model name="fixture"><link name="base_link"><pose>0 0 0 0 0 0</pose>'
        '<collision name="base"><geometry><box><size>.1 .1 .02</size></box></geometry>'
        f'</collision></link><link name="primitive"><pose>{link_pose}</pose>'
        f'<collision name="test"><pose>{collision_pose}</pose><geometry>{geometry}</geometry>'
        "</collision></link></model></sdf>"
    )


def test_repo_generated_fixture_has_055m_ground_base_height(tmp_path, monkeypatch):
    """Generate repository model; use an explicitly synthetic collision-free GPS leaf."""
    repository = PACKAGE.parents[2] / "simulation/easyfly_px4_sitl"
    source_model = repository / "models/easyfly_iris/easyfly_iris.sdf"
    original = source_model.read_bytes()
    spec = importlib.util.spec_from_file_location(
        "collision_prepare_fixture", PACKAGE / "scripts/prepare_down_camera.py"
    )
    prepare = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prepare)
    monkeypatch.setattr(prepare, "get_package_share_directory", lambda _name: str(repository))
    source = tmp_path / "down_iris.sdf"
    prepare.prepare(source)
    synthetic_gps_no_collision = ET.fromstring(
        '<model name="synthetic_collision_free_gps_fixture"><link name="sensor_fixture"/></model>'
    )
    includes = {
        "model://mid360": PACKAGE.parents[2]
        / "simulation/easyfly_gazebo_models/mid360/mid360.sdf",
        "model://gps": synthetic_gps_no_collision,
    }
    with pytest.raises(ValueError):
        MODULE.fixture_ground_z(source)
    assert MODULE.fixture_ground_z(source, includes) == pytest.approx(0.055)
    assert MODULE.fixture_ground_z(ET.parse(source), includes) == pytest.approx(0.055)
    assert MODULE.fixture_ground_z(source_model, includes) == pytest.approx(0.055)
    assert source_model.read_bytes() == original


@pytest.mark.parametrize(
    "geometry,rotation,expected",
    [
        ("<box><size>2 4 6</size></box>", "0 0 0", 3.0),
        ("<box><size>2 4 6</size></box>", f"0 {math.pi / 2} 0", 1.0),
        ("<cylinder><radius>2</radius><length>6</length></cylinder>", "0 0 0", 3.0),
        ("<cylinder><radius>2</radius><length>6</length></cylinder>", f"0 {math.pi / 2} 0", 2.0),
        ("<sphere><radius>2</radius></sphere>", ".3 .5 .7", 2.0),
    ],
)
def test_primitive_projection_accounts_for_collision_rotation(geometry, rotation, expected):
    """Use support-function extents for boxes, tilted cylinders and spheres."""
    assert MODULE.fixture_ground_z(model(geometry, "0 0 0 " + rotation)) == pytest.approx(expected)


def test_link_rotation_rotates_collision_translation_and_shape():
    """Link and collision poses compose instead of adding RPY angles."""
    root = model("<box><size>2 4 6</size></box>", "1 0 0 0 0 0", f"0 0 0 0 {math.pi / 2} 0")
    assert MODULE.fixture_ground_z(root) == pytest.approx(2.0)


@pytest.mark.parametrize(
    "geometry",
    [
        "<mesh><uri>fixture.obj</uri></mesh>",
        "<plane><normal>0 0 1</normal></plane>",
        "<box><size>1 2 nan</size></box>",
        "<sphere><radius>-1</radius></sphere>",
        "<box><size>1 2</size></box>",
        "<capsule><radius>1</radius></capsule>",
    ],
)
def test_unknown_or_nonfinite_primitives_are_rejected(geometry):
    """An unsupported collision cannot be silently ignored in the global minimum."""
    with pytest.raises(ValueError):
        MODULE.fixture_ground_z(model(geometry))


@pytest.mark.parametrize("change", ["base_pose", "relative", "frame", "nested", "bad_pose"])
def test_ambiguous_frame_layout_is_rejected(change):
    """Reject nonzero base transforms and any unimplemented frame graph."""
    root = model("<sphere><radius>1</radius></sphere>")
    if change == "base_pose":
        root.find("./model/link/pose").text = "0 0 .1 0 0 0"
    elif change == "relative":
        root.find("./model/link/pose").set("relative_to", "unknown")
    elif change == "frame":
        ET.SubElement(root.find("model"), "frame", {"name": "unknown"})
    elif change == "nested":
        ET.SubElement(root.find("model"), "model", {"name": "nested"})
    else:
        root.find("./model/link/pose").text = "0 0 0 0 0 inf"
    with pytest.raises(ValueError):
        MODULE.fixture_ground_z(root)


def test_explicit_include_composes_link_collision_pose_and_descends_recursively():
    """Include geometry must affect the minimum, not be silently dropped."""
    root = model("<sphere><radius>.02</radius></sphere>")
    parent = ET.fromstring(
        '<model name="parent"><pose>0 0 0 0 0 0</pose>'
        "<include><uri>model://leaf</uri><pose>0 0 -.2 0 0 0</pose></include></model>"
    )
    leaf = ET.fromstring(
        '<model name="leaf"><link name="not_base"><pose>0 0 -.05 0 0 0</pose>'
        '<collision name="c"><pose>0 0 -.05 0 0 0</pose>'
        "<geometry><sphere><radius>.1</radius></sphere></geometry>"
        "</collision></link></model>"
    )
    include = ET.SubElement(root.find("model"), "include")
    ET.SubElement(include, "uri").text = "model://parent"
    ET.SubElement(include, "pose").text = "0 0 -.3 0 0 0"
    assert MODULE.fixture_ground_z(
        root, {"model://parent": parent, "model://leaf": leaf}
    ) == pytest.approx(0.7)


def test_unknown_and_cyclic_includes_rejected():
    """Resolve only explicit caller assets, never environment or recursive cycles."""
    root = model("<sphere><radius>.02</radius></sphere>")
    include = ET.SubElement(root.find("model"), "include")
    ET.SubElement(include, "uri").text = "model://self"
    with pytest.raises(ValueError):
        MODULE.fixture_ground_z(root)
    with pytest.raises(ValueError):
        MODULE.fixture_ground_z(root, {"model://self": root})


@pytest.mark.parametrize("modifier", ["model_pose", "model_scale", "include_scale"])
def test_ambiguous_included_model_overrides_are_rejected(modifier):
    """Never guess SDF include override or model scaling semantics."""
    root = model("<sphere><radius>.02</radius></sphere>")
    include = ET.SubElement(root.find("model"), "include")
    ET.SubElement(include, "uri").text = "model://child"
    child = ET.fromstring('<model name="child"><link name="sensor"/></model>')
    if modifier == "model_pose":
        ET.SubElement(child, "pose").text = "0 0 .1 0 0 0"
    elif modifier == "model_scale":
        ET.SubElement(child, "scale").text = "2 2 2"
    else:
        ET.SubElement(include, "scale").text = "2 2 2"
    with pytest.raises(ValueError):
        MODULE.fixture_ground_z(root, {"model://child": child})
