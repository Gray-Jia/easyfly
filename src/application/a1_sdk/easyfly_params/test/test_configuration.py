"""Behavior tests for invalid profiles and cross-package contract drift."""

from copy import deepcopy
from pathlib import Path
import shutil

import pytest
import yaml

from easyfly_params.configuration import ensure_launchable, load_profile, validate_workspace


PACKAGE = Path(__file__).resolve().parents[1]
WORKSPACE = PACKAGE.parents[3]
CONFIG = PACKAGE / "config"
SOURCE_FILES = (
    "perception/p4_fusion/easyfly_semantic_map/config/semantic_map.yaml",
    "perception/p1_preprocess/easyfly_pointcloud_filter/config/pointcloud_filter.yaml",
    "perception/p4_fusion/easyfly_pixel_to_3d/config/pixel_to_3d.yaml",
    "execution/e3_control/easyfly_flight_control/config/flight_control.yaml",
    "execution/e3_control/easyfly_flight_control/include/easyfly_flight_control/trajectory_startup_timeout.hpp",
    "execution/e2_planning/easyfly_local_planner/launch/local_planner.launch.py",
)


@pytest.mark.parametrize("name", ["base_sim", "full_perception", "navigation_dev", "landing_dev"])
def test_simulation_profiles(name):
    profile = load_profile(name, CONFIG)
    ensure_launchable(profile)
    assert profile["launch_arguments"]["headless"] == "true"
    assert not profile["capabilities"]["precision_landing"]
    if name == "landing_dev":
        assert profile["readiness"] == "preparation_only"


def test_hardware_can_be_inspected_but_never_launched():
    profile = load_profile("hardware_unverified", CONFIG)
    with pytest.raises(ValueError, match="non-launchable"):
        ensure_launchable(profile)


@pytest.mark.parametrize("name", ["../base_sim", "unknown", ""])
def test_unknown_profiles_rejected(name):
    with pytest.raises(ValueError, match="unknown profile"):
        load_profile(name, CONFIG)


@pytest.mark.parametrize("field,value", [
    ("headless", "true"), ("schema_version", True), ("entrypoint", "disabled"),
    ("environment", "hardware"), ("readiness", "unverified"), ("extra", 1),
])
def test_invalid_profile_fields(tmp_path, field, value):
    shutil.copytree(CONFIG, tmp_path / "config")
    path = tmp_path / "config/profiles/base_sim.yaml"
    profile = deepcopy(yaml.safe_load(path.read_text()))
    profile[field] = value
    path.write_text(yaml.safe_dump(profile))
    with pytest.raises(ValueError):
        load_profile("base_sim", tmp_path / "config")


def test_unimplemented_capability_rejected(tmp_path):
    shutil.copytree(CONFIG, tmp_path / "config")
    path = tmp_path / "config/profiles/landing_dev.yaml"
    profile = yaml.safe_load(path.read_text())
    profile["capabilities"]["precision_landing"] = True
    path.write_text(yaml.safe_dump(profile))
    with pytest.raises(ValueError, match="unimplemented"):
        load_profile("landing_dev", tmp_path / "config")


def test_source_defaults_match_frozen_contracts():
    assert len(validate_workspace(WORKSPACE, CONFIG)) == 10


@pytest.mark.parametrize("index,old,new", [
    (0, "max_nonground_points: 200000", "max_nonground_points: 400000"),
    (1, "output_frame: odom", "output_frame: map"),
    (2, "target_frame: odom", "target_frame: map"),
    (3, "trajectory_startup_grace: 8.0", "trajectory_startup_grace: 12.0"),
    (4, "kTrajectoryStreamTimeout = 0.5", "kTrajectoryStreamTimeout = 2.0"),
    (5, "'grid_map/ground_height': 0.5", "'grid_map/ground_height': 0.0"),
    (5, "default_value='3.2'", "default_value='5.0'"),
])
def test_cross_package_drift_rejected(tmp_path, index, old, new):
    for filename in SOURCE_FILES:
        target = tmp_path / "src" / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(WORKSPACE / "src" / filename, target)
    path = tmp_path / "src" / SOURCE_FILES[index]
    contents = path.read_text()
    assert old in contents
    path.write_text(contents.replace(old, new))
    with pytest.raises(ValueError, match="contract mismatch"):
        validate_workspace(tmp_path, CONFIG)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, -1])
def test_invalid_safety_values_rejected(tmp_path, value):
    shutil.copytree(CONFIG, tmp_path / "config")
    path = tmp_path / "config/safety_contracts.yaml"
    contracts = yaml.safe_load(path.read_text())
    contracts["trajectory_stream_timeout"] = value
    path.write_text(yaml.safe_dump(contracts))
    with pytest.raises(ValueError):
        load_profile("base_sim", tmp_path / "config")


@pytest.mark.parametrize("field,value", [
    ("schema_version", 1.0), ("max_nonground_points", 200000.0),
])
def test_integer_contract_fields_reject_equal_floats(tmp_path, field, value):
    shutil.copytree(CONFIG, tmp_path / "config")
    path = tmp_path / "config/safety_contracts.yaml"
    contracts = yaml.safe_load(path.read_text())
    contracts[field] = value
    path.write_text(yaml.safe_dump(contracts))
    with pytest.raises(ValueError, match="must be an integer"):
        load_profile("base_sim", tmp_path / "config")
