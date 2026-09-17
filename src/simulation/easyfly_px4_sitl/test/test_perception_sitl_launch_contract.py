#!/usr/bin/env python3
"""Static launch contracts for reproducible G6 headless acceptance runs."""

from pathlib import Path


LAUNCH = (Path(__file__).resolve().parents[1] / "launch" / "perception_sitl.launch.py").read_text()


def require(needle: str) -> None:
    if needle not in LAUNCH:
        raise AssertionError(f"perception_sitl launch contract missing {needle!r}")


def main() -> None:
    for argument in (
        '"headless"',
        '"gzclient"',
        '"rviz"',
        '"debug_image"',
        '"detection_use_gpu"',
        '"detection_performance_log_period_s"',
        '"detection_input_qos_reliability"',
        '"detection_input_qos_depth"',
    ):
        require(f"DeclareLaunchArgument(\n        {argument}")

    require('UnlessCondition(LaunchConfiguration("headless"))')
    require("effective_debug_image = PythonExpression(")
    require("'false' if '")
    require('IfCondition(LaunchConfiguration("gzclient"))')
    require('IfCondition(LaunchConfiguration("rviz"))')
    require('"publish_debug_image": effective_debug_image')
    require('"use_gpu": LaunchConfiguration("detection_use_gpu")')
    require('"performance_log_period_s": LaunchConfiguration(')
    require('"input_qos_reliability": LaunchConfiguration(')
    require('"input_qos_depth": LaunchConfiguration(')
    require('px4_delayed = TimerAction(period=6.0, actions=[px4_sitl])')
    print("PASS perception_sitl headless/override contract")


if __name__ == "__main__":
    main()
