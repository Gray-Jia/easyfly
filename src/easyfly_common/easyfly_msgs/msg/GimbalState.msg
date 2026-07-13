# 云台状态
std_msgs/Header header

float32 pitch_angle          # 俯仰角 [度]
float32 yaw_angle            # 偏航角 [度]
float32 roll_angle           # 横滚角 [度]

bool    is_tracking          # 是否正在跟踪目标
int32   tracking_target_id   # 跟踪目标ID (-1表示无)

string  gimbal_model         # 云台型号
bool    is_connected         # 是否连接
