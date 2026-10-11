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

#pragma once
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <memory>
#include <stdexcept>
#include <string>
#include <unistd.h>

namespace ef_timing
{
inline int64_t wall_ns()
{
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
    std::chrono::system_clock::now().time_since_epoch()).count();
}
struct Event
{
  int64_t source_ns{0}, writer_wall_ns{0}, receive_wall_ns{0}, entry_wall_ns{0};
  int64_t entry_ros_ns{0}, publish_begin_wall_ns{0}, publish_end_wall_ns{0};
  bool input{false}, valid{false};
  char reason[64]{};
};
// Single-executor recorder: no additional reader, thread or callback-time I/O.
// Last 8192 publications only. Count/drop fields make truncation explicit.
class Trace
{
public:
  explicit Trace(const std::string & path)
  {
    if (path.empty()) {
      return;
    }
    events_ = std::make_unique<std::array<Event, capacity>>();
    int fd = open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    if (fd < 0) {
      throw std::runtime_error("cannot exclusively create landing timing trace");
    }
    file_ = fdopen(fd, "w");
    if (!file_) {
      close(fd);
      throw std::runtime_error("cannot open landing timing stream");
    }
  }
  ~Trace()
  {
    if (!file_) {
      return;
    }
    const auto retained = std::min(count_, capacity);
    fprintf(file_, "# total=%zu retained=%zu dropped=%zu\n", count_, retained, count_ - retained);
    fprintf(
      file_, "sequence\tinput\tsource_ns\twriter_wall_ns\treceive_wall_ns\t"
      "entry_wall_ns\tentry_ros_ns\tpublish_begin_wall_ns\tpublish_end_wall_ns\tvalid\treason\n");
    for (size_t i = count_ - retained; i < count_; ++i) {
      const auto & e = (*events_)[i % capacity];
      fprintf(
        file_, "%zu\t%d\t%lld\t%lld\t%lld\t%lld\t%lld\t%lld\t%lld\t%d\t%s\n",
        i, e.input, static_cast<long long>(e.source_ns), static_cast<long long>(e.writer_wall_ns),
        static_cast<long long>(e.receive_wall_ns), static_cast<long long>(e.entry_wall_ns),
        static_cast<long long>(e.entry_ros_ns), static_cast<long long>(e.publish_begin_wall_ns),
        static_cast<long long>(e.publish_end_wall_ns), e.valid, e.reason);
    }
    const bool failed = ferror(file_) != 0;
    if (fclose(file_) != 0 || failed) {
      fprintf(stderr, "landing timing trace write failed\n");
    }
  }
  bool enabled() const {return file_ != nullptr;}
  void record(Event event, const std::string & reason)
  {
    if (!enabled()) {
      return;
    }
    std::strncpy(event.reason, reason.c_str(), sizeof(event.reason) - 1);
    (*events_)[count_++ % capacity] = event;
  }

private:
  static constexpr size_t capacity = 8192;
  std::unique_ptr<std::array<Event, capacity>> events_;
  FILE * file_{nullptr};
  size_t count_{0};
};
}  // namespace ef_timing
