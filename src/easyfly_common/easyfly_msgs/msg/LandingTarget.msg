# Perception only, NOT a descent/landing command. Optical-frame center/pose.
std_msgs/Header header
int32 tag_id
float64 tag_size_m
geometry_msgs/Pose pose
# Tag local x-axis yaw in optical camera XY plane [rad].
float64 yaw_rad
# Optical z distance [m], NOT vertical height above ground.
float64 optical_depth_m
float64 reprojection_error_px
bool valid
string reason
