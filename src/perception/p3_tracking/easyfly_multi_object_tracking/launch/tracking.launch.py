"""M4 多目标跟踪节点启动"""
from launch import LaunchDescription
from launch_ros.actions import ComposableNodeContainer
from launch_ros.descriptions import ComposableNode


def generate_launch_description():
    container = ComposableNodeContainer(
        name="tracking_container",
        namespace="",
        package="rclcpp_components",
        executable="component_container",
        composable_node_descriptions=[
            ComposableNode(
                package="easyfly_multi_object_tracking",
                plugin="easyfly_multi_object_tracking::TrackingNode",
                name="easyfly_multi_object_tracking",
                parameters=[{"use_sim_time": True}],
            ),
        ],
        output="screen",
    )
    return LaunchDescription([container])
