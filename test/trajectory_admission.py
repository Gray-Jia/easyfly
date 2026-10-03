"""ROS-free admission helpers for E3/E4 trajectory-start evidence."""

from __future__ import annotations

import math


# action_msgs/GoalStatus values are stable ROS action protocol constants.  The
# helper keeps the acceptance contract ROS-free by accepting the numeric
# status from a result future, while the node passes the imported constants at
# the call site when available.
GOAL_STATUS_ACCEPTED = 1
GOAL_STATUS_EXECUTING = 2


def goal_is_active(accepted, result_done, result_status,
                   active_statuses=(GOAL_STATUS_ACCEPTED,
                                    GOAL_STATUS_EXECUTING)):
    """Return whether an accepted FollowTrajectory goal is still active.

    A not-yet-complete result future is the normal ACCEPTED/EXECUTING window;
    it is therefore considered active only when the goal handle itself was
    accepted.  Once the future is complete, only explicit ACCEPTED or
    EXECUTING statuses pass.  SUCCEEDED, CANCELED, ABORTED and malformed
    statuses fail closed so E3/E4 never trigger RTL or kill on a finished
    action.
    """
    if not bool(accepted):
        return False
    if not bool(result_done):
        return True
    try:
        return int(result_status) in tuple(int(value) for value in active_statuses)
    except (TypeError, ValueError, OverflowError):
        return False


def goal_command_progress(
    origin,
    target,
    command_position,
    command_velocity=None,
    min_progress=0.25,
):
    """Return whether a READY command visibly advances toward a requested goal.

    A changed trajectory_id alone is unsafe: an emergency-stop spline can also
    allocate a fresh ID.  Require finite geometry, a meaningful goal vector,
    and an actual reduction in distance to the requested target.  If velocity
    is available, a non-zero speed is additionally required so a stationary
    stop command cannot pass as a goal trajectory.
    """
    try:
        origin = tuple(float(value) for value in origin)
        target = tuple(float(value) for value in target)
        command_position = tuple(float(value) for value in command_position)
        threshold = float(min_progress)
    except (TypeError, ValueError, OverflowError):
        return False
    values = origin + target + command_position + (threshold,)
    if not all(math.isfinite(value) for value in values) or threshold <= 0.0:
        return False
    goal_delta = tuple(target[i] - origin[i] for i in range(3))
    goal_norm = math.sqrt(sum(value * value for value in goal_delta))
    if not math.isfinite(goal_norm) or goal_norm < threshold:
        return False
    command_delta = tuple(command_position[i] - origin[i] for i in range(3))
    command_goal_delta = tuple(target[i] - command_position[i] for i in range(3))
    origin_distance = goal_norm
    command_distance = math.sqrt(sum(value * value for value in command_goal_delta))
    progress = origin_distance - command_distance
    if not math.isfinite(progress) or progress < threshold:
        return False
    if command_velocity is not None:
        try:
            velocity = tuple(float(value) for value in command_velocity)
        except (TypeError, ValueError, OverflowError):
            return False
        if not all(math.isfinite(value) for value in velocity):
            return False
        speed = math.sqrt(sum(value * value for value in velocity))
        if not math.isfinite(speed) or speed < 0.05:
            return False
    # Keep this calculation explicit: it documents that the accepted command
    # is not merely closer by a numerical roundoff while moving orthogonally.
    projection = sum(command_delta[i] * goal_delta[i] for i in range(3)) / goal_norm
    return math.isfinite(projection) and projection >= threshold * 0.5


def is_new_goal_trajectory(
    baseline_count,
    baseline_id,
    sample_count,
    trajectory_id,
    origin,
    target,
    command_position,
    command_velocity=None,
):
    """Combine new READY identity with goal-directed command progress."""
    if sample_count <= baseline_count or trajectory_id is None:
        return False
    try:
        if baseline_id is not None and int(trajectory_id) == int(baseline_id):
            return False
    except (TypeError, ValueError, OverflowError):
        return False
    return goal_command_progress(
        origin, target, command_position, command_velocity)
