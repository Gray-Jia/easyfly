#!/usr/bin/env python3
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

"""Generate a separate D5 fixture SDF without modifying the production Iris."""

import argparse
import copy
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from ament_index_python.packages import get_package_share_directory


def prepare(destination, unused_camera_rate=30):
    """Add only a link-fixed down camera to a new, non-overwriting output."""
    if unused_camera_rate not in (1, 30):
        raise ValueError("explicit unused-camera fixture rates: 1 or 30 Hz")
    source = (
        Path(get_package_share_directory("easyfly_px4_sitl"))
        / "models/easyfly_iris/easyfly_iris.sdf"
    )
    tree = ET.parse(source)
    body = tree.find("./model/link[@name='base_link']")
    camera = copy.deepcopy(body.find("sensor[@name='color']"))
    camera.set("name", "down_color")
    # Below the body collision, while retaining pad visibility at handoff height.
    camera.find("pose").text = f"0 0 -0.08 0 {math.pi / 2} 0"
    camera.find("camera/noise/stddev").text = "0.0"
    plugin = camera.find("plugin")
    plugin.set("name", "down_camera_plugin")
    plugin.find("ros/namespace").text = "/camera_down"
    plugin.find("frame_name").text = "camera_down_optical_frame"
    body.append(camera)
    for name in ("color", "depth"):
        body.find(f"sensor[@name='{name}']/update_rate").text = str(
            unused_camera_rate
        )
    # Generated fixture only: the production model/file is never overwritten.
    with Path(destination).open("xb") as stream:
        tree.write(stream, encoding="utf-8", xml_declaration=True)


def main():
    """Require an explicit output path in the caller's fixture directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_sdf")
    parser.add_argument("--unused-camera-rate", type=int, default=30)
    args = parser.parse_args()
    prepare(args.output_sdf, args.unused_camera_rate)


if __name__ == "__main__":
    main()
