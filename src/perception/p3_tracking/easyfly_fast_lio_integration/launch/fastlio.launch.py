"""M3: fast_lio + map→odom TF 集成启动

用法:
  ros2 launch easyfly_fast_lio_integration fastlio.launch.py
  # 参数: config_file (默认 mid360.yaml), rviz (默认 false, 由 perception_sitl 统一开)

内容:
  - fast_lio::fastlio_mapping (上游 ROS2 版, config/mid360.yaml)
  - map_odom_tf (EasyFly 定制: SLAM odom + /odom → TF map→odom, 平滑)

前置 (由 perception_sitl 或手动提供):
  - /livox/lidar, /livox/imu (M0 仿真插件)
  - /odom (M1 easyfly_coord_transform, 需 /uav_state 即 mavros)
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, TimerAction
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import ComposableNodeContainer, Node
from launch_ros.descriptions import ComposableNode
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    use_sim_time = LaunchConfiguration('use_sim_time')
    config_file = LaunchConfiguration('config_file')

    declare_sim_time = DeclareLaunchArgument(
        'use_sim_time', default_value='true')
    declare_config = DeclareLaunchArgument(
        'config_file', default_value='mid360.yaml',
        description='fast_lio config (位于 fast_lio/config/)')

    fast_lio_node = Node(
        package='fast_lio',
        executable='fastlio_mapping',
        parameters=[PathJoinSubstitution([
            get_package_share_directory('fast_lio'), 'config', config_file]),
            {'use_sim_time': use_sim_time}],
        output='screen',
    )

    # map→odom TF (延后启动: 等 fast_lio 出 Odometry)
    map_odom_tf_container = ComposableNodeContainer(
        name="fastlio_integration_container",
        namespace="",
        package="rclcpp_components",
        executable="component_container",
        composable_node_descriptions=[
            ComposableNode(
                package="easyfly_fast_lio_integration",
                plugin="easyfly_fast_lio_integration::MapOdomTf",
                name="map_odom_tf",
                parameters=[{"use_sim_time": use_sim_time}],
            ),
        ],
        output="screen",
    )
    map_odom_delayed = TimerAction(period=5.0, actions=[map_odom_tf_container])

    return LaunchDescription([
        declare_sim_time,
        declare_config,
        fast_lio_node,
        map_odom_delayed,
    ])
