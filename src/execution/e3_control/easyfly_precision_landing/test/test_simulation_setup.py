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

"""Pure isolated preparation regression; never execute PX4 or a ROS goal."""

import hashlib
import importlib.util
import os
from pathlib import Path
import shlex

import pytest


PACKAGE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "simulation_setup",
    PACKAGE / "easyfly_precision_landing/simulation_setup.py",
)
SETUP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SETUP)
PROFILE = (PACKAGE / "config/d5_fastdds.xml").read_bytes()


@pytest.fixture
def source(tmp_path):
    """Provide inert fake ELF bytes and realistic input layout, never run them."""
    root = tmp_path / "original PX4"
    build = root / "build/px4_sitl_default"
    for directory in (
        "bin",
        "etc/init.d-posix",
        "build_gazebo-classic",
        "rootfs",
    ):
        (build / directory).mkdir(parents=True)
    (root / "Tools").mkdir()
    (root / "test_data").mkdir()
    binary = build / "bin/px4"
    binary.write_bytes(b"\x7fELFfake-inert")
    binary.chmod(0o755)
    (build / "etc/init.d-posix/rcS").write_text("source fixture\n")
    (
        build / "build_gazebo-classic/libgazebo_mavlink_interface.so"
    ).write_bytes(b"plugin")
    (build / "rootfs/parameters.bson").write_bytes(b"original parameters")
    return root


def test_staging_isolated_and_quoted_without_mutating_original(
    source, tmp_path
):
    """Preserve every input byte and use only the isolated writable rootfs."""
    before = {
        str(p.relative_to(source)): p.read_bytes()
        for p in source.rglob("*")
        if p.is_file()
    }
    destination = tmp_path / "new staging"
    result = SETUP.prepare_staging(source, destination)
    assert SETUP.validate_staging(destination) == result
    wrapper = Path(result["wrapper"])
    command = shlex.split(wrapper.read_text().splitlines()[1])
    assert command == [
        "exec",
        result["binary"],
        "-w",
        result["rootfs"],
        "-s",
        str(destination / "build/px4_sitl_default/etc/init.d-posix/rcS"),
        "$@",
    ]
    assert os.access(wrapper, os.X_OK)
    assert not (Path(result["rootfs"]) / "parameters.bson").exists()
    assert (
        Path(result["rootfs"]) / "etc"
    ).resolve() == source / "build/px4_sitl_default/etc"
    assert (destination / "Tools").resolve() == source / "Tools"
    after = {
        str(p.relative_to(source)): p.read_bytes()
        for p in source.rglob("*")
        if p.is_file()
    }
    assert before == after
    with pytest.raises(FileExistsError):
        SETUP.prepare_staging(source, destination)


@pytest.mark.parametrize(
    "missing",
    [
        "bin/px4",
        "etc/init.d-posix/rcS",
        "build_gazebo-classic/libgazebo_mavlink_interface.so",
    ],
)
def test_missing_source_rejected_before_writes(source, tmp_path, missing):
    """Invalid source inputs must not create a partially valid staging tree."""
    (source / "build/px4_sitl_default" / missing).unlink()
    destination = tmp_path / "stage"
    with pytest.raises(ValueError):
        SETUP.prepare_staging(source, destination)
    assert not destination.exists()


def test_unsafe_destination_and_wrapper_source_rejected(source, tmp_path):
    """Reject source-tree writes, symlink aliasing, nonempty and broad output."""
    for path in (source, source / "stage", Path("/"), Path.home(), Path.cwd()):
        with pytest.raises(ValueError):
            SETUP.prepare_staging(source, path)
    alias = tmp_path / "alias"
    alias.symlink_to(source, target_is_directory=True)
    with pytest.raises(ValueError):
        SETUP.prepare_staging(source, alias / "stage")
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "keep").write_text("keep")
    with pytest.raises(FileExistsError):
        SETUP.prepare_staging(source, occupied)
    assert (occupied / "keep").read_text() == "keep"
    (source / "build/px4_sitl_default/bin/px4").write_text(
        "#!/bin/sh\nexit 0\n"
    )
    with pytest.raises(ValueError):
        SETUP.prepare_staging(source, tmp_path / "stage")


def test_profile_freezes_exact_bytes_and_local_environment(tmp_path):
    """Freeze one validated profile, preserving source bytes and global env."""
    source = tmp_path / "source.xml"
    source.write_bytes(PROFILE)
    frozen = tmp_path / "frozen.xml"
    environment = dict(os.environ)
    result = SETUP.freeze_fastdds(source, frozen)
    assert result["sha256"] == hashlib.sha256(PROFILE).hexdigest()
    assert source.read_bytes() == frozen.read_bytes() == PROFILE
    assert dict(os.environ) == environment
    assert result["env"]["RMW_IMPLEMENTATION"] == "rmw_fastrtps_cpp"
    assert result["env"]["FASTRTPS_DEFAULT_PROFILES_FILE"] == str(frozen)
    assert result["budget"]["segment_size"] == 67108864
    with pytest.raises(FileExistsError):
        SETUP.freeze_fastdds(source, frozen)
    assert frozen.read_bytes() == PROFILE


@pytest.mark.parametrize(
    "old,new",
    [
        (b"fastRTPS_Profiles", b"wrong"),
        (b'is_default_profile="true"', b'is_default_profile="false"'),
        (
            b"<transport_id>d5_shm</transport_id>",
            b"<transport_id>missing</transport_id>",
        ),
        (b"<type>SHM</type>", b"<type>TCPv4</type>"),
        (b"4194304", b"1000"),
        (b"67108864", b"4194304"),
        (b"512", b"0"),
        (b"<useBuiltinTransports>false", b"<useBuiltinTransports>true"),
    ],
)
def test_well_formed_but_wrong_transport_rejected(old, new):
    """XML syntax alone does not establish transport selection or image budget."""
    data = PROFILE.replace(old, new, 1)
    with pytest.raises(ValueError):
        SETUP.validate_fastdds(data)


@pytest.mark.parametrize(
    "data",
    [b"<profiles/>", b"bad", b"x" * 65537, b"<!DOCTYPE profiles><profiles/>"],
)
def test_plain_bounded_profile_required(data):
    """No arbitrary XML, external entities or unbounded profile retention."""
    with pytest.raises(ValueError):
        SETUP.validate_fastdds(data)


def test_explicit_smaller_profile_with_image_headroom_is_valid():
    """Budgets need cover an image, not duplicate the bundled XML verbatim."""
    data = (
        PROFILE.replace(b"4194304", b"1048576")
        .replace(b"67108864", b"2097152")
        .replace(b"512", b"16")
    )
    assert SETUP.validate_fastdds(data)["maxMessageSize"] == 1048576


@pytest.mark.parametrize("change", ["manifest", "wrapper", "rootfs", "tools"])
def test_changed_isolation_proof_rejected(source, tmp_path, change):
    """A generated tree cannot retain proof after path or wrapper alteration."""
    stage = tmp_path / "stage"
    result = SETUP.prepare_staging(source, stage)
    if change == "manifest":
        Path(result["manifest"]).write_text("{}")
    elif change == "wrapper":
        Path(result["wrapper"]).write_text(
            '#!/bin/sh\nexec /original/px4 "$@"\n'
        )
    elif change == "rootfs":
        rootfs = Path(result["rootfs"])
        for link in rootfs.iterdir():
            link.unlink()
        rootfs.rmdir()
        rootfs.symlink_to(
            source / "build/px4_sitl_default/rootfs", target_is_directory=True
        )
    else:
        (stage / "Tools").unlink()
        (stage / "Tools").mkdir()
    with pytest.raises(ValueError):
        SETUP.validate_staging(stage)


def test_handmade_staging_without_manifest_rejected(tmp_path):
    """Never accept an arbitrary binary directory as independent simulation."""
    stage = tmp_path / "manual"
    stage.mkdir()
    with pytest.raises(ValueError):
        SETUP.validate_staging(stage)
