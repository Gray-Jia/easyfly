#include <gtest/gtest.h>
#include "easyfly_mission_fsm/search_geometry.hpp"
using namespace easyfly_mission_fsm;
TEST(SearchGeometry, ZigzagAreaCountsCompletedStripsNotApproach) {
  auto route = searchRoute(0, 0, 4, 3, 1.5, 2, {});
  ASSERT_EQ(route.size(), 4u);
  EXPECT_DOUBLE_EQ(route[0].x, -2); EXPECT_DOUBLE_EQ(route[1].x, 2);
  EXPECT_DOUBLE_EQ(route[2].x, 2); EXPECT_DOUBLE_EQ(route[3].x, -2);
  EXPECT_DOUBLE_EQ(route[0].y, -.75); EXPECT_DOUBLE_EQ(route[2].y, .75);
  EXPECT_DOUBLE_EQ(route[0].completed_area, 0); EXPECT_DOUBLE_EQ(route[1].completed_area, 6);
  EXPECT_DOUBLE_EQ(route[2].completed_area, 6); EXPECT_DOUBLE_EQ(route[3].completed_area, 12);
}
TEST(SearchGeometry, RejectBoundsNonfiniteAndExcessiveWork) {
  EXPECT_THROW(searchRoute(50, 0, 4, 3, 1.5, 2, {}), std::invalid_argument);
  EXPECT_THROW(searchRoute(0, 0, 4, 3, 3, 2, {}), std::invalid_argument);
  EXPECT_THROW(searchRoute(0, 0, 4, 30, 1.5, .1, {}), std::invalid_argument);
  EXPECT_THROW(searchRoute(NAN, 0, 4, 3, 1.5, 2, {}), std::invalid_argument);
  EXPECT_THROW(searchRoute(0, 0, 4, 3, 1.5, 0, {}), std::invalid_argument);
}
