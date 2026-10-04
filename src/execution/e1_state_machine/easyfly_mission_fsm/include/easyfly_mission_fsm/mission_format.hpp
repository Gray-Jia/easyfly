#pragma once
#include "easyfly_mission_fsm/legacy_mission.hpp"

namespace easyfly_mission_fsm {
// Content detection also works with the facade's extensionless private snapshots.
// Static validation is not authorization to fly: live action admission still applies.
MissionValidation validateMissionText(const std::string & text);
MissionValidation validateMissionFile(const std::string & path);
}  // namespace easyfly_mission_fsm
