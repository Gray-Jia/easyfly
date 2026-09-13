"""M5 像素转 3D 节点启动"""
from launch import LaunchDescription
from launch_ros.actions import ComposableNodeContainer
from launch_ros.descriptions import ComposableNode


def generate_launch_description():
    container = ComposableNodeContainer(
        name="pixel_to_3d_container",
        namespace="",
        package="rclcpp_components",
        executable="component_container",
        composable_node_descriptions=[
            ComposableNode(
                package="easyfly_pixel_to_3d",
                plugin="easyfly_pixel_to_3d::PixelTo3dNode",
                name="easyfly_pixel_to_3d",
                parameters=[{"use_sim_time": True}],
            ),
        ],
        output="screen",
    )
    return LaunchDescription([container])
