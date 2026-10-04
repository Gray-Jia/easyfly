#include "easyfly_mission_fsm/mission_format.hpp"
#include <iostream>
int main(int argc, char ** argv) {
  if (argc != 2) {std::cerr << "usage: mission_validate PATH\n"; return 2;}
  const auto result = easyfly_mission_fsm::validateMissionFile(argv[1]);
  if (!result.valid()) {std::cerr << result.error << '\n'; return 1;}
  std::cout << "valid: " << result.steps.size() << " steps; live flight admission still required\n";
  return 0;
}
