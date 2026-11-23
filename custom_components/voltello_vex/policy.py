"""When to call VE-X: the one polling rule (pure, no Home Assistant imports).

* Daylight only (sun above the horizon, or PV above DAYLIGHT_PV_W when the sun is unknown).
* One call per CYCLE_S; one per QUIET_S while the feed-in price is above
  QUIET_FEED_IN_ABOVE (nothing to curtail then).
* After FAILURES_BEFORE_PAUSE failures in a row, one call per PAUSE_S until one succeeds.
Ceiling: 12 calls an hour; none overnight, except an install's very first read.
"""

from __future__ import annotations

from dataclasses import dataclass

from .const import CYCLE_S, DAYLIGHT_PV_W, FAILURES_BEFORE_PAUSE, PAUSE_S, QUIET_FEED_IN_ABOVE, QUIET_S


@dataclass(frozen=True)
class PollState:
    last_call: float | None = None      # epoch seconds of the last call, good or bad
    last_success: float | None = None   # epoch seconds of the last good read
    failures: int = 0                   # consecutive failed calls


def is_daylight(sun_state: str | None, pv_w: float | None) -> bool:
    if sun_state == "above_horizon":
        return True
    if pv_w is not None and pv_w > DAYLIGHT_PV_W:
        return True
    return False


def interval_s(state: PollState, feed_in: float | None) -> int:
    if state.failures >= FAILURES_BEFORE_PAUSE:
        return PAUSE_S
    if feed_in is not None and feed_in > QUIET_FEED_IN_ABOVE:
        return QUIET_S
    return CYCLE_S


def due(state: PollState, now: float, daylight: bool, feed_in: float | None) -> bool:
    """Whether a call should be made now."""
    if state.last_call is None:
        return True    # the first read ever, at any hour: a new install shows its state at once
    if not daylight:
        return False
    return now - state.last_call >= interval_s(state, feed_in)


def after_call(state: PollState, now: float, ok: bool) -> PollState:
    if ok:
        return PollState(last_call=now, last_success=now, failures=0)
    return PollState(last_call=now, last_success=state.last_success, failures=state.failures + 1)
