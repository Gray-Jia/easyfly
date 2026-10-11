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

"""Prepare explicit local simulation inputs; never start processes or set globals."""

import hashlib
import json
import os
from pathlib import Path
import shlex
import xml.etree.ElementTree as ET


NAMESPACE = "http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles"


def safe_destination(destination):
    """Reject broad, symlinked or malformed output paths before creating anything."""
    path = Path(destination).absolute()
    if any(ord(character) < 32 for character in str(path)):
        raise ValueError("control characters in destination")
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("symlink output path")
    path = path.resolve()
    if path in (Path("/"), Path.home(), Path.cwd()):
        raise ValueError("broad output target")
    return path


def prepare_staging(px4_dir, destination):
    """
    Create a fresh independent PX4 rootfs with an explicit -w/-s wrapper.

    Shared Tools, etc and plugins are read-only inputs by convention, not a
    filesystem read-only mount. This function never modifies those source trees.
    The returned wrapper must be used instead of executing the original binary
    directly when launching this staging tree.
    """
    source = Path(px4_dir).resolve(strict=True)
    build = source / "build/px4_sitl_default"
    binary = build / "bin/px4"
    script = build / "etc/init.d-posix/rcS"
    plugins = build / "build_gazebo-classic"
    tools = source / "Tools"
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError("executable PX4 binary required")
    with binary.open("rb") as stream:
        if stream.read(4) != b"\x7fELF":
            raise ValueError(
                "source must be the real ELF PX4, not a staging wrapper"
            )
    if not script.is_file() or not tools.is_dir() or not plugins.is_dir():
        raise ValueError("PX4 rcS, Tools and Gazebo plugin directory required")
    if not (plugins / "libgazebo_mavlink_interface.so").is_file():
        raise ValueError("PX4 Gazebo MAVLink plugin unavailable")
    destination = safe_destination(destination)
    if (
        destination == source
        or source in destination.parents
        or destination in source.parents
    ):
        raise ValueError("staging must be outside the source PX4 tree")
    if destination.exists() and (
        not destination.is_dir() or any(destination.iterdir())
    ):
        raise FileExistsError("staging destination must be new or empty")
    if not destination.parent.is_dir():
        raise ValueError("staging parent must already exist")
    destination.mkdir(exist_ok=True)
    staged_build = destination / "build/px4_sitl_default"
    rootfs = staged_build / "rootfs"
    rootfs.mkdir(parents=True)
    (staged_build / "bin").mkdir()
    (destination / "Tools").symlink_to(tools, target_is_directory=True)
    (staged_build / "etc").symlink_to(build / "etc", target_is_directory=True)
    (rootfs / "etc").symlink_to(build / "etc", target_is_directory=True)
    (staged_build / "build_gazebo-classic").symlink_to(
        plugins, target_is_directory=True
    )
    if (source / "test_data").is_dir():
        (rootfs / "test_data").symlink_to(
            source / "test_data", target_is_directory=True
        )
    wrapper = staged_build / "bin/px4"
    command = " ".join(
        shlex.quote(str(value))
        for value in (
            binary,
            "-w",
            rootfs,
            "-s",
            staged_build / "etc/init.d-posix/rcS",
        )
    )
    with wrapper.open("x", encoding="utf-8") as stream:
        stream.write("#!/bin/sh\nexec " + command + ' "$@"\n')
    wrapper.chmod(0o755)
    result = {
        "source": str(source),
        "staging": str(destination),
        "rootfs": str(rootfs),
        "wrapper": str(wrapper),
        "binary": str(binary),
        "rcS": str(script),
        "plugins": str(plugins),
    }
    manifest = destination / "easyfly_staging.json"
    result["manifest"] = str(manifest)
    with manifest.open("x", encoding="utf-8") as stream:
        json.dump(
            {"schema_version": 1, "independent_rootfs": True, **result},
            stream,
            indent=2,
        )
    return result


def validate_staging(destination):
    """
    Reject unproven binary trees and changed generated wrapper/path bindings.

    A manifest is structural isolation evidence, not a cryptographic signature
    or proof that an unrelated process cannot access the source filesystem.
    """
    destination = safe_destination(destination)
    manifest = destination / "easyfly_staging.json"
    if (
        manifest.is_symlink()
        or not manifest.is_file()
        or manifest.stat().st_size > 65536
    ):
        raise ValueError("bounded generated staging manifest required")
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
        source = Path(value["source"]).resolve(strict=True)
        build = source / "build/px4_sitl_default"
        staged = destination / "build/px4_sitl_default"
        expected = {
            "source": str(source),
            "staging": str(destination),
            "rootfs": str(staged / "rootfs"),
            "wrapper": str(staged / "bin/px4"),
            "binary": str(build / "bin/px4"),
            "rcS": str(build / "etc/init.d-posix/rcS"),
            "plugins": str(build / "build_gazebo-classic"),
            "manifest": str(manifest),
        }
        if value != {
            "schema_version": 1,
            "independent_rootfs": True,
            **expected,
        }:
            raise ValueError("staging manifest path mismatch")
        if (
            source == destination
            or source in destination.parents
            or destination in source.parents
        ):
            raise ValueError("source and staging must be independent")
        for directory in (
            destination / "build",
            staged,
            staged / "bin",
            staged / "rootfs",
        ):
            if directory.is_symlink() or not directory.is_dir():
                raise ValueError("independent staging directories required")
        for link, target in (
            (destination / "Tools", source / "Tools"),
            (staged / "etc", build / "etc"),
            (staged / "rootfs/etc", build / "etc"),
            (staged / "build_gazebo-classic", build / "build_gazebo-classic"),
        ):
            if not link.is_symlink() or link.resolve(
                strict=True
            ) != target.resolve(strict=True):
                raise ValueError("shared input binding changed")
        binary = Path(expected["binary"])
        with binary.open("rb") as stream:
            if stream.read(4) != b"\x7fELF" or not os.access(binary, os.X_OK):
                raise ValueError("real executable PX4 required")
        if (
            not Path(expected["rcS"]).is_file()
            or not (
                Path(expected["plugins"]) / "libgazebo_mavlink_interface.so"
            ).is_file()
        ):
            raise ValueError("staging source dependencies missing")
        wrapper = Path(expected["wrapper"])
        command = " ".join(
            shlex.quote(str(part))
            for part in (
                binary,
                "-w",
                staged / "rootfs",
                "-s",
                staged / "etc/init.d-posix/rcS",
            )
        )
        if (
            wrapper.is_symlink()
            or not os.access(wrapper, os.X_OK)
            or wrapper.read_text()
            != ("#!/bin/sh\nexec " + command + ' "$@"\n')
        ):
            raise ValueError("generated wrapper isolation arguments changed")
        return expected
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("invalid generated staging") from error


def validate_fastdds(data):
    """Validate the explicit same-host UDP/SHM image transport budget."""
    if (
        len(data) > 65536
        or b"<!DOCTYPE" in data.upper()
        or b"<!ENTITY" in data.upper()
    ):
        raise ValueError("bounded plain FastDDS XML required")
    try:
        root = ET.fromstring(data)
        prefix = "{" + NAMESPACE + "}"
        if root.tag != prefix + "profiles":
            raise ValueError("FastDDS profiles namespace required")
        participants = root.findall(prefix + "participant")
        defaults = [
            p for p in participants if p.get("is_default_profile") == "true"
        ]
        if len(defaults) != 1 or not defaults[0].get("profile_name"):
            raise ValueError("one named default participant required")
        participant = defaults[0]
        if (
            participant.findtext(
                prefix + "rtps/" + prefix + "useBuiltinTransports"
            )
            != "false"
        ):
            raise ValueError("explicit user transports required")
        descriptors = root.findall(
            prefix + "transport_descriptors/" + prefix + "transport_descriptor"
        )
        transports = {}
        for descriptor in descriptors:
            identity = descriptor.findtext(prefix + "transport_id")
            if not identity or identity in transports:
                raise ValueError("unique transport IDs required")
            transports[identity] = descriptor
        references = [
            e.text
            for e in participant.findall(
                prefix
                + "rtps/"
                + prefix
                + "userTransports/"
                + prefix
                + "transport_id"
            )
        ]
        if (
            len(references) != 2
            or len(set(references)) != 2
            or any(r not in transports for r in references)
        ):
            raise ValueError(
                "exact UDP and SHM user transport references required"
            )
        types = {
            transports[r].findtext(prefix + "type"): transports[r]
            for r in references
        }
        if set(types) != {"UDPv4", "SHM"}:
            raise ValueError("same-host UDPv4 and SHM required")
        shm = types["SHM"]
        budget = {
            field: int(shm.findtext(prefix + field, "0"))
            for field in (
                "maxMessageSize",
                "segment_size",
                "port_queue_capacity",
            )
        }
        if (
            budget["maxMessageSize"] < 640 * 480 * 3 + 4096
            or budget["segment_size"] < 2 * budget["maxMessageSize"]
            or budget["port_queue_capacity"] <= 0
        ):
            raise ValueError("insufficient explicit D5 image transport budget")
        return budget
    except (ET.ParseError, TypeError) as error:
        raise ValueError("invalid FastDDS XML") from error


def freeze_fastdds(source, frozen_path):
    """Freeze validated bytes without overwrite and return process-tree env only."""
    source = Path(source).resolve(strict=True)
    if not source.is_file() or source.stat().st_size > 65536:
        raise ValueError("bounded FastDDS profile file required")
    data = source.read_bytes()
    budget = validate_fastdds(data)
    frozen = safe_destination(frozen_path)
    if source == frozen or not frozen.parent.is_dir():
        raise ValueError("independent existing profile parent required")
    with frozen.open("xb") as stream:
        stream.write(data)
    return {
        "source": str(source),
        "frozen": str(frozen),
        "sha256": hashlib.sha256(data).hexdigest(),
        "budget": budget,
        "env": {
            "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp",
            "FASTRTPS_DEFAULT_PROFILES_FILE": str(frozen),
            "FASTDDS_DEFAULT_PROFILES_FILE": str(frozen),
        },
    }
