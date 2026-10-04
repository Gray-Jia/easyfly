"""Expand the service entrypoint without starting any process."""
import importlib.util
from pathlib import Path

from launch import LaunchContext
from launch.actions import IncludeLaunchDescription, OpaqueFunction
from launch_ros.utilities import evaluate_parameters
import pytest

PATH = Path(__file__).resolve().parents[1] / 'launch/platform.launch.py'


def entrypoint():
    spec = importlib.util.spec_from_file_location('platform_launch', PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_service_entrypoint_clock_and_profile():
    module = entrypoint()
    context = LaunchContext()
    context.launch_configurations.update(profile='navigation_dev', use_sim_time='true',
                                          mission_directory='/tmp/example-catalog', start_mission_executor='false')
    nodes = module.service_nodes(context)
    assert len(nodes) == 3
    parameters = [evaluate_parameters(context, node._Node__parameters) for node in nodes]
    assert all(group[0]['use_sim_time'] is True for group in parameters)
    assert parameters[0][1]['profile'] == 'navigation_dev'
    assert parameters[2][1]['mission_directory'] == '/tmp/example-catalog'
    description = module.generate_launch_description()
    include = next(e for e in description.entities if isinstance(e, IncludeLaunchDescription))
    guard = next(e for e in description.entities if isinstance(e, OpaqueFunction))
    assert description.entities.index(guard) < description.entities.index(include)
    assert not include.condition.evaluate(context)
    context.launch_configurations['profile'] = 'hardware_unverified'
    with pytest.raises(ValueError, match='non-launchable'):
        module.service_nodes(context)
