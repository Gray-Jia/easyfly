// Copyright 2026 EasyFly Project
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//     http://www.apache.org/licenses/LICENSE-2.0
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
#ifndef EASYFLY_TRANSPORT__COMPAT_HPP_
#define EASYFLY_TRANSPORT__COMPAT_HPP_

#include <cstddef>
#include <string>

namespace easyfly_transport
{
constexpr char kCoreSha[] =
  "984c29da37f618c4f72e2023733df82479bc6cc98352f6fb6f30e3ddd4c5899d";

// Validate the actual loaded library, not a file guessed from LD_LIBRARY_PATH.
bool ValidateLibrary(const std::string & expected_sha = kCoreSha);
// Main-thread lifecycle controls; never call these from an IO callback.
void Drain();
bool Finish();
struct Statistics
{
  std::size_t live;
  std::size_t pending;
  std::size_t deferred;
  std::size_t completed;
};
Statistics GetStatistics();
}  // namespace easyfly_transport
#endif  // EASYFLY_TRANSPORT__COMPAT_HPP_
