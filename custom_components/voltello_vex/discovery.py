"""Find a site's service points and endpoints from VE-X responses (pure, no HA imports).

So nobody types ids: the service-point list gives the service points, and the DER call
gives the endpoints with their types (`endPointType`: smartInverter, battery, smartMeter).
Contracts have no list call in the customer API; they are learned from the control log
(`triggerById` of each command).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def service_point_ids(listing: dict[str, Any]) -> list[str]:
    points = ((listing or {}).get("data") or {}).get("servicePoints") or []
    return [p["servicePointId"] for p in points if isinstance(p, dict) and p.get("servicePointId")]


@dataclass
class Endpoints:
    inverter: str | None = None
    battery: str | None = None
    meter: str | None = None


def endpoints(der: dict[str, Any]) -> Endpoints:
    found = Endpoints()
    items = [e for e in (((der or {}).get("data") or {}).get("endPoints") or []) if isinstance(e, dict)]
    inverters = [e for e in items if e.get("endPointType") == "smartInverter"]
    # Prefer the inverter VE-X can control: that is the one export limits are sent to.
    inverters.sort(key=lambda e: not e.get("control"))
    if inverters:
        found.inverter = inverters[0].get("endPointId")
    found.battery = next((e.get("endPointId") for e in items if e.get("endPointType") == "battery"), None)
    found.meter = next((e.get("endPointId") for e in items if e.get("endPointType") == "smartMeter"), None)
    return found
