"""Diagnostics download: polling state and the last control log, with identifiers redacted."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import VexConfigEntry
from .const import (
    CONF_API_KEY, CONF_BATTERY_ID, CONF_CURTAILMENT_CONTRACT, CONF_CUSTOMER_ID, CONF_INVERTER_ID, CONF_METER_ID,
    CONF_SERVICE_POINT_ID,
)

REDACT = {
    CONF_API_KEY, CONF_CUSTOMER_ID, CONF_SERVICE_POINT_ID, CONF_INVERTER_ID, CONF_BATTERY_ID, CONF_METER_ID,
    CONF_CURTAILMENT_CONTRACT,
    "servicePointId", "endPointId", "meterEndPointId", "triggerById", "nationalMeteringId", "serviceEntityId",
    "utilityIdentifier", "location", "serialNo", "contract_id",
}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: VexConfigEntry) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return async_redact_data({
        "entry": {"data": dict(entry.data), "options": dict(entry.options)},
        "poll": {"last_call": coordinator.poll.last_call, "last_success": coordinator.poll.last_success,
                 "failures": coordinator.poll.failures, "fresh": coordinator.fresh},
        # Allowlist: only the control log leaves; the rest of the answer (address, NMI, ...) never.
        "control_log": ((coordinator.last_detail or {}).get("data") or {}).get("controlLogInfo"),
        "seen_contracts": coordinator.seen_contracts,
    }, REDACT | {"seen_contracts"})
