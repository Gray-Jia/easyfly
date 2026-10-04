#include <gtest/gtest.h>
#include "easyfly_mission_fsm/mission_format.hpp"
using easyfly_mission_fsm::validateMissionText;
const std::string prefix = "schema_version: 1\nframe_id: odom\nunits: {position: m, angle: rad, time: s}\nsteps:\n";
TEST(MissionFormat, AllSevenTypesAndLegacyCompatibility) {
  auto v = validateMissionText(prefix +
    "- {type: takeoff, altitude: 1.5}\n- {type: hover, duration: 1}\n"
    "- {type: waypoint, x: 1, y: 0, z: 1.5}\n- {type: navigate, x: 0, y: 0, z: 1.5}\n"
    "- {type: track, target_id: -1, duration: 1}\n"
    "- {type: search, center_x: 0, center_y: 0, area_width: 4, area_height: 3, altitude: 1.5, pattern: boustrophedon}\n"
    "- {type: land}\n");
  ASSERT_TRUE(v.valid()) << v.error; ASSERT_EQ(v.steps.size(), 7u);
  EXPECT_EQ(v.steps[4].target_id, -1); EXPECT_EQ(v.steps[5].search_pattern, 1);
  EXPECT_TRUE(validateMissionText("---\n type = hover\n wait = 200\n").valid());
  EXPECT_TRUE(validateMissionText("altitude: 1\ntype: takeoff\n").valid());
  EXPECT_TRUE(validateMissionText("---\n" + prefix + "- {type: land}\n").valid());
}
TEST(MissionFormat, RejectWholeMissionAndMalformedValues) {
  for (const auto & bad : {
    "- {type: takeoff, altitude: 1}\n- {type: unknown}\n", "- {type: land, retry: 2}\n",
    "- {type: navigate, x: .nan, y: 0, z: 1}\n", "- {type: takeoff, altitude: 1, altitude: 2}\n",
    "- {type: takeoff, altitude: '1'}\n", "- {type: track, target_id: -2, duration: 1}\n",
    "- {type: track, target_id: 1.5, duration: 1}\n", "- {type: track, target_id: 1, duration: 2, timeout: 1}\n",
    "- {type: hover, duration: 1, timeout: 0}\n", "- {type: navigate, x: 0, y: 0}\n",
    "- {type: search, center_x: 0, center_y: 0, area_width: 4, area_height: 3, altitude: 1.5, pattern: spiral}\n"}) {
    auto result = validateMissionText(prefix + bad);
    EXPECT_FALSE(result.valid()) << bad; EXPECT_TRUE(result.steps.empty());
  }
  for (const auto & bad : {"schema_version: 2\n", "schema_version: '1'\n", "schema_version: true\n",
      "schema_version: 1\nschema_version: 1\n", "schema_version: 1\nframe_id: map\n"})
    EXPECT_FALSE(validateMissionText(std::string(bad) + "steps: [{type: land}]\n").valid());
  EXPECT_FALSE(validateMissionText(prefix + "- {type: land}\n---\nfoo: 2\n").valid());
  EXPECT_FALSE(validateMissionText("{\"schema_version\": 1}").valid());
  EXPECT_FALSE(validateMissionText(std::string(65537, 'x')).valid());
}
TEST(MissionFormat, BudgetsAndStepCountAreBounded) {
  auto text = prefix;
  for (int i=0; i<256; ++i) text += "- {type: hover, duration: 0, timeout: 1}\n";
  EXPECT_TRUE(validateMissionText(text).valid());
  EXPECT_FALSE(validateMissionText(text + "- {type: land}\n").valid());
  EXPECT_FALSE(validateMissionText(prefix + "- {type: land, timeout: 3600}\n- {type: land, timeout: 3600}\n- {type: land}\n").valid());
}
