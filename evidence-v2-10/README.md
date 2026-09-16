# V2-10 D435i model dynamics evidence

Date: 2026-09-15. PX4 SITL: `/home/jia/PX4-Autopilot-1.16.2`, v1.16.2 commit `54f0455ffcd755534539a7cf33a09a20bf71d29d`; Gazebo Classic 11.10.2; ROS 2 Humble; MAVROS and the EasyFly bridge.

## Experiment matrix

| Trial | Change | Result | ULog |
|---|---|---|---|
| E7 | Level camera pose; corrected camera_link box inertia; original color/depth child links, joints, sensors, and plugins retained | Failed around 2.6 s after arming/OFFBOARD; roll/pitch destabilized; recorded actuator output reached the 2000 PWM logging ceiling (this alone does not establish allocator saturation state) | `/home/jia/PX4-Autopilot-1.16.2/build/px4_sitl_default/rootfs/log/2026-09-15/14_04_49.ulg` |
| E5 | E7 plus only removal of both `<sensor>` elements; camera child links/joints retained | Failed around 2.6 s; removing render sensors alone did not fix dynamics | `/home/jia/PX4-Autopilot-1.16.2/build/px4_sitl_default/rootfs/log/2026-09-15/14_18_06.ulg` |
| Previous structure candidate | Kept 56 g camera_link/inertia, moved sensors under it, removed color/depth physical child links/joints | Inconsistent: one exploratory hover lacked a controlled landing; one preflight race; one controlled landing passed; a repeat of the same model flipped about 3.2 s after arming with mag/attitude faults. The single pass was not sufficient; candidate rejected. | `14_28_39.ulg`, `14_36_46.ulg`, `14_40_06.ulg`, `14_53_18.ulg` in the PX4 log directory above |
| Candidate F1 | Deleted camera_link, camera_color_frame, camera_depth_frame and all camera mass/inertia/joints; retained camera visual and both full sensors directly under base_link at `(0.25, 0, 0.22)` | Passed a 44 s OFFBOARD test window, accepted AUTO.LAND, and landed/disarmed; EKF yaw@arm `85.76°`, no mag fault, roll `-3.87°..1.43°`, pitch `-1.41°..1.42°`; max recorded actuator output 1851 PWM; no failsafe/dropout | `/home/jia/PX4-Autopilot-1.16.2/build/px4_sitl_default/rootfs/log/2026-09-15/15_10_46.ulg` |
| Candidate F2 | Same Candidate F, clean restart | Passed a 44 s OFFBOARD test window, accepted AUTO.LAND, and landed/disarmed; EKF yaw@arm `86.50°`, no mag fault, roll `-2.86°..1.29°`, pitch `-1.30°..0.95°`; max recorded actuator output 1834 PWM; no failsafe/dropout | `/home/jia/PX4-Autopilot-1.16.2/build/px4_sitl_default/rootfs/log/2026-09-15/15_15_25.ulg` |
| Candidate F3 | Same Candidate F, clean restart | Passed a 44 s OFFBOARD test window, accepted AUTO.LAND, and landed/disarmed; EKF yaw@arm `87.31°`, no mag fault, roll `-0.77°..1.90°`, pitch `-1.16°..0.50°`; max recorded actuator output 1811 PWM; no failsafe/dropout | `/home/jia/PX4-Autopilot-1.16.2/build/px4_sitl_default/rootfs/log/2026-09-15/15_17_52.ulg` |
| Final-pose F4 | Same no-camera-rigidbody structure; sensor origins corrected to `(0.2825, 0, 0.22)` from the calibration mount + optical translation; clean restart | Passed arm, a 44 s OFFBOARD test window (about 32 s at stable target altitude after climb), accepted AUTO.LAND, and landed/disarmed; EKF yaw@arm `72.14°`, no mag fault, roll `-1.64°..1.52°`, pitch `-1.18°..1.08°`; MAVROS test-window x `-0.091..0.189 m`, y `-0.118..0.141 m`; max recorded actuator output 1948 PWM (below the 2000 PWM logging ceiling; allocator saturation state not inferred); no failsafe/dropout | `/home/jia/PX4-Autopilot-1.16.2/build/px4_sitl_default/rootfs/log/2026-09-15/15_50_38.ulg` |

F1–F3 were the initial flight-validation pose at x=0.25 m. F4 is the final pose after static review composed `sensors.yaml`'s mount `(0.25,0,0.22)` and optical-origin translation `(0.0325,0,0)`. The four ULogs have no dropouts and remain in the PX4 build tree rather than being copied into this repository. Each run used a clean launch and shutdown; after F4 no PX4/Gazebo/MAVROS process remained.

## Runtime camera contract

With Candidate F running, both `/camera/color/image_raw` and `/camera/aligned_depth_to_color/image_raw` produced sensor-data messages. Their message `frame_id` values were `camera_color_optical_frame` and `camera_depth_optical_frame`, respectively. Camera-info, aligned-depth, and point-cloud plugin outputs were also advertised. The same contract was rechecked on final pose F4; see `F1-camera-contract.log` and `F4-camera-contract.log`.

The original SDF placed `0.0325 m` on separate color/depth child `<link><pose>` elements. That is a link pose, not a sensor-local optical offset, and SDF 1.6 does not make it camera-link-relative merely because a fixed joint names `camera_link` as its parent. Candidate F instead removes the extra links and places each sensor directly under `base_link` at the composed x=0.2825 m. During F4 spawn, the installed Gazebo/SDF parser warned that `pose@frame` was ignored; the final SDF therefore omits that unsupported-in-practice attribute and relies on direct-child pose semantics. Runtime F4 confirmed topic and frame IDs with the final sensor pose.

## Reproduction

In separate terminals:

```bash
source /opt/ros/humble/setup.bash
source install-v2/setup.bash
export PX4_DIR=/home/jia/PX4-Autopilot-1.16.2
ros2 launch easyfly_px4_sitl px4_sitl.launch.py
```

```bash
source /opt/ros/humble/setup.bash
source install-v2/setup.bash
ros2 launch easyfly_mavlink_bridge mavlink_bridge.launch.py \
  fcu_url:=udp://:14540@127.0.0.1:14555 use_sim_time:=true
```

After PX4/Gazebo and MAVROS connect:

```bash
source /opt/ros/humble/setup.bash
source install-v2/setup.bash
python3 evidence-v2-10/offboard_flight_check.py --hover-seconds 44
```

The harness waits for PX4 preflight startup, publishes `/mavros/setpoint_position/local` at 20 Hz with a 1.5 m target, and records pose, attitude, mode, arming state, and RC outputs. It requests native `AUTO.LAND`; success requires PX4 disarmed and `/mavros/extended_state` to report `LANDED_STATE_ON_GROUND`. No blind in-air disarm is attempted.

Static SDF regression checks run through `colcon test --build-base build-v2 --install-base install-v2 --packages-select easyfly_px4_sitl --event-handlers console_direct+`. They verify physical realizability of all explicit link inertias, absence of camera rigid bodies/joints, the pose-only camera visual, and the D435i sensor/plugin/topic/frame contract. The targeted package build and test both pass.

## Scope and remaining validation

Candidate F retains both sensor plugins and camera topic/frame names, while removing all camera physical links, joints, mass, and inertia. E5 showed that removing `<sensor>` alone is insufficient. F1–F3 passed three consecutive full flights; final-pose F4 passed another complete flight after restoring the calibration-composed x=0.2825 m sensor origins. This meets V2-10's model-stability criterion. The evidence does not isolate whether the previous failure was caused by the camera mass/inertia, fixed-link structure, their SDF/lumping interaction, or some combination; nor does it certify real-world extrinsic calibration. There is no outstanding 3.25 cm pose-offset issue in the current model.

Each 1-second flight sample, SITL/bridge log, camera contract snapshot, and ULog-derived EKF/mag/attitude/position/motor/landing summary is preserved in this directory (`F{1,2,3,4}-*.log`, `F{1,2,3,4}-ulog-summary.txt`). ULog binary files remain outside the repository under the PX4 build tree.
