"""P1 标定节点启动: 静态 TF 发布 + 内参校验"""
from launch import LaunchDescription
from launch_ros.actions import ComposableNodeContainer
from launch_ros.descriptions import ComposableNode


def generate_launch_description():
    container = ComposableNodeContainer(
        name="calib_container",
        namespace="",
        package="rclcpp_components",
        executable="component_container",
        composable_node_descriptions=[
            ComposableNode(
                package="easyfly_camera_calib",
                plugin="easyfly_camera_calib::CalibTfPublisher",
                name="calib_tf_publisher",
                parameters=[{"use_sim_time": True}],
            ),
            ComposableNode(
                package="easyfly_camera_calib",
                plugin="easyfly_camera_calib::CameraInfoChecker",
                name="camera_info_checker",
                parameters=[{"use_sim_time": True}],
            ),
        ],
        output="screen",
    )
    return LaunchDescription([container])
