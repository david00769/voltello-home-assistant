"""The config flow: key and customer id once; service point and endpoints discovered."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.voltello_vex.const import DOMAIN

from .conftest import DER, DETAIL_ACTIVE, ENTRY_DATA, SERVICE_POINTS, SP, URL_DER, URL_DETAIL, URL_SERVICE_POINTS, USER_INPUT


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})


async def test_one_service_point_is_discovered_with_its_endpoints(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(URL_SERVICE_POINTS, json=SERVICE_POINTS)
    aioclient_mock.get(URL_DER, json=DER)
    aioclient_mock.get(URL_DETAIL, json=DETAIL_ACTIVE)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == ENTRY_DATA
    assert result["result"].unique_id == SP
    # The key is sent with exactly the header name VE-X expects.
    assert aioclient_mock.mock_calls[0][3]["apiKey"] == "KEY1"


async def test_refused_key_unreachable_and_empty_account(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(URL_SERVICE_POINTS, status=403)
    result = await hass.config_entries.flow.async_configure((await _start(hass))["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "invalid_auth"}
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL_SERVICE_POINTS, status=503)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "cannot_connect"}
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL_SERVICE_POINTS, json={"data": {"servicePoints": []}})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "no_service_points"}


async def test_no_inverter_aborts_and_a_site_is_added_once(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(URL_SERVICE_POINTS, json=SERVICE_POINTS)
    aioclient_mock.get(URL_DER, json={"data": {"endPoints": []}})
    result = await hass.config_entries.flow.async_configure((await _start(hass))["flow_id"], USER_INPUT)
    assert result == {**result, "type": FlowResultType.ABORT, "reason": "no_inverter"}
    MockConfigEntry(domain=DOMAIN, unique_id=SP, data=ENTRY_DATA).add_to_hass(hass)
    result = await hass.config_entries.flow.async_configure((await _start(hass))["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"


async def test_two_service_points_ask_which(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(URL_SERVICE_POINTS, json={"data": {"servicePoints": [{"servicePointId": SP}, {"servicePointId": "SP2"}]}})
    aioclient_mock.get(URL_DER, json=DER)
    aioclient_mock.get(URL_DETAIL, json=DETAIL_ACTIVE)
    result = await hass.config_entries.flow.async_configure((await _start(hass))["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "service_point"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"service_point_id": SP})
    assert result["type"] is FlowResultType.CREATE_ENTRY and result["data"]["inverter_endpoint_id"] == "INV1"


async def test_reauth_replaces_only_the_key(hass: HomeAssistant, aioclient_mock) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=SP, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    aioclient_mock.get(URL_SERVICE_POINTS, json=SERVICE_POINTS)
    aioclient_mock.get(URL_DETAIL, json=DETAIL_ACTIVE)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "KEY2"})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reauth_successful"
    assert entry.data == {**ENTRY_DATA, "api_key": "KEY2"}


async def test_a_key_without_control_log_access_is_refused_at_setup(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(URL_SERVICE_POINTS, json=SERVICE_POINTS)
    aioclient_mock.get(URL_DER, json=DER)
    aioclient_mock.get(URL_DETAIL, json={"result": "error"})
    result = await hass.config_entries.flow.async_configure((await _start(hass))["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "no_control_log"


async def test_reauth_refuses_a_key_for_another_account(hass: HomeAssistant, aioclient_mock) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=SP, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    aioclient_mock.get(URL_SERVICE_POINTS, json={"data": {"servicePoints": [{"servicePointId": "OTHER"}]}})
    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "KEY9"})
    assert result["errors"] == {"base": "wrong_account"} and entry.data["api_key"] == "KEY1"
