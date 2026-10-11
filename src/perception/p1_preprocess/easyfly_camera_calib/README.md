# Configured calibration validation

All configured transforms/intrinsics are validated before publishing any static
TF. This loads known calibration; it does not solve calibration online.
The continuous CameraInfo diagnostic checks frame, K/distortion, source/receipt
age and ROS-clock progress, rather than trusting the first valid sample forever.
The diagnostic is not an automatic flight-admission gate. Configuration changes
require restarting the common calibration launch.

`ros2 launch easyfly_camera_calib calib_tf.launch.py` defaults to simulated time.
Set `use_sim_time:=false` for system time; `calib_file` selects a trusted local
file. First format supports plumb_bob/5 coefficients only. Detailed contract and
tests: [D4 guide](../../../../docs/development/d4-perception.md).
