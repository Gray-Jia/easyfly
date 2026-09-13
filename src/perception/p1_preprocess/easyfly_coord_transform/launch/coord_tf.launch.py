"""P1 坐标变换节点启动: odom→base_link 动态 TF + /odom"""
from launch import LaunchDescription
from launch_ros.actions import ComposableNodeContainer
from launch_ros.descriptions import ComposableNode


def generate_launch_description():
    container = ComposableNodeContainer(
        name="coord_container",
        namespace="",
        package="rclcpp_components",
        executable="component_container",
        composable_node_descriptions=[
            ComposableNode(
                package="easyfly_coord_transform",
                plugin="easyfly_coord_transform::OdomTfPublisher",
                name="odom_tf_publisher",
                parameters=[{"use_sim_time": True}],
            ),
        ],
        output="screen",
    )
    return LaunchDescription([container])
