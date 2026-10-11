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

"""Real kernel locks and launch failure propagation, with no flight processes."""

import gc
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from launch import LaunchDescription, LaunchService
from launch.actions import (
    DeclareLaunchArgument,
    EmitEvent,
    ExecuteProcess,
    OpaqueFunction,
    RegisterEventHandler,
    TimerAction,
)
from launch.event_handlers import OnProcessIO
from launch.events import Shutdown

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE))
from easyfly_px4_sitl.session_guard import (  # noqa: E402
    SessionReservation,
    guarded_launch,
    guarded_session,
    master_port,
    require_free_port,
)


class SessionGuardTests(unittest.TestCase):
    def test_local_uri_validation(self):
        for uri in (
            "http://localhost:11345",
            "http://127.0.0.1:11355/",
            "http://[::1]:11357",
        ):
            self.assertGreater(master_port(uri), 0)
        for uri in (
            "http://192.0.2.1:11345",
            "localhost:11345",
            "http://localhost",
            "http://localhost:0",
            "http://localhost:65536",
            "http://localhost:abc",
            "http://localhost:11345/world",
            "http://u@localhost:11345",
        ):
            with self.assertRaises(RuntimeError, msg=uri):
                master_port(uri)

    def test_foreign_tcp_or_udp_listener_refused_without_connecting(self):
        for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
            with socket.socket(socket.AF_INET, kind) as listener:
                listener.bind(("127.0.0.1", 0))
                if kind == socket.SOCK_STREAM:
                    listener.listen()
                port = listener.getsockname()[1]
                with self.assertRaisesRegex(RuntimeError, "unavailable"):
                    require_free_port(port, kind, "existing owner")
            require_free_port(port, kind, "released owner")

    def test_lock_blocks_other_process_and_stale_file_does_not_block(self):
        with tempfile.TemporaryDirectory() as directory:
            owner = SessionReservation(directory)
            with patch("easyfly_px4_sitl.session_guard.require_free_port"):
                owner.acquire("http://localhost:11345")
            try:
                code = (
                    "from unittest.mock import patch; "
                    "from easyfly_px4_sitl.session_guard import SessionReservation; "
                    'p=patch("easyfly_px4_sitl.session_guard.require_free_port"); '
                    "p.start(); "
                    f'SessionReservation({directory!r}).acquire("http://localhost:11355")'
                )
                env = dict(
                    os.environ,
                    PYTHONPATH=str(PACKAGE)
                    + os.pathsep
                    + os.environ.get("PYTHONPATH", ""),
                )
                second = subprocess.run(
                    [sys.executable, "-c", code],
                    env=env,
                    capture_output=True,
                    timeout=4,
                )
                self.assertNotEqual(second.returncode, 0)
                self.assertIn(b"Another EasyFly SITL session", second.stderr)
            finally:
                owner.close()
            self.assertTrue((Path(directory) / "single-vehicle.lock").exists())
            with patch("easyfly_px4_sitl.session_guard.require_free_port"):
                next_owner = SessionReservation(directory)
                next_owner.acquire("http://localhost:11345")
                next_owner.close()

    def test_port_failure_releases_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            first = SessionReservation(directory)
            with patch(
                "easyfly_px4_sitl.session_guard.require_free_port",
                side_effect=RuntimeError("occupied"),
            ):
                with self.assertRaisesRegex(RuntimeError, "occupied"):
                    first.acquire("http://localhost:11345")
            self.assertIsNone(first.fd)
            with patch("easyfly_px4_sitl.session_guard.require_free_port"):
                other = SessionReservation(directory)
                other.acquire("http://localhost:11345")
                other.close()

    def test_symlink_or_public_lock_directory_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory) / "public"
            public.mkdir(mode=0o755)
            with self.assertRaisesRegex(RuntimeError, "private"):
                SessionReservation(public).acquire("http://localhost:11345")
            alias = Path(directory) / "alias"
            alias.symlink_to(public, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, "private"):
                SessionReservation(alias).acquire("http://localhost:11345")

    def test_failed_or_early_core_exit_aborts_timers_and_returns_failure(self):
        for command, role in (
            (["/bin/false"], "model spawn"),
            (["/bin/true"], "Gazebo"),
            (["/bin/true"], "PX4"),
        ):
            with self.subTest(
                role=role
            ), tempfile.TemporaryDirectory() as directory:
                reached = []

                def late(context):
                    reached.append(True)

                process = ExecuteProcess(cmd=command, output="screen")
                service = LaunchService()
                service.include_launch_description(
                    LaunchDescription(
                        [
                            guarded_session(
                                [
                                    process,
                                    TimerAction(
                                        period=0.3,
                                        actions=[
                                            OpaqueFunction(function=late)
                                        ],
                                    ),
                                ],
                                {process: role},
                                lock_directory=directory,
                            ),
                        ]
                    )
                )
                with patch("easyfly_px4_sitl.session_guard.require_free_port"):
                    self.assertEqual(service.run(), 1)
                    self.assertFalse(reached)
                    # Even after Shutdown the owning context must retain its
                    # lock until teardown; pending/late children cannot race it.
                    other = SessionReservation(directory)
                    with self.assertRaisesRegex(RuntimeError, "Another"):
                        other.acquire("http://localhost:11345")
                    del service
                    del process
                    gc.collect()
                    other.acquire("http://localhost:11345")
                    other.close()

    def test_occupied_master_refuses_all_startup_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as owner:
                owner.bind(("127.0.0.1", 0))
                owner.listen()
                reached = []

                def startup(context):
                    reached.append(True)

                service = LaunchService()
                service.context.environment[
                    "GAZEBO_MASTER_URI"
                ] = f"http://localhost:{owner.getsockname()[1]}"
                service.include_launch_description(
                    LaunchDescription(
                        [
                            guarded_session(
                                [OpaqueFunction(function=startup)],
                                {},
                                lock_directory=directory,
                            ),
                        ]
                    )
                )
                self.assertEqual(service.run(), 1)
                self.assertFalse(reached)
                del service
                gc.collect()

    def test_core_exit_after_shutdown_preserves_failure_and_holds_lock(self):
        for returncode in (0, 3):
            with self.subTest(
                returncode=returncode
            ), tempfile.TemporaryDirectory() as directory:
                script = (
                    "import signal,sys,time; "
                    f"signal.signal(signal.SIGINT, lambda *_: sys.exit({returncode})); "
                    "print('ready', flush=True); time.sleep(5)"
                )
                process = ExecuteProcess(
                    cmd=[sys.executable, "-u", "-c", script]
                )

                def ready(event):
                    if b"ready" in event.text:
                        return [
                            EmitEvent(event=Shutdown(reason="fixture stop"))
                        ]

                service = LaunchService()
                service.include_launch_description(
                    LaunchDescription(
                        [
                            guarded_session(
                                [
                                    RegisterEventHandler(
                                        OnProcessIO(
                                            target_action=process,
                                            on_stdout=ready,
                                        )
                                    ),
                                    process,
                                ],
                                {process: "Gazebo"},
                                lock_directory=directory,
                            ),
                        ]
                    )
                )
                with patch("easyfly_px4_sitl.session_guard.require_free_port"):
                    self.assertEqual(service.run(), int(returncode != 0))
                    self.assertTrue(service.context.is_shutdown)
                    other = SessionReservation(directory)
                    with self.assertRaisesRegex(RuntimeError, "Another"):
                        other.acquire("http://localhost:11345")
                    del service
                    del process
                    gc.collect()
                    other.acquire("http://localhost:11345")
                    other.close()

    def test_successful_spawn_continues_and_cli_arguments_remain_visible(self):
        declarations = [
            DeclareLaunchArgument("world", default_value="empty.world")
        ]
        visible = guarded_launch(declarations, {}).get_launch_arguments()
        self.assertEqual([arg.name for arg in visible], ["world"])
        with tempfile.TemporaryDirectory() as directory:
            reached = []

            def late(context):
                reached.append(True)

            process = ExecuteProcess(cmd=["/bin/true"])
            service = LaunchService()
            service.include_launch_description(
                LaunchDescription(
                    [
                        guarded_session(
                            [
                                process,
                                TimerAction(
                                    period=0.05,
                                    actions=[OpaqueFunction(function=late)],
                                ),
                            ],
                            {process: "model spawn"},
                            lock_directory=directory,
                        ),
                    ]
                )
            )
            with patch("easyfly_px4_sitl.session_guard.require_free_port"):
                self.assertEqual(service.run(), 0)
            self.assertTrue(reached)
            del service
            del process
            gc.collect()


if __name__ == "__main__":
    unittest.main()
