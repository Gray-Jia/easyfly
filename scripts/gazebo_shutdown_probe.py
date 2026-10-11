#!/usr/bin/env python3
# Copyright 2026 EasyFly Project
# Licensed under the Apache License, Version 2.0.
# You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
# Distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""One bounded, reserved sensor-only experiment; never starts PX4 or flies."""

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET


def fixture(iris, mid360, camera_library, duplicate):
    """Use unchanged camera/lidar rates; explicitly provoke a duplicate node."""
    root = ET.Element('sdf', version='1.6')
    world = ET.SubElement(root, 'world', name='shutdown_probe')
    physics = ET.SubElement(world, 'physics', name='default', type='ode')
    ET.SubElement(physics, 'max_step_size').text = '0.004'
    ET.SubElement(physics, 'real_time_update_rate').text = '250'
    model = ET.SubElement(world, 'model', name='sensor_fixture')
    ET.SubElement(model, 'static').text = 'true'
    link = ET.SubElement(model, 'link', name='camera_link')
    ET.SubElement(link, 'pose').text = '0 0 1 0 0 0'
    sensors = ET.parse(iris).findall('.//sensor')
    cameras = [s for s in sensors if s.get('type') in ('camera', 'depth')]
    if len(cameras) != 2:
        raise ValueError('expected the explicit two-camera iris fixture')
    for camera in cameras[:1] if duplicate else cameras:
        cloned = copy.deepcopy(camera)
        for plugin in cloned.findall('plugin'):
            plugin.set('filename', str(camera_library))
        link.append(cloned)
    if duplicate:
        cloned = copy.deepcopy(link[1])  # pose precedes the first camera
        cloned.set('name', 'duplicate_color_sensor')
        # Deliberately keep plugin name and ROS namespace identical.
        link.append(cloned)
    else:
        lidar = copy.deepcopy(ET.parse(mid360).find('model'))
        ET.SubElement(lidar, 'static').text = 'true'
        ET.SubElement(lidar, 'pose').text = '0 0 1 0 0 0'
        world.append(lidar)
    ET.indent(root)
    return ET.ElementTree(root)


def child_pid(parent_pid, server=None):
    """Identify only our direct GDB inferior, not another system simulator."""
    children = Path(f'/proc/{parent_pid}/task/{parent_pid}/children')
    if not children.exists():
        return None
    executable = (Path(server) if server else Path(shutil.which('gzserver'))).resolve(strict=True)
    for value in children.read_text().split():
        pid = int(value)
        try:
            if Path(f'/proc/{pid}/exe').resolve() == executable:
                return pid
        except FileNotFoundError:
            pass
    return None


def probe_passed(result, log):
    """Treat a captured old crash as reproduction, never runtime success."""
    if result['forced'] or result['error'] is not None:
        return False
    if result['expected_crash']:
        return (result['crash_captured'] and result['duplicate_reported'] and
                result.get('returncode') != 0)
    return (result['ready'] and not result['crash_captured'] and
            result.get('returncode') == 0 and
            (not result['duplicate'] or (result['duplicate_reported'] and
             'Camera plugin rejected:' in log)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True, type=Path)
    parser.add_argument('--camera-library', required=True, type=Path)
    parser.add_argument('--duplicate', action='store_true')
    parser.add_argument('--expect-crash', action='store_true')
    parser.add_argument('--capture', required=True, type=Path)
    parser.add_argument('--server', type=Path,
                        help='Explicit project-local server; default keeps system gzserver')
    parser.add_argument('--port', type=int, default=11361)
    parser.add_argument('--domain', type=int, default=129)
    parser.add_argument('--signal', choices=('SIGINT', 'SIGTERM'), default='SIGINT')
    args = parser.parse_args()
    directory = args.directory.resolve(strict=True)
    if any(directory.iterdir()):
        raise ValueError('requires a new empty evidence directory')
    library = args.camera_library.resolve(strict=True)
    capture = args.capture.resolve(strict=True)
    server = (args.server if args.server else Path(shutil.which('gzserver'))).resolve(strict=True)
    if args.expect_crash and not args.duplicate:
        raise ValueError('expected failure only supports the duplicate fixture')
    if not 0 <= args.domain <= 232:
        raise ValueError('invalid explicit ROS domain')
    from ament_index_python.packages import get_package_prefix, get_package_share_directory
    import rclpy
    from sensor_msgs.msg import CameraInfo, Image, PointCloud2
    from livox_ros_driver2.msg import CustomMsg
    from easyfly_px4_sitl.session_guard import SessionReservation

    iris = (Path(get_package_share_directory('easyfly_px4_sitl')) /
            'models/easyfly_iris/easyfly_iris.sdf')
    mid360 = Path(get_package_share_directory('easyfly_gazebo_models')) / 'mid360/mid360.sdf'
    plugin_dir = Path(get_package_prefix('easyfly_gazebo_plugins')) / 'lib'
    os.environ.update(
        ROS_DOMAIN_ID=str(args.domain),
        GAZEBO_MASTER_URI=f'http://127.0.0.1:{args.port}',
        ROS_LOG_DIR=str(directory / 'ros'),
        GAZEBO_MODEL_PATH=get_package_share_directory('easyfly_gazebo_models'),
        GAZEBO_PLUGIN_PATH=f'{plugin_dir}:/opt/ros/humble/lib',
    )
    reservation = SessionReservation()
    reservation.acquire(os.environ['GAZEBO_MASTER_URI'])
    world = directory / 'fixture.world'
    fixture(iris, mid360, library, args.duplicate).write(world, encoding='utf-8')
    topics = {
        '/camera/color/image_raw': Image,
        '/camera/color/camera_info': CameraInfo,
    }
    if not args.duplicate:
        topics.update({
            '/camera/aligned_depth_to_color/image_raw': Image,
            '/camera/aligned_depth_to_color/points': PointCloud2,
            '/livox/lidar': CustomMsg,
        })
    counts = dict.fromkeys(topics, 0)
    result = {
        'camera_library': str(library),
        'camera_library_sha256': hashlib.sha256(library.read_bytes()).hexdigest(),
        'fixture_sha256': hashlib.sha256(world.read_bytes()).hexdigest(),
        'duplicate': args.duplicate, 'expected_crash': args.expect_crash,
        'signal': args.signal, 'domain': args.domain, 'master': os.environ['GAZEBO_MASTER_URI'],
        'server': str(server),
        'server_sha256': hashlib.sha256(server.read_bytes()).hexdigest(),
        'counts': counts, 'forced': False, 'error': None,
    }
    rclpy.init()
    node = rclpy.create_node('shutdown_probe_observer')
    subscriptions = []
    for topic, msg_type in topics.items():
        def received(message, key=topic):
            counts[key] += 1
        subscriptions.append(node.create_subscription(
            msg_type, topic, received, rclpy.qos.qos_profile_sensor_data))
    command = ['gdb', '-q', '-batch', '--return-child-result', '-x', str(capture),
               '--args', str(server), '--verbose', '-s', 'libgazebo_ros_init.so', str(world)]
    result['command'] = command
    process = None
    log_path = directory / 'gazebo.log'
    try:
        with log_path.open('w') as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            deadline = time.monotonic() + 25
            ready_at = None
            while process.poll() is None and time.monotonic() < deadline:
                rclpy.spin_once(node, timeout_sec=0.05)
                if all(count >= 3 for count in counts.values()):
                    if ready_at is None:
                        ready_at = time.monotonic()
                    if time.monotonic() - ready_at >= 1:
                        break
            result['ready'] = ready_at is not None
            inferior = child_pid(process.pid, server)
            result['inferior_pid'] = inferior
            if process.poll() is None:
                if not result['ready']:
                    result['error'] = 'sensor readiness deadline exceeded'
                if inferior is None:
                    raise RuntimeError('cannot identify own Gazebo inferior')
                began = time.monotonic()
                os.kill(inferior, getattr(signal, args.signal))
                result['signal_sent'] = True
                process.wait(timeout=10)
                result['shutdown_seconds'] = time.monotonic() - began
            result['returncode'] = process.returncode
    except Exception as error:
        result['error'] = str(error)
    finally:
        if process is not None and process.poll() is None:
            result['forced'] = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)
        node.destroy_node()
        rclpy.shutdown()
        reservation.close()
    log = log_path.read_text(errors='replace') if log_path.exists() else ''
    result['crash_captured'] = ('received signal SIGSEGV' in log or
                                'received signal SIGABRT' in log)
    result['duplicate_reported'] = 'Found multiple nodes with same name' in log
    result['passed'] = probe_passed(result, log)
    (directory / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
