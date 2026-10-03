#include <gtest/gtest.h>

#include <limits>

#include "easyfly_flight_control/trajectory_startup_timeout.hpp"

namespace easyfly_flight_control
{
namespace
{

TEST(TrajectoryStartupTimeoutTest, DefaultAndFiniteBoundsAreExplicit)
{
  EXPECT_DOUBLE_EQ(
    sanitizeTrajectoryStartupGrace(kDefaultTrajectoryStartupGrace),
    kDefaultTrajectoryStartupGrace);
  EXPECT_DOUBLE_EQ(sanitizeTrajectoryStartupGrace(kMinTrajectoryStartupGrace),
                   kMinTrajectoryStartupGrace);
  EXPECT_DOUBLE_EQ(sanitizeTrajectoryStartupGrace(kMaxTrajectoryStartupGrace),
                   kMaxTrajectoryStartupGrace);
  EXPECT_DOUBLE_EQ(sanitizeTrajectoryStartupGrace(0.0),
                   kDefaultTrajectoryStartupGrace);
  EXPECT_DOUBLE_EQ(sanitizeTrajectoryStartupGrace(-1.0),
                   kDefaultTrajectoryStartupGrace);
  EXPECT_DOUBLE_EQ(sanitizeTrajectoryStartupGrace(
                     std::numeric_limits<double>::quiet_NaN()),
                   kDefaultTrajectoryStartupGrace);
  EXPECT_DOUBLE_EQ(sanitizeTrajectoryStartupGrace(
                     std::numeric_limits<double>::infinity()),
                   kDefaultTrajectoryStartupGrace);
  EXPECT_DOUBLE_EQ(sanitizeTrajectoryStartupGrace(kMaxTrajectoryStartupGrace + 1.0),
                   kDefaultTrajectoryStartupGrace);
}

TEST(TrajectoryStartupTimeoutTest, StartupGraceAppliesOnlyBeforeFirstReadyFrame)
{
  EXPECT_FALSE(trajectoryStreamLost(false, 7.99, kDefaultTrajectoryStartupGrace));
  EXPECT_TRUE(trajectoryStreamLost(false, 8.0, kDefaultTrajectoryStartupGrace));

  // Once a valid frame has arrived, the independent 0.5s stream watchdog
  // remains in force even though startup grace is longer.
  EXPECT_FALSE(trajectoryStreamLost(true, 0.49, kDefaultTrajectoryStartupGrace));
  EXPECT_TRUE(trajectoryStreamLost(true, 0.5, kDefaultTrajectoryStartupGrace));
}

TEST(TrajectoryStartupTimeoutTest, StartupWaitCannotExtendActionDeadline)
{
  EXPECT_FALSE(trajectoryStartupTimedOut(2.0, 8.0, 10.0));
  EXPECT_TRUE(trajectoryStartupTimedOut(8.01, 8.0, 10.0));

  // A short action timeout wins over the longer planner retry grace.
  EXPECT_FALSE(trajectoryStartupTimedOut(2.99, 8.0, 3.0));
  EXPECT_TRUE(trajectoryStartupTimedOut(3.0, 8.0, 3.0));
  EXPECT_TRUE(trajectoryStartupTimedOut(3.01, 8.0, 3.0));
  EXPECT_TRUE(trajectoryStartupTimedOut(3.01, 8.0, -0.01));
  EXPECT_FALSE(trajectoryDeadlineExpired(2.99, 3.0));
  EXPECT_TRUE(trajectoryDeadlineExpired(3.0, 3.0));
}

TEST(TrajectoryStartupTimeoutTest, InvalidTimingEvidenceFailsClosed)
{
  EXPECT_TRUE(trajectoryStreamLost(false, -0.01, kDefaultTrajectoryStartupGrace));
  EXPECT_TRUE(trajectoryStreamLost(
    false, std::numeric_limits<double>::quiet_NaN(), kDefaultTrajectoryStartupGrace));
  EXPECT_TRUE(trajectoryStreamLost(
    true, 0.1, kDefaultTrajectoryStartupGrace,
    std::numeric_limits<double>::quiet_NaN()));
  EXPECT_TRUE(trajectoryStartupTimedOut(
    0.1, kDefaultTrajectoryStartupGrace,
    std::numeric_limits<double>::quiet_NaN()));
}

}  // namespace
}  // namespace easyfly_flight_control
