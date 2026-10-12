# MAVLink bridge fault boundaries

`/platform/mavlink_bridge/capabilities` is a read-only command-transport query
using the existing `GetCapabilities` interface. It names
`flight_command_transport` and retains a JSON snapshot of `command_fault`,
context, ROS clock and mode/arming service discovery. `ready` means only that
the transport peers exist and the independent bridge fault is not set. It is
not flight permission, FCU mode acceptance, telemetry validation or a control
reservation. Actual requests still perform their existing checks.

An attempted MAVROS request without a confirmed local reply keeps the existing
bridge fault latch. Queries, fresh telemetry and late replies cannot clear it.
Mode and arming services return `command_result_unknown: bridge fault locked`
without forwarding further requests; encoder input/output is also guarded.
Audit the remote aircraft state before restarting. No automatic retry, mode
compensation, disarm or recovery is added.

Normal `mavlink_bridge.launch.py` still starts exactly one bridge by default.
`start_bridge:=false` is for an explicit owner that starts its own instance;
MAVROS/RC and the original clock policy are unchanged. The D5 simulation entry
uses this only with explicit bridge fault scenarios and remaps only the owned
bridge's MAVROS clients to its typed test proxy. Real MAVROS stays unchanged.

The real ROS regression uses explicitly synthetic MAVROS services and clock,
not a flight controller or physical aircraft. It checks read-only queries while
a mode or arming service is pending, the original five-second timeout, persistent fault
after late reply, direct mode/arm denials and encoder silence despite fresh
command input (with an actual pre-fault output baseline). This component test
is not a substitute for real SITL/native PX4 evidence.

The explicit D5 `bridge-mode-late` and `bridge-mode-withheld` SITL cases also
passed independent raw-result/native-PX4/lifecycle audit (schedule-v4 section
36). They verify distinct flight/bridge locks, real AUTO.LAND evidence, exact
failed parent/child terminals, valid direct service denials without further
MAVROS requests, positive-output baseline followed by silence, and owned
process/callback cleanup. Fresh command input after fault remains component
evidence only. Arming-reply uncertainty, cancellation cross-cases and physical
aircraft are not covered by these two mode-reply tests.

Separate explicit `bridge-arm-late` / `bridge-arm-withheld` cases target the
real Takeoff preparation transaction (schedule-v4 section 37). They admit one
unchanged arming request only after live, independently sourced disarmed
OFFBOARD and owned EXECUTING Takeoff evidence. The actual CommandBool ACK is
withheld, never synthesized; independently advanced UAVState/FlightStatus
must confirm actual arming. Later probes wait for native PX4 disarming without
platform compensation. This fixture does not authorize cancellation cross-cases
or alter any ordinary flight control or safety parameters.
Both arming-reply cases passed real SITL/raw/native/lifecycle audit in that
section. They retain true ABORTED Takeoff results and both fault locks, with
no climb, retransmission, compensating disarm or late-reply recovery. This is
not Takeoff success, upstream-only arming-reply coverage or physical-aircraft
validation.

Section 38 adds four explicit `cancel-bridge-{arm,mode}-{late,withheld}`
Takeoff-preparation cases: exact cancel acknowledgement, still-reserved
pending transaction and unresolved GetResult, silence during cancellation,
then true CANCELED/false/unknown after the original request drains. Two
`upstream-arm-{late,withheld}` cases withhold only the flight-facing reply;
the flight fault persists while the bridge is independently healthy. They
never command that healthy bridge directly. All six scoped SITL/raw/native/
lifecycle audits passed, with one separate pre-goal calibration rejection
retained. No production flight logic or safety thresholds changed. Ordinary
Land/precision-handoff cancellation cross-cases remain unverified.
