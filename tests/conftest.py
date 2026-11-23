"""Shared fixtures. Hand-written VE-X answers with made-up ids only."""

from __future__ import annotations

import pytest

from custom_components.voltello_vex.const import DEFAULT_BASE_URL

CTX = "Voltello/CUSTOMERS/Individual/CUST1"
SP = "SP1"
BASE = DEFAULT_BASE_URL

SERVICE_POINTS = {"result": True, "data": {"servicePoints": [{"servicePointId": SP, "nationalMeteringId": "NMI0"}]}}
DER = {"result": True, "data": {"servicePointId": SP, "endPoints": [
    {"endPointId": "INV1", "endPointType": "smartInverter", "type": "SOLAR_PV", "control": True},
    {"endPointId": "MET1", "endPointType": "smartMeter", "type": "OTHER", "control": False},
    {"endPointId": "BAT1", "endPointType": "battery", "type": "STORAGE", "control": False},
]}}
DETAIL_ACTIVE = {"result": True, "data": {"servicePointId": SP, "nationalMeteringId": "NMI0",
                                          "location": {"simple": {"addressLine1": "1 Example St"}},
                                          "controlLogInfo": {"endPoints": [
    {"start": "20260101T031102Z", "controlAction": "controlBattery", "triggerById": "CON_BAT", "endPointId": "BAT1",
     "batteryMode": "scm", "pSetPoint": 20, "socDischargeThres": 21},
    {"start": "20260101T031046Z", "controlAction": "controlInverter", "triggerById": "CON_SOLAR", "endPointId": "INV1",
     "currentPower": -9.1688, "enableExportControl": True, "exportPSetPoint": "0.05"},
]}}}

URL_SERVICE_POINTS = f"{BASE}/get/customer/energy/electricity/servicepoints/{CTX}"
URL_DER = f"{BASE}/get/customer/energy/electricity/servicepoints/{SP}/der/{CTX}"
URL_DETAIL = f"{BASE}/get/customer/energy/electricity/servicepoints/{SP}/{CTX}"

USER_INPUT = {"api_key": "KEY1", "customer_id": "CUST1", "base_url": BASE}
ENTRY_DATA = {**USER_INPUT, "service_point_id": SP, "inverter_endpoint_id": "INV1",
              "battery_endpoint_id": "BAT1", "meter_endpoint_id": "MET1"}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
