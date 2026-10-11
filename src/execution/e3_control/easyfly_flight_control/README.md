# Flight control: PrecisionLand extension

`/precision_land` owns one parent flight reservation from acquisition through the
real `/land` action terminal. Ordinary Takeoff, GoToWaypoint, FollowTrajectory and
Land goals are rejected throughout. `/uav_command` still has this node as its only
platform flight publisher; the observation converter cannot command flight.

This node generates references and manages action ownership, not a separate
position/velocity PID. The normal position and trajectory paths use PX4's
position/velocity outer loops and attitude/angular-rate inner loops.

## C++ checks

`colcon test --packages-select easyfly_flight_control` includes cpplint,
uncrustify and cppcheck over every C++ file in `include`, `src` and `test`.
Cppcheck uses its installed `googletest` library to parse test/expectation macros;
test bodies are still analyzed, with no file exclusions or added suppressions.
Humble's slow-version override is scoped to this small cppcheck test, so an
installed cppcheck 2.x is checked rather than silently counted as skipped.
This is not a whole-workspace lint certification.

## Takeoff readiness

`/platform/flight_control/capabilities` is a read-only Takeoff readiness query.
Its existing GetCapabilities response names `takeoff`; `details[0]` retains a
JSON decision snapshot (original state source/receipt, clock, validity and locks).
It uses the same state/ownership predicate as Takeoff admission, but does not
validate a specific goal, reserve control, clear faults or send flight commands.
The actual goal and accepted handler still recheck current evidence. A ready
response is not permission to bypass them. Rejected Takeoff requests log their
UUID and actual decision snapshot, including invalid goal parameters.

## Precision landing configuration

Precision landing is disabled by default. Enable only an explicitly configured
simulation setup. Startup-only, read-only required parameters:

- `precision_enabled=true`, `precision_tag_id>=0`, `precision_tag_size_m>0`.
- `precision_horizontal_speed`, `precision_descent_speed` (m/s).
- `precision_align_tolerance`, `precision_handoff_height`,
  `precision_descent_floor_height`, `precision_max_height`,
  `precision_max_radius`, `precision_plane_z` (m).

The explicit descent target floor must satisfy
`0.15 <= precision_descent_floor_height < precision_handoff_height`.
It bounds generated targets; it does not authorize Land above measured handoff
height or replace fresh target evidence and independent settled observations.

Remaining bounded parameters match the policy Config names with `precision_`
prefix: `plane_tolerance`, `tilt_limit` (rad), `target_jump`, `target_max_age`,
`acquire_timeout`, `lost_timeout`, `settle_observations`. The default fixed optical
frame is `camera_down_optical_frame` (`precision_optical_frame`). Invalid enabled
configuration fails startup. Values must also satisfy `Config::valid()` safety
bounds; defaults of required geometric/control values are intentionally NaN.

Only fresh `/landing/guidance_target` evidence with matching ID, explicit tag
size, odom frame, fixed optical source frame, equal positive source timestamps,
trusted unit plane normal and configured landing plane can drive the policy.
Both ROS source age and monotonic receipt age expire observations; repeated source
timestamps do not refresh receipt TTL or stable alignment counts.
Before descent, the policy requires multiple independent source-stamped aligned
observations. Target loss immediately holds the trusted measured OFFBOARD pose;
short reacquisition must align again, and long loss fails while hovering.
Flight feedback loss or external mode takeover stops platform output instead.

The guidance reader has a 50 ms progress watchdog in the same mutually exclusive
callback group. The callback and watchdog check local steady progress after
acquiring the flight lock: exceeding the existing target-age budget (default
0.3 s) invalidates cached target/receipt and rebuilds the reliable, depth-1,
volatile reader. Retired-generation callbacks cannot clear or refresh recovered
evidence. Source watermark and policy/loss deadlines are preserved; no queries
renew this progress, and RMW wall time is not flight admission evidence. Reader
creation errors propagate after clearing evidence, stopping the node rather than
continuing on the old target. This isolates local processing blackouts, not
arbitrary upstream delay or per-topic starvation while the group keeps running.
Fresh input must still pass all original alignment/reacquisition checks.

At validated low height, the parent forwards only an internal Land goal bearing
its UUID session. Admission, accepted handling and the actual AUTO.LAND request
each recheck fresh evidence and measured alignment. After that request, ordinary
Land semantics apply. Feedback phase stays `land_handoff` through the child Land.
Success requires the real child result and fresh disarm confirmation, not service
acceptance, odom Z or a simulated ground-height guess.

Parent cancellation/timeout precisely cancels its own child, waits for actual
admission and terminal results, and never cancels other goals. Ordinary Land's
owned AUTO.LAND cancellation recovery is reused, including its existing state,
takeover and fault-latch guards. Unknown child admission/result cannot release
the parent reservation. `/precision_landing/ownership` reports exact lowercase
UUID `OWNED`, `RELEASED`, or `UNKNOWN`; public terminal results alone are not proof
of release. UUID sessions are correlation, not authentication: ROS control peers
must remain trusted. Unknown remote flight-command outcomes keep the existing
flight fault latch and require human audit before restart.
An Action's confirmed terminal/drain may report `RELEASED` while that independent
flight-command fault latch stays set; release never proves the PX4 mode result.
Fault-latched Land failures, like Takeoff failures, report
`command_result_unknown:`. This does not claim PX4 refused or never executed the
command. Logs do not claim OFFBOARD hover while the fault guard stops streaming.

`/platform/precision_landing/capabilities` reports implementation and live
configuration/readiness separately. This implementation and fake-feedback ROS
regression are not physical aircraft, camera calibration or precision certification.
## Opt-in precision frame timing

`precision_timing_diagnostics` is a read-only startup parameter, default `false`.
When enabled, `precision_frame_diag` reports at one-second intervals with a
256-event bounded ring and cumulative dropped count. It separates guidance
callback entry, native RMW receive metadata, flight mutex wait and admission
outcome; it records source stamp, current `generation`, captured
`callback_generation` (including retired readers), and session active/UUID.
`ready_at_exit` is callback-time evidence, not proof the control loop used a frame.
Missing/backward native wall timestamps are `null`, not zero latency. Callback
entry is not native take time; timestamps never authorize flight. Final unflushed
events may be absent on process exit. Simulation `--transform-diagnostics` enables
both transform and flight timing in the generated configuration only.
