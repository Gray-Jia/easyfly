"""Typed ROS parameter services and legacy JSON compatibility."""
import json
import time
import unittest

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rcl_interfaces.srv import SetParametersAtomically
from rclpy.parameter import Parameter
from easyfly_msgs.srv import QueryParams
from std_srvs.srv import Trigger
from easyfly_params.runtime import ParameterManager


class RuntimeTest(unittest.TestCase):
    def test_local_typed_parameters_are_atomic_and_exported(self):
        rclpy.init()
        manager = ParameterManager()
        node = rclpy.create_node('parameter_test')
        executor = SingleThreadedExecutor()
        executor.add_node(manager)
        executor.add_node(node)
        query = node.create_client(QueryParams, '/platform/params/query')
        typed = node.create_client(SetParametersAtomically, '/easyfly_params/set_parameters_atomically')
        export = node.create_client(Trigger, '/platform/params/export')

        def call(client, request):
            self.assertTrue(client.wait_for_service(timeout_sec=3))
            future = client.call_async(request)
            end = time.monotonic() + 3
            while not future.done() and time.monotonic() < end:
                executor.spin_once(timeout_sec=0.02)
            self.assertTrue(future.done())
            return future.result()

        try:
            result = call(query, QueryParams.Request(param_name='operator_note'))
            self.assertTrue(result.success)
            self.assertEqual(json.loads(result.current_value), '')
            result = call(query, QueryParams.Request(param_name='operator_note', param_value='"hello"'))
            self.assertTrue(result.success)
            result = call(query, QueryParams.Request(param_name='operator_note', param_value='""'))
            self.assertTrue(result.success)  # JSON empty string writes; empty request reads.
            result = call(query, QueryParams.Request(param_name='export_pretty', param_value='true'))
            self.assertTrue(result.success)
            self.assertFalse(call(query, QueryParams.Request(param_name='export_pretty', param_value='1')).success)
            self.assertTrue(manager.get_parameter('export_pretty').value)
            for value in ('null', '{}', 'not-json', 'NaN'):
                self.assertFalse(call(query, QueryParams.Request(param_name='operator_note', param_value=value)).success)
            for name in ('planning_floor', 'profile', 'unknown', '/flight_control/max_altitude'):
                self.assertFalse(call(query, QueryParams.Request(param_name=name, param_value='2')).success)
            result = call(typed, SetParametersAtomically.Request(parameters=[
                Parameter('operator_note', value='must not commit').to_parameter_msg(),
                Parameter('export_pretty', value=1).to_parameter_msg()]))
            self.assertFalse(result.result.successful)
            self.assertEqual(manager.get_parameter('operator_note').value, '')
            self.assertTrue(manager.get_parameter('export_pretty').value)
            result = call(export, Trigger.Request())
            self.assertTrue(result.success)
            effective = json.loads(result.message)
            self.assertEqual(effective['schema_version'], 1)
            self.assertEqual(effective['launch_arguments']['navigation_strategy'], 'combined')
            self.assertEqual(effective['contracts']['planning_ceiling'], 3.2)
        finally:
            executor.shutdown()
            node.destroy_node()
            manager.destroy_node()
            rclpy.shutdown()


if __name__ == '__main__':
    unittest.main()
