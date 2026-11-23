"""Turn a VE-X service-point detail response into entity values (pure, no HA imports).

Village's rule (ticket #6097): export control is on when the inverter command's
`enableExportControl` is true and `exportPSetPoint` is numeric; that number (sent as a
string, e.g. "0.05") is the allowed export in kW. `currentPower` uses VE-X's sign:
negative is generation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


def _number(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def has_control_log(detail: Any) -> bool:
    """A usable answer: `data.controlLogInfo.endPoints` is a list (it may be empty).

    A 200 with an error body, or any other shape, is a failed call, not "no commands".
    """
    if not isinstance(detail, dict):
        return False
    info = (detail.get("data") or {}).get("controlLogInfo") if isinstance(detail.get("data"), dict) else None
    return isinstance(info, dict) and isinstance(info.get("endPoints"), list)


def curtailment_active(state: "ControlState", contract_id: str | None) -> bool:
    """An export limit is in force, set by `contract_id` when one is configured.

    The customer API has no contract types, so the solar plan's contract can only be named
    by the user (the options list the ones seen in the log). Without one, any export limit
    counts, which is right where only a solar plan limits export.
    """
    if not state.export_control_active:
        return False
    return contract_id in (None, "") or state.inverter_contract_id == contract_id


def end_points(detail: dict[str, Any]) -> list[dict[str, Any]]:
    """The control-log entries, exactly as VE-X sent them (the archive keeps this shape)."""
    info = ((detail or {}).get("data") or {}).get("controlLogInfo") or {}
    entries = info.get("endPoints") or []
    return [e for e in entries if isinstance(e, dict)]


@dataclass
class ControlState:
    inverter_command_start: str | None = None
    export_control_active: bool = False
    allowed_export_kw: float | None = None
    inverter_current_power_kw: float | None = None
    inverter_power_setpoint_kw: float | None = None
    inverter_contract_id: str | None = None
    inverter_summary: str | None = None
    battery_mode: str | None = None
    battery_power_setpoint_kw: float | None = None
    battery_soc_discharge_threshold: float | None = None
    battery_contract_id: str | None = None
    end_points: list[dict[str, Any]] = field(default_factory=list)


def summarize(detail: dict[str, Any], inverter_id: str | None, battery_id: str | None) -> ControlState:
    entries = end_points(detail)
    by_id = {e.get("endPointId"): e for e in entries}
    inverter = by_id.get(inverter_id) or next((e for e in entries if e.get("controlAction") == "controlInverter"), None)
    battery = by_id.get(battery_id) or next((e for e in entries if e.get("controlAction") == "controlBattery"), None)
    state = ControlState(end_points=entries)
    if inverter:
        limit = _number(inverter.get("exportPSetPoint"))
        enabled = inverter.get("enableExportControl") in (True, 1, "1", "true", "True")
        state.inverter_command_start = inverter.get("start")
        state.export_control_active = bool(enabled and limit is not None)
        state.allowed_export_kw = limit if state.export_control_active else None
        state.inverter_current_power_kw = _number(inverter.get("currentPower"))
        state.inverter_power_setpoint_kw = _number(inverter.get("pSetPoint"))
        state.inverter_contract_id = inverter.get("triggerById")
        state.inverter_summary = inverter.get("summaryText")
    if battery:
        state.battery_mode = battery.get("batteryMode")
        state.battery_power_setpoint_kw = _number(battery.get("pSetPoint"))
        state.battery_soc_discharge_threshold = _number(battery.get("socDischargeThres"))
        state.battery_contract_id = battery.get("triggerById")
    return state
