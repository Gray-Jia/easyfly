#!/usr/bin/env python3
"""PX4 launch 路径选择的无 ROS 运行时副作用回归测试。"""

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
LAUNCH_FILES = (
    ROOT / "src/simulation/easyfly_px4_sitl/launch/px4_sitl.launch.py",
    ROOT / "src/simulation/easyfly_px4_sitl/launch/perception_sitl.launch.py",
)


def _load_launch_module(path):
    name = "_%s" % path.stem
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Px4DirResolutionTest(unittest.TestCase):

    def test_explicit_environment_overrides_all_default_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            explicit = home / "custom-px4"
            for name in ("PX4-Autopilot-1.16.2", "PX4-Autopilot-1.16.1",
                         "PX4-Autopilot"):
                (home / name).mkdir()
            for launch_file in LAUNCH_FILES:
                module = _load_launch_module(launch_file)
                with patch.dict(os.environ, {"HOME": str(home),
                                              "PX4_DIR": str(explicit)}):
                    self.assertEqual(module._resolve_px4_dir(), explicit)

    def test_defaults_are_selected_in_exact_version_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            v162 = home / "PX4-Autopilot-1.16.2"
            v161 = home / "PX4-Autopilot-1.16.1"
            base = home / "PX4-Autopilot"
            for launch_file in LAUNCH_FILES:
                v162.mkdir()
                v161.mkdir()
                base.mkdir()
                module = _load_launch_module(launch_file)
                with patch.dict(os.environ, {"HOME": str(home), "PX4_DIR": ""}):
                    self.assertEqual(module._resolve_px4_dir(), v162)
                    v162.rmdir()
                    self.assertEqual(module._resolve_px4_dir(), v161)
                    v161.rmdir()
                    self.assertEqual(module._resolve_px4_dir(), base)
                    base.rmdir()
                    self.assertEqual(module._resolve_px4_dir(), base)


if __name__ == "__main__":
    unittest.main()
