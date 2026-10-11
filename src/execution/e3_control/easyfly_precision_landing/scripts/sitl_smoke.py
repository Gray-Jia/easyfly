#!/usr/bin/env python3
# Copyright 2026 EasyFly Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Source compatibility entry; prefer ros2 run easyfly_sim_launcher d5_simulation."""

from easyfly_precision_landing.simulation import (
    completed_mission,
    complete_precision_chain,
    exact_released,
    fresh_disarmed_state,
    main,
    mission_fixture,
    parse_arguments,
)

__all__ = [
    "completed_mission", "complete_precision_chain", "exact_released",
    "fresh_disarmed_state", "mission_fixture", "parse_arguments", "main",
]


if __name__ == "__main__":
    main()
