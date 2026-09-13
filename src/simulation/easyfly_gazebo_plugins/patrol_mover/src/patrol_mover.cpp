// PatrolMover — M4.1: 巡航移动目标驱动 (运动学, 每物理步直接设置位姿)
//
// 用途: 驱动 person_walking 沿 A↔B 直线以恒速往返, 为 TrackTarget 跟随
// 验收提供可复现的移动目标。
//
// 设计说明:
//   - 模型应为 static (world 接线时由 model.sdf 声明): 纯运动学移动,
//     无重力/接触干扰, 不会像动态模型那样被物理引擎缓慢推移 (M4.0 教训);
//     static 模型的 collision/visual 不变, 相机与雷达均可感知;
//   - 朝向随行进方向翻转 (更接近真实行人, 检测/跟踪链更真实)。
//
// SDF 用法:
//   <plugin name="patrol_mover" filename="libpatrol_mover.so">
//     <waypoint_a>14 -2 0</waypoint_a>
//     <waypoint_b>22 -2 0</waypoint_b>
//     <speed>1.0</speed>
//   </plugin>

#include <gazebo/common/Plugin.hh>
#include <gazebo/physics/physics.hh>
#include <ignition/math/Pose3.hh>
#include <ignition/math/Vector3.hh>

#include <cmath>

namespace gazebo
{

class PatrolMover : public ModelPlugin
{
public:
  void Load(physics::ModelPtr model, sdf::ElementPtr sdf) override
  {
    model_ = model;
    a_ = sdf->Get<ignition::math::Vector3d>("waypoint_a",
         ignition::math::Vector3d(14, -2, 0)).first;
    b_ = sdf->Get<ignition::math::Vector3d>("waypoint_b",
         ignition::math::Vector3d(22, -2, 0)).first;
    speed_ = sdf->Get<double>("speed", 1.0).first;
    a_.Z() = 0.0;
    b_.Z() = 0.0;
    len_ = (b_ - a_).Length();
    if (len_ < 0.01) len_ = 1.0;

    conn_ = event::Events::ConnectWorldUpdateBegin(
        std::bind(&PatrolMover::OnUpdate, this));

    gzmsg << "[patrol_mover] " << model->GetName() << ": ("
          << a_.X() << "," << a_.Y() << ")↔(" << b_.X() << "," << b_.Y()
          << ") @ " << speed_ << " m/s\n";
  }

private:
  void OnUpdate()
  {
    const double t = model_->GetWorld()->SimTime().Double();
    // 自检: 每 10s 打印实际位姿 vs 期望 (诊断静态模型是否被外力缓慢移动)
    if (t - last_log_ > 10.0) {
      last_log_ = t;
      const auto cur = model_->WorldPose();
      gzmsg << "[patrol_mover] t=" << t << " 期望z=" << a_.Z()
            << " 实际=(" << cur.Pos().X() << "," << cur.Pos().Y() << "," << cur.Pos().Z()
            << ") static=" << model_->IsStatic() << "\n";
    }
    double s = std::fmod(t * speed_, 2.0 * len_);
    bool forward = true;
    if (s > len_) {
      s = 2.0 * len_ - s;
      forward = false;
    }
    const ignition::math::Vector3d dir = (b_ - a_) / len_;
    const ignition::math::Vector3d pos = a_ + dir * s;
    const double yaw = forward ? std::atan2(dir.Y(), dir.X())
                               : std::atan2(-dir.Y(), -dir.X());
    model_->SetWorldPose(
        ignition::math::Pose3d(pos.X(), pos.Y(), a_.Z(), 0, 0, yaw));
  }

  physics::ModelPtr model_;
  event::ConnectionPtr conn_;
  ignition::math::Vector3d a_, b_;
  double speed_{1.0};
  double len_{1.0};
  double last_log_{-10.0};
};

GZ_REGISTER_MODEL_PLUGIN(PatrolMover)

}  // namespace gazebo
