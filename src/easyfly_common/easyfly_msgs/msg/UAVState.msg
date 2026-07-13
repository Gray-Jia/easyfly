# 无人机全状态消息
std_msgs/Header header

# 飞行状态
bool   armed                 # 是否解锁
uint8  flight_mode           # 飞行模式 (0=Manual, 1=Altitude, 2=Position, 3=Offboard, 4=Stabilized, 5=Acro, 6=RTL, 7=Land)
string flight_mode_name      # 飞行模式名称

# 姿态 (NED坐标系)
float64 roll                 # 横滚角 [rad]
float64 pitch                # 俯仰角 [rad]
float64 yaw                  # 偏航角 [rad]
float64 rollspeed            # 横滚角速度 [rad/s]
float64 pitchspeed           # 俯仰角速度 [rad/s]
float64 yawspeed             # 偏航角速度 [rad/s]

# 位置 (ENU坐标系, 以home点为原点)
float64 position_x           # x [m]
float64 position_y           # y [m]
float64 position_z           # z [m] (负值表示高于home)

# 速度 (ENU坐标系)
float64 velocity_x           # vx [m/s]
float64 velocity_y           # vy [m/s]
float64 velocity_z           # vz [m/s]

# GPS
float64 latitude             # 纬度 [度]
float64 longitude            # 经度 [度]
float64 altitude             # 海拔高度 [m]
float64 relative_altitude    # 相对起飞点高度 [m]
uint8   satellites_visible   # 可见卫星数
float64 eph                  # 水平位置精度因子
float64 epv                  # 垂直位置精度因子

# 电池
float64 battery_voltage      # 电池电压 [V]
float64 battery_remaining    # 剩余电量 [0.0-1.0]

# 遥控器
bool   rc_connected          # 遥控器是否连接
