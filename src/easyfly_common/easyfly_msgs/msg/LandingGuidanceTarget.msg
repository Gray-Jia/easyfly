# Perception only: converted fixed-camera landing observation, NOT a command.
# Header is the original image stamp in odom; source_header preserves optical frame.
std_msgs/Header header
std_msgs/Header source_header
int32 tag_id
float64 tag_size_m
geometry_msgs/Point position
geometry_msgs/Vector3 plane_normal
bool valid
string reason
