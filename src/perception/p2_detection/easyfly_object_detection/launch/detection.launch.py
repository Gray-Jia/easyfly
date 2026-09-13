"""P2 目标检测节点启动 (可独立于 perception_sitl 调试)"""
from launch import LaunchDescription
from launch_ros.actions import ComposableNodeContainer
from launch_ros.descriptions import ComposableNode


def generate_launch_description():
    container = ComposableNodeContainer(
        name="detection_container",
        namespace="",
        package="rclcpp_components",
        executable="component_container",
        composable_node_descriptions=[
            ComposableNode(
                package="easyfly_object_detection",
                plugin="easyfly_object_detection::DetectionNode",
                name="easyfly_object_detection",
                parameters=[{"use_sim_time": True}],
            ),
        ],
        output="screen",
    )
    return LaunchDescription([container])
