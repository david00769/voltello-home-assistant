"""Config flow: the API key and customer id once; everything else is discovered."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VexAuthError, VexClient, VexError
from .const import (
    CONF_API_KEY, CONF_BASE_URL, CONF_BATTERY_ID, CONF_CURTAILMENT_CONTRACT, CONF_CUSTOMER_ID, CONF_FEED_IN_ENTITY,
    CONF_INVERTER_ID, CONF_METER_ID, CONF_PV_ENTITY, CONF_SERVICE_POINT_ID, DEFAULT_BASE_URL,
    DEFAULT_NAME, DOMAIN,
)
from .control_log import has_control_log
from .discovery import endpoints, service_point_ids

USER_SCHEMA = vol.Schema({
    vol.Required(CONF_API_KEY): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
    vol.Required(CONF_CUSTOMER_ID): str,
    vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
})


def base_url_ok(url: str) -> bool:
    """https only: the API key travels in a header. Plain http only to this machine (testing)."""
    try:
        parts = urlparse(url)
        host = parts.hostname
    except ValueError:          # e.g. an unclosed IPv6 bracket
        return False
    if parts.scheme == "https":
        return bool(host)
    return parts.scheme == "http" and host in ("localhost", "127.0.0.1", "::1")


class VoltelloVexConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._input: dict[str, Any] = {}
        self._points: list[str] = []

    def _client(self, data: Mapping[str, Any]) -> VexClient:
        return VexClient(async_get_clientsession(self.hass), data[CONF_BASE_URL], data[CONF_API_KEY], data[CONF_CUSTOMER_ID])

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = {**user_input, CONF_BASE_URL: user_input[CONF_BASE_URL].strip()}
        if user_input is not None and not base_url_ok(user_input[CONF_BASE_URL]):
            errors[CONF_BASE_URL] = "invalid_url"
        elif user_input is not None:
            try:
                self._points = service_point_ids(await self._client(user_input).service_points())
            except VexAuthError:
                errors["base"] = "invalid_auth"
            except VexError:
                errors["base"] = "cannot_connect"
            else:
                if not self._points:
                    errors["base"] = "no_service_points"
                else:
                    self._input = user_input
                    if len(self._points) == 1:
                        return await self._finish(self._points[0])
                    return await self.async_step_service_point()
        return self.async_show_form(step_id="user", data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input or {}),
                                    errors=errors)

    async def async_step_service_point(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return await self._finish(user_input[CONF_SERVICE_POINT_ID])
        return self.async_show_form(step_id="service_point", data_schema=vol.Schema({
            vol.Required(CONF_SERVICE_POINT_ID): selector.SelectSelector(selector.SelectSelectorConfig(options=self._points)),
        }))

    async def _finish(self, service_point_id: str) -> ConfigFlowResult:
        await self.async_set_unique_id(service_point_id)
        self._abort_if_unique_id_configured()
        try:
            client = self._client(self._input)
            found = endpoints(await client.der(service_point_id))
            if not found.inverter:
                return self.async_abort(reason="no_inverter")
            # The polled call must work too: a key allowed the listing but not the control
            # log would otherwise create an entry that only ever asks to re-authenticate.
            if not has_control_log(await client.detail(service_point_id)):
                return self.async_abort(reason="no_control_log")
        except VexAuthError:
            return self.async_abort(reason="invalid_auth")
        except VexError:
            return self.async_abort(reason="cannot_connect")
        return self.async_create_entry(title=DEFAULT_NAME, data={
            **self._input, CONF_SERVICE_POINT_ID: service_point_id,
            CONF_INVERTER_ID: found.inverter, CONF_BATTERY_ID: found.battery, CONF_METER_ID: found.meter,
        })

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, CONF_API_KEY: user_input[CONF_API_KEY]}
            try:
                client = self._client(data)
                if entry.unique_id not in service_point_ids(await client.service_points()):
                    errors["base"] = "wrong_account"
                elif not has_control_log(await client.detail(entry.unique_id)):
                    errors["base"] = "cannot_connect"
            except VexAuthError:
                errors["base"] = "invalid_auth"
            except VexError:
                errors["base"] = "cannot_connect"
            if not errors:
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(step_id="reauth_confirm", errors=errors, data_schema=vol.Schema({
            vol.Required(CONF_API_KEY): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
        }))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return VoltelloVexOptionsFlow()


class VoltelloVexOptionsFlow(OptionsFlow):
    """Optional: a feed-in price and a PV power sensor (polling), and the solar plan's
    contract (curtailment), chosen from the contracts seen in the control log."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        coordinator = getattr(self.config_entry, "runtime_data", None)
        seen = list(getattr(coordinator, "seen_contracts", []) or [])
        schema = vol.Schema({
            vol.Optional(CONF_FEED_IN_ENTITY): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(CONF_PV_ENTITY): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(CONF_CURTAILMENT_CONTRACT): selector.SelectSelector(
                selector.SelectSelectorConfig(options=seen, custom_value=True)),
        })
        return self.async_show_form(step_id="init", data_schema=self.add_suggested_values_to_schema(schema, self.config_entry.options))
