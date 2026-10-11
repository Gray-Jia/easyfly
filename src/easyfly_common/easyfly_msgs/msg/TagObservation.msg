# Tag -> optical camera pose; original image time, meters, unit quaternion.
std_msgs/Header header
int32 tag_id
geometry_msgs/Pose pose
float64 tag_size_m
float64 reprojection_error_px
float64 range_m
bool valid
string reason
