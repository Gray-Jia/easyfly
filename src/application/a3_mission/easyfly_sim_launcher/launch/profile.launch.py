"""D0 development entrypoint; no automatic flight goal and no hardware launch."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from easyfly_params.configuration import PROFILES, ensure_launchable, load_profile
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription, LogInfo, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def _launch_profile(context):
    profile = load_profile(LaunchConfiguration("profile").perform(context))
    ensure_launchable(profile)
    if profile["entrypoint"] == "base":
        package, filename = "easyfly_sim_launcher", "easyfly_sim.launch.py"
    else:
        package, filename = "easyfly_px4_sitl", "perception_sitl.launch.py"
    source = Path(get_package_share_directory(package)) / "launch" / filename
    include = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(source)),
        launch_arguments=profile["launch_arguments"].items(),
    )
    message = f"D0 profile={profile['name']} readiness={profile['readiness']}"
    if profile.get("note"):
        message += ": " + profile["note"]
    # Parent generic config_file/use_sim_time overrides must not pollute child defaults.
    return [LogInfo(msg=message), GroupAction(
        scoped=True, forwarding=False, actions=[include])]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("profile", default_value="base_sim", choices=PROFILES),
        OpaqueFunction(function=_launch_profile),
    ])
