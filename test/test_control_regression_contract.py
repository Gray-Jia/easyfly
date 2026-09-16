#!/usr/bin/env python3
"""Static contracts for the T9 control-regression test harness.

These tests intentionally inspect ``control_regression.py`` instead of
importing it: the harness requires a sourced ROS 2 environment, while the
ordering and trajectory-ID rules must also be checkable in a plain Python
test run.
"""

import ast
from pathlib import Path
import unittest


SCRIPT = Path(__file__).with_name("control_regression.py")


def _method(cls, name):
    return next(
        node for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )


def _attr_call(node, receiver, method):
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == method
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == receiver
    )


class ControlRegressionContractTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")
        cls.module = ast.parse(cls.source, filename=str(SCRIPT))
        cls.runner = next(
            node for node in cls.module.body
            if isinstance(node, ast.ClassDef)
            and node.name == "RegressionRunner"
        )
        cls.synthetic = next(
            node for node in cls.module.body
            if isinstance(node, ast.ClassDef)
            and node.name == "_SyntheticTrajectory"
        )

    def test_synthetic_trajectory_id_is_allocated_per_start(self):
        start_line = _method(self.synthetic, "start_line")
        tick = _method(self.synthetic, "_tick")

        allocates_from_next = any(
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
                and target.attr == "_trajectory_id"
                for target in node.targets
            )
            and isinstance(node.value, ast.Attribute)
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "self"
            and node.value.attr == "_next_trajectory_id"
            for node in ast.walk(start_line)
        )
        increments_next = any(
            isinstance(node, ast.AugAssign)
            and isinstance(node.target, ast.Attribute)
            and isinstance(node.target.value, ast.Name)
            and node.target.value.id == "self"
            and node.target.attr == "_next_trajectory_id"
            and isinstance(node.op, ast.Add)
            for node in ast.walk(start_line)
        )
        trajectory_assignments = [
            node for node in ast.walk(tick)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Attribute)
                and target.attr == "trajectory_id"
                for target in node.targets
            )
        ]

        self.assertTrue(allocates_from_next,
                        "start_line must allocate a fresh trajectory ID")
        self.assertTrue(increments_next,
                        "start_line must advance the trajectory-ID counter")
        self.assertEqual(len(trajectory_assignments), 1)
        value = trajectory_assignments[0].value
        self.assertIsInstance(value, ast.Name)
        self.assertEqual(value.id, "trajectory_id")
        self.assertNotIn("msg.trajectory_id = 1", self.source)

    def test_follow_helper_is_a_runner_method_and_orders_goal_before_stream(self):
        helper = _method(self.runner, "_start_follow_stream")
        calls = list(ast.walk(helper))
        stop_calls = [node for node in calls if _attr_call(node, "pub", "stop")]
        send_calls = [
            node for node in calls
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "send_goal"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
        ]
        start_calls = [node for node in calls if _attr_call(node, "pub", "start_line")]

        self.assertEqual(len(stop_calls), 1)
        self.assertEqual(len(send_calls), 1)
        self.assertEqual(len(start_calls), 1)
        self.assertLess(stop_calls[0].lineno, send_calls[0].lineno)
        self.assertLess(send_calls[0].lineno, start_calls[0].lineno)

        rejected_guard = any(
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "gh"
            and len(node.test.ops) == 1
            and isinstance(node.test.ops[0], ast.Is)
            and len(node.test.comparators) == 1
            and isinstance(node.test.comparators[0], ast.Constant)
            and node.test.comparators[0].value is None
            and any(
                isinstance(child, ast.Return)
                and isinstance(child.value, ast.Constant)
                and child.value.value is None
                for child in ast.walk(node)
            )
            for node in calls
        )
        self.assertTrue(rejected_guard,
                        "rejected goals must return without starting the stream")

    def test_t9_uses_helper_without_pre_goal_warmup(self):
        t9 = _method(self.runner, "t9_follow_trajectory")
        helper_calls = [
            node for node in ast.walk(t9)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_start_follow_stream"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
        ]
        direct_stream_starts = [
            node for node in ast.walk(t9) if _attr_call(node, "pub", "start_line")
        ]
        half_second_sleeps = [
            node for node in ast.walk(t9)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "sleep"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == 0.5
        ]

        self.assertEqual(len(helper_calls), 3,
                         "T9a/T9b/T9c must all use the ordered helper")
        self.assertEqual(direct_stream_starts, [],
                         "T9 must not start a stream directly before its goal")
        self.assertEqual(half_second_sleeps, [],
                         "the old goal-before-stream warmup must stay removed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
