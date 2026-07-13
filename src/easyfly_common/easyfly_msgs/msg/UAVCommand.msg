# 无人机控制指令
std_msgs/Header header

# 控制模式
uint8 POSITION=0
uint8 VELOCITY=1
uint8 ATTITUDE=2
uint8 ATTITUDE_THRUST=3
uint8 ANGULAR_RATE=4
uint8 control_mode

# 位置设置点 (ENU, m)
float64 position_x
float64 position_y
float64 position_z
float64 yaw

# 速度设置点 (ENU, m/s)
float64 velocity_x
float64 velocity_y
float64 velocity_z
float64 yaw_rate

# 姿态设置点
float64 roll
float64 pitch
float64 yaw_att
float64 thrust                 # 归一化推力 [0.0-1.0]

# 角速率设置点 (rad/s)
float64 roll_rate
float64 pitch_rate
float64 yaw_rate_cmd
