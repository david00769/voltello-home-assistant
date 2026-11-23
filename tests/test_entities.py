"""Polling, entity values and ids, staleness, reauth on a refused key, diagnostics redaction."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.components.diagnostics import REDACTED
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.voltello_vex.const import DOMAIN
from custom_components.voltello_vex.diagnostics import async_get_config_entry_diagnostics

from .conftest import DETAIL_ACTIVE, ENTRY_DATA, SP, URL_DETAIL

CLOCK = "custom_components.voltello_vex.coordinator._now"


async def _setup(hass: HomeAssistant, now: float, sun: str = "above_horizon", ok: bool = True) -> MockConfigEntry:
    hass.states.async_set("sun.sun", sun)
    entry = MockConfigEntry(domain=DOMAIN, unique_id=SP, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    with patch(CLOCK, return_value=now):
        assert await hass.config_entries.async_setup(entry.entry_id) is ok
        await hass.async_block_till_done()
    return entry


async def test_entity_ids_are_stable_and_read_an_active_limit(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(URL_DETAIL, json=DETAIL_ACTIVE)
    with patch(CLOCK, return_value=1000.0):
        await _setup(hass, 1000.0)
        # These ids are a public contract: dashboards, automations and recorder history use them.
        expected = {
            "binary_sensor.voltello_export_control_active": "on",
            "binary_sensor.voltello_curtailment_active": "on",
            "binary_sensor.voltello_vex_stale": "off",
            "sensor.voltello_allowed_export": "0.05",
            "sensor.voltello_inverter_current_power": "-9.1688",
            "sensor.voltello_inverter_power_setpoint": "unknown",
            "sensor.voltello_battery_mode": "scm",
            "sensor.voltello_battery_power_setpoint": "20.0",
            "sensor.voltello_battery_soc_discharge_threshold": "21.0",
            "sensor.voltello_vex_detail": "20260101T031046Z",
            "sensor.voltello_vex_failures": "0",
        }
        assert {e: hass.states.get(e).state for e in expected} == expected
    detail = hass.states.get("sensor.voltello_vex_detail")
    assert detail.attributes["endPoints"] == DETAIL_ACTIVE["data"]["controlLogInfo"]["endPoints"]
    assert hass.states.get("binary_sensor.voltello_curtailment_active").attributes["contract_id"] == "CON_SOLAR"
    assert aioclient_mock.mock_calls[0][1].query["includeControlLogInfo"] == "true"


async def test_first_read_at_any_hour_then_nothing_at_night_and_one_call_per_cycle(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(URL_DETAIL, json=DETAIL_ACTIVE)
    entry = await _setup(hass, 1000.0, sun="below_horizon")
    assert aioclient_mock.call_count == 1                     # a new install reads once, even at night
    assert hass.states.get("binary_sensor.voltello_export_control_active").state == "on"
    coordinator = entry.runtime_data
    with patch(CLOCK, return_value=1000.0 + 3600):
        await coordinator.async_refresh()
    assert aioclient_mock.call_count == 1                     # then nothing overnight
    hass.states.async_set("sun.sun", "above_horizon")
    for now, calls in ((4600.0, 2), (4700.0, 2), (4899.0, 2), (4900.0, 3)):
        with patch(CLOCK, return_value=now):
            await coordinator.async_refresh()
        assert aioclient_mock.call_count == calls, now


async def test_entities_go_unavailable_when_the_read_is_stale(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(URL_DETAIL, json=DETAIL_ACTIVE)
    entry = await _setup(hass, 1000.0)
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL_DETAIL, status=503)
    coordinator = entry.runtime_data
    with patch(CLOCK, return_value=1000.0 + 1300):
        await coordinator.async_refresh()
        coordinator.async_update_listeners()
        await hass.async_block_till_done()
        assert hass.states.get("binary_sensor.voltello_export_control_active").state == "unavailable"
        assert hass.states.get("binary_sensor.voltello_vex_stale").state == "on"
        assert hass.states.get("sensor.voltello_vex_failures").state == "1"


def _reauth_started(hass: HomeAssistant) -> bool:
    return any(f["context"]["source"] == "reauth" for f in hass.config_entries.flow.async_progress())


async def test_three_refusals_in_a_row_start_reauth(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(URL_DETAIL, status=401)
    entry = await _setup(hass, 1000.0)                       # refusal 1: set up, no data
    assert entry.state is ConfigEntryState.LOADED and not _reauth_started(hass)
    coordinator = entry.runtime_data
    with patch(CLOCK, return_value=1300.0):                  # refusal 2
        await coordinator.async_refresh()
    assert not _reauth_started(hass) and coordinator.refusals == 2
    with patch(CLOCK, return_value=1600.0):                  # refusal 3
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    assert _reauth_started(hass)


async def test_a_good_answer_between_refusals_starts_over(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(URL_DETAIL, status=403)
    entry = await _setup(hass, 1000.0)
    coordinator = entry.runtime_data
    with patch(CLOCK, return_value=1300.0):
        await coordinator.async_refresh()
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL_DETAIL, json=DETAIL_ACTIVE)
    with patch(CLOCK, return_value=1600.0):
        await coordinator.async_refresh()
    assert coordinator.refusals == 0 and coordinator.poll.failures == 0
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL_DETAIL, status=403)
    for now in (1900.0, 2200.0):
        with patch(CLOCK, return_value=now):
            await coordinator.async_refresh()
    assert not _reauth_started(hass) and coordinator.refusals == 2


async def test_diagnostics_redact_ids_key_and_address(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(URL_DETAIL, json=DETAIL_ACTIVE)
    entry = await _setup(hass, 1000.0)
    # Every option set, the solar contract included (a clean install leaked it before).
    hass.config_entries.async_update_entry(entry, options={
        "curtailment_contract_id": "CON_SOLAR", "feed_in_price_entity": "sensor.feed_in", "pv_power_entity": "sensor.pv"})
    diag = await async_get_config_entry_diagnostics(hass, entry)
    text = str(diag)
    for secret in ("KEY1", "CUST1", "SP1", "INV1", "BAT1", "MET1", "CON_SOLAR", "NMI0", "1 Example St"):
        assert secret not in text, secret
    assert set(diag) == {"entry", "poll", "control_log", "seen_contracts"}   # nothing else of the answer
    assert diag["entry"]["data"]["api_key"] == REDACTED and diag["poll"]["failures"] == 0


async def test_an_error_body_is_a_failed_call_not_no_commands(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(URL_DETAIL, json=DETAIL_ACTIVE)
    entry = await _setup(hass, 1000.0)
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL_DETAIL, json={"result": "error"})
    coordinator = entry.runtime_data
    with patch(CLOCK, return_value=1300.0):
        await coordinator.async_refresh()
    assert coordinator.poll.failures == 1 and coordinator.poll.last_success == 1000.0
    assert coordinator.data.export_control_active          # the last good state is kept


async def test_a_restart_inside_the_cycle_makes_no_call(hass: HomeAssistant, aioclient_mock, hass_storage) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=SP, data=ENTRY_DATA, entry_id="E1")
    hass_storage[f"{DOMAIN}.E1"] = {"version": 1, "minor_version": 1, "key": f"{DOMAIN}.E1",
                                    "data": {"last_call": 1000.0, "failures": 0, "seen_contracts": ["CON_SOLAR"]}}
    aioclient_mock.get(URL_DETAIL, json=DETAIL_ACTIVE)
    hass.states.async_set("sun.sun", "above_horizon")
    entry.add_to_hass(hass)
    with patch(CLOCK, return_value=1200.0):                 # 200 s after the last call
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert aioclient_mock.call_count == 0
    assert entry.runtime_data.seen_contracts == ["CON_SOLAR"]


async def test_options_set_the_solar_contract_and_curtailment_follows_it(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(URL_DETAIL, json=DETAIL_ACTIVE)
    with patch(CLOCK, return_value=1000.0):
        entry = await _setup(hass, 1000.0)
        assert entry.runtime_data.seen_contracts == ["CON_SOLAR"]
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(result["flow_id"], {"curtailment_contract_id": "CON_OTHER"})
        assert entry.options["curtailment_contract_id"] == "CON_OTHER"
        entry.runtime_data.async_update_listeners()
        await hass.async_block_till_done()
        assert hass.states.get("binary_sensor.voltello_curtailment_active").state == "off"
        assert hass.states.get("binary_sensor.voltello_export_control_active").state == "on"
    assert aioclient_mock.call_count == 1                   # saving options made no call


async def test_a_restart_inside_the_stale_window_shows_the_last_reading(hass: HomeAssistant, aioclient_mock, hass_storage) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=SP, data=ENTRY_DATA, entry_id="E2")
    hass_storage[f"{DOMAIN}.E2"] = {"version": 1, "minor_version": 1, "key": f"{DOMAIN}.E2", "data": {
        "last_call": 1000.0, "last_success": 1000.0, "failures": 0, "seen_contracts": ["CON_SOLAR"],
        "control_log": {"data": {"controlLogInfo": DETAIL_ACTIVE["data"]["controlLogInfo"]}}}}
    hass.states.async_set("sun.sun", "above_horizon")
    entry.add_to_hass(hass)
    with patch(CLOCK, return_value=1200.0):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert aioclient_mock.call_count == 0
        assert hass.states.get("binary_sensor.voltello_export_control_active").state == "on"
    with patch(CLOCK, return_value=1000.0 + 1201):      # past 20 min with no new read: unavailable
        entry.runtime_data.async_update_listeners()
        await hass.async_block_till_done()
        assert hass.states.get("binary_sensor.voltello_export_control_active").state == "unavailable"


async def test_a_failure_logs_its_reason_once_and_the_recovery(hass: HomeAssistant, aioclient_mock, caplog) -> None:
    aioclient_mock.get(URL_DETAIL, json=DETAIL_ACTIVE)
    entry = await _setup(hass, 1000.0)
    coordinator = entry.runtime_data
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL_DETAIL, status=503)
    for now in (1300.0, 1600.0, 1900.0, 5500.0):
        with patch(CLOCK, return_value=now):
            await coordinator.async_refresh()
    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING" and "VE-X" in r.getMessage()]
    assert len(warnings) == 2 and "503" in warnings[0] and "once an hour" in warnings[1]
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL_DETAIL, json=DETAIL_ACTIVE)
    with patch(CLOCK, return_value=5500.0 + 3600):
        await coordinator.async_refresh()
    assert any("answering again after 4 failed calls" in r.getMessage() for r in caplog.records)
