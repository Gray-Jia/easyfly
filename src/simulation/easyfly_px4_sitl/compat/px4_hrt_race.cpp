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

// Explicit native probe: compile the actual selected PX4 POSIX HRT implementation.
// Only the outer timer dispatch/log sink is stubbed; queue and semaphore code is PX4's.
#include <atomic>
#include <chrono>
#include <cstdio>
#include <thread>

#include EASYFLY_PX4_HRT_SOURCE

extern "C" int hrt_work_queue(struct work_s *, worker_t, void *, uint32_t) {return 0;}
extern "C" void hrt_work_cancel(struct work_s *) {}
extern "C" void px4_log_modulename(int, const char *, const char *, ...) {}

static std::atomic<bool> entered{false};
static std::atomic<bool> started{false};
static std::atomic<bool> done{false};
static struct hrt_call nested{};

static void same_thread(void *)
{
  hrt_call_after(&nested, 1000000, nullptr, nullptr);
  done = true;
}

static void periodic(void *)
{
  entered = true;
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
  while (!started && std::chrono::steady_clock::now() < deadline) {
    std::this_thread::yield();
  }
  // Old code lets the other thread requeue this in-flight periodic entry here.
  // Correct serialization blocks it until this callback/periodic reinsert finishes.
  const auto window = std::chrono::steady_clock::now() + std::chrono::milliseconds(100);
  while (!done && std::chrono::steady_clock::now() < window) {
    std::this_thread::yield();
  }
}

int main(int argc, char **)
{
  hrt_init();
  if (argc == 2) {
    struct hrt_call outer{};
    hrt_call_after(&outer, 0, same_thread, nullptr);
    hrt_call_invoke();
    const bool intact = callout_queue.head == &nested.link &&
      callout_queue.tail == &nested.link && nested.link.flink == nullptr;
    std::printf("{\"callback_reentry_completed\":%s,\"nested_timer_queued\":%s}\n",
      done ? "true" : "false", intact ? "true" : "false");
    return done && intact ? 0 : 2;
  }
  struct hrt_call repeating{};
  struct hrt_call sentinel{};
  hrt_call_every(&repeating, 0, 1000000, periodic, nullptr);
  hrt_call_after(&sentinel, 2000000, nullptr, nullptr);
  std::thread rescheduler([&]() {
      const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
      while (!entered && std::chrono::steady_clock::now() < deadline) {
        std::this_thread::yield();
      }
      started = true;
      hrt_call_every(&repeating, 1000000, 1000000, periodic, nullptr);
      done = true;
    });
  hrt_call_invoke();
  rescheduler.join();
  int repeating_count = 0;
  bool sentinel_present = false;
  sq_entry_t * seen[8]{};
  int count = 0;
  bool cycle = false;
  for (auto * node = callout_queue.head; node != nullptr && count < 8; node = node->flink) {
    for (int i = 0; i < count; ++i) {
      if (seen[i] == node) {cycle = true;}
    }
    if (cycle) {break;}
    seen[count++] = node;
    if (node == &repeating.link) {++repeating_count;}
    if (node == &sentinel.link) {sentinel_present = true;}
  }
  const bool corrupt = cycle || count == 8 || repeating_count != 1 || !sentinel_present;
  std::printf("{\"queue_corrupt\":%s,\"cycle\":%s,\"sentinel_present\":%s,"
    "\"unique_entries\":%d,\"rescheduler_completed\":%s}\n",
    corrupt ? "true" : "false", cycle ? "true" : "false",
    sentinel_present ? "true" : "false", count, done ? "true" : "false");
  return entered && started && done ? 0 : 2;
}
