"""The coordinator: wakes every minute, calls VE-X only when the polling rule says so."""

from __future__ import annotations

from datetime import timedelta
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import policy
from .api import VexAuthError, VexClient, VexError
from .const import (
    CONF_BATTERY_ID, CONF_FEED_IN_ENTITY, CONF_INVERTER_ID, CONF_PV_ENTITY, CONF_SERVICE_POINT_ID,
    DOMAIN, REFUSALS_BEFORE_REAUTH, STALE_S, STORAGE_VERSION, TICK_S,
)
from .control_log import ControlState, has_control_log, summarize

_LOGGER = logging.getLogger(__name__)


def _now() -> float:
    """Wall-clock seconds (one hook, so tests can move time without touching the time module)."""
    return time.time()


def _float_state(hass: HomeAssistant, entity_id: str | None) -> float | None:
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    try:
        return float(state.state) if state is not None else None
    except (TypeError, ValueError):
        return None


class VexCoordinator(DataUpdateCoordinator[ControlState | None]):
    """Holds the latest control state; `fresh` says whether entities may show it."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: VexClient) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=TICK_S), config_entry=entry)
        self.client = client
        self.entry = entry
        self.poll = policy.PollState()
        self.last_detail: dict[str, Any] | None = None
        self.seen_contracts: list[str] = []
        self.refusals = 0   # 401/403 answers in a row
        # The last call survives restarts and reloads, so they never add a call (the ceiling).
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")

    async def async_load_poll_state(self) -> None:
        saved = await self._store.async_load() or {}
        self.poll = policy.PollState(last_call=saved.get("last_call"), last_success=saved.get("last_success"),
                                     failures=int(saved.get("failures", 0)))
        self.seen_contracts = list(saved.get("seen_contracts", []))
        # The last good control log comes back too, so a restart inside the 20-minute window
        # shows it at once instead of leaving the entities unavailable until the next call.
        saved_log = saved.get("control_log")
        if self.poll.last_success is not None and has_control_log(saved_log):
            self.last_detail = saved_log
            self.data = summarize(saved_log, self.entry.data.get(CONF_INVERTER_ID), self.entry.data.get(CONF_BATTERY_ID))

    def _remember(self) -> None:
        self._store.async_delay_save(lambda: {
            "last_call": self.poll.last_call, "last_success": self.poll.last_success, "failures": self.poll.failures,
            "seen_contracts": self.seen_contracts,
            # Only the control log is kept (the part summarize reads), never the rest of the answer.
            "control_log": {"data": {"controlLogInfo": ((self.last_detail or {}).get("data") or {}).get("controlLogInfo")}}
            if self.last_detail else None,
        }, 1)

    @property
    def fresh(self) -> bool:
        last = self.poll.last_success
        return last is not None and _now() - last <= STALE_S

    def daylight_and_feed_in(self) -> tuple[bool, float | None]:
        """Whether it is daylight (sun, or the optional PV sensor) and the optional feed-in price."""
        options = self.entry.options
        sun = self.hass.states.get("sun.sun")
        daylight = policy.is_daylight(sun.state if sun else None, _float_state(self.hass, options.get(CONF_PV_ENTITY)))
        return daylight, _float_state(self.hass, options.get(CONF_FEED_IN_ENTITY))

    async def _async_update_data(self) -> ControlState | None:
        now = _now()
        daylight, feed_in = self.daylight_and_feed_in()
        if not policy.due(self.poll, now, daylight, feed_in):
            return self.data   # nothing due: keep the last state (entities go stale on their own)
        try:
            detail = await self.client.detail(self.entry.data[CONF_SERVICE_POINT_ID])
            if not has_control_log(detail):
                raise VexError("no control log in the answer")
        except VexAuthError as err:
            self.poll = policy.after_call(self.poll, now, ok=False)
            self._remember()
            self.refusals += 1
            if self.refusals >= REFUSALS_BEFORE_REAUTH:
                raise ConfigEntryAuthFailed(str(err)) from err
            if self.refusals == 1:
                _LOGGER.warning("VE-X refused the key (%s); asking for a new one after %s refusals in a row",
                                err, REFUSALS_BEFORE_REAUTH)
            return self.data
        except VexError as err:
            self.poll = policy.after_call(self.poll, now, ok=False)
            self._remember()
            self.refusals = 0
            # Logged once as it goes, so the reason survives in the log (HA's pattern for an
            # unavailable service); later failures in the same run only at debug.
            if self.poll.failures == 1:
                _LOGGER.warning("VE-X call failed: %s", err)
            elif self.poll.failures == policy.FAILURES_BEFORE_PAUSE:
                _LOGGER.warning("VE-X failed %s times in a row (%s); calling once an hour until it answers",
                                self.poll.failures, err)
            else:
                _LOGGER.debug("VE-X call failed (%s failures in a row): %s", self.poll.failures, err)
            return self.data
        state = summarize(detail, self.entry.data.get(CONF_INVERTER_ID), self.entry.data.get(CONF_BATTERY_ID))
        if self.poll.failures:
            _LOGGER.info("VE-X answering again after %s failed calls", self.poll.failures)
        self.poll = policy.after_call(self.poll, now, ok=True)
        self.refusals = 0
        self.last_detail = detail
        if state.inverter_contract_id and state.inverter_contract_id not in self.seen_contracts:
            self.seen_contracts.append(state.inverter_contract_id)
        self._remember()
        return state
