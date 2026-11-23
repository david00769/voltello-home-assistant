"""The Voltello integration's pure logic: polling rule, control-log parsing, discovery.

Hand-written fixtures only (made-up ids): no recorded VE-X response belongs in this repo.
"""

from __future__ import annotations

from custom_components.voltello_vex import control_log, discovery, policy

ACTIVE = {"data": {"controlLogInfo": {"endPoints": [
    {"start": "20260101T031102Z", "controlAction": "controlBattery", "triggerBy": "CONTRACT", "triggerById": "CON_BAT",
     "batteryMode": "scm", "duration": 600, "pSetPoint": 20, "socDischargeThres": 21, "endPointId": "BAT1"},
    {"start": "20260101T031046Z", "controlAction": "controlInverter", "triggerBy": "CONTRACT", "triggerById": "CON_SOLAR",
     "currentPower": -9.1688, "enableExportControl": True, "exportPSetPoint": "0.05", "endPointId": "INV1",
     "summaryText": "DER export limit set from 9.2 kW to 0.05 kW"},
]}}}
INACTIVE = {"data": {"controlLogInfo": {"endPoints": [
    {"start": "20260101T082546Z", "controlAction": "controlInverter", "triggerById": "CON_SOLAR", "endPointId": "INV1",
     "enableExportControl": False, "exportPSetPoint": None, "pSetPoint": 20, "currentPower": -0.338},
]}}}


def test_active_export_limit_is_read_as_village_describes():
    s = control_log.summarize(ACTIVE, "INV1", "BAT1")
    assert s.export_control_active and s.allowed_export_kw == 0.05      # "0.05" arrives as a string
    assert s.inverter_current_power_kw == -9.1688 and s.inverter_power_setpoint_kw is None
    assert s.inverter_contract_id == "CON_SOLAR" and s.inverter_command_start == "20260101T031046Z"
    assert (s.battery_mode, s.battery_power_setpoint_kw, s.battery_soc_discharge_threshold) == ("scm", 20.0, 21.0)
    assert s.end_points == ACTIVE["data"]["controlLogInfo"]["endPoints"]  # the archive's shape, untouched


def test_no_limit_when_disabled_or_setpoint_missing_or_log_empty():
    s = control_log.summarize(INACTIVE, "INV1", None)
    assert not s.export_control_active and s.allowed_export_kw is None and s.inverter_power_setpoint_kw == 20.0
    enabled_no_number = {"data": {"controlLogInfo": {"endPoints": [
        {"controlAction": "controlInverter", "endPointId": "INV1", "enableExportControl": True, "exportPSetPoint": ""}]}}}
    assert not control_log.summarize(enabled_no_number, "INV1", None).export_control_active
    empty = control_log.summarize({"result": "error"}, "INV1", "BAT1")
    assert empty.end_points == [] and not empty.export_control_active and empty.battery_mode is None


def test_an_answer_without_a_control_log_is_not_a_good_read():
    assert control_log.has_control_log(ACTIVE) and control_log.has_control_log({"data": {"controlLogInfo": {"endPoints": []}}})
    for bad in ({"result": "error"}, {"data": {}}, {"data": {"controlLogInfo": {}}}, [], "x", None):
        assert not control_log.has_control_log(bad), bad
    assert control_log._number("nan") is None and control_log._number("inf") is None


def test_curtailment_follows_the_configured_solar_contract():
    s = control_log.summarize(ACTIVE, "INV1", "BAT1")
    assert control_log.curtailment_active(s, None) and control_log.curtailment_active(s, "CON_SOLAR")
    assert not control_log.curtailment_active(s, "CON_OTHER")
    assert not control_log.curtailment_active(control_log.summarize(INACTIVE, "INV1", None), None)


def test_commands_are_found_by_action_when_the_endpoint_id_is_unknown():
    s = control_log.summarize(ACTIVE, None, None)
    assert s.export_control_active and s.battery_mode == "scm"


def test_polling_rule_daylight_cycle_quiet_and_pause():
    p = policy.PollState()
    assert policy.due(p, 1000, daylight=False, feed_in=None)              # an install's first read: any hour
    assert policy.due(p, 1000, daylight=True, feed_in=None)
    p = policy.after_call(p, 1000, ok=True)
    assert not policy.due(p, 9000, daylight=False, feed_in=None)          # after that, nothing overnight
    assert not policy.due(p, 1299, True, None) and policy.due(p, 1300, True, None)   # 5-minute floor
    assert not policy.due(p, 1899, True, 0.05) and policy.due(p, 1900, True, 0.05)   # quiet: 15 min
    for k in range(3):
        p = policy.after_call(p, 2000 + k, ok=False)
    assert p.failures == 3 and p.last_success == 1000
    assert not policy.due(p, 2002 + 3599, True, None) and policy.due(p, 2002 + 3600, True, None)  # pause 1 h
    assert policy.after_call(p, 9000, ok=True).failures == 0


def test_daylight_from_sun_or_pv():
    assert policy.is_daylight("above_horizon", None)
    assert not policy.is_daylight("below_horizon", 10)
    assert policy.is_daylight(None, 51) and not policy.is_daylight(None, None)


def test_discovery_finds_service_points_and_typed_endpoints():
    assert discovery.service_point_ids({"data": {"servicePoints": [{"servicePointId": "SP1"}, {"x": 1}]}}) == ["SP1"]
    der = {"data": {"endPoints": [
        {"endPointId": "MET1", "endPointType": "smartMeter", "control": False},
        {"endPointId": "INV0", "endPointType": "smartInverter", "control": False},
        {"endPointId": "INV1", "endPointType": "smartInverter", "control": True},
        {"endPointId": "BAT1", "endPointType": "battery", "control": False},
    ]}}
    found = discovery.endpoints(der)
    assert (found.inverter, found.battery, found.meter) == ("INV1", "BAT1", "MET1")   # the controllable inverter
    assert discovery.endpoints({}).inverter is None
