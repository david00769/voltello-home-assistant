"""Constants for the Voltello (VE-X) integration."""

from __future__ import annotations

DOMAIN = "voltello_vex"
DEFAULT_NAME = "Voltello"
DEFAULT_BASE_URL = "https://acapi.vecddevau1.village.energy/xv1"

CONF_API_KEY = "api_key"
CONF_CUSTOMER_ID = "customer_id"
CONF_BASE_URL = "base_url"
CONF_SERVICE_POINT_ID = "service_point_id"
CONF_INVERTER_ID = "inverter_endpoint_id"
CONF_BATTERY_ID = "battery_endpoint_id"
CONF_METER_ID = "meter_endpoint_id"
CONF_FEED_IN_ENTITY = "feed_in_price_entity"
CONF_PV_ENTITY = "pv_power_entity"
CONF_CURTAILMENT_CONTRACT = "curtailment_contract_id"
STORAGE_VERSION = 1

# Polling, the restraint Village asked for (ticket #6097). The floor is a constant, not an
# option: one call per Voltello cycle is all the control log can change.
CYCLE_S = 300              # Voltello re-issues its commands every 300 s
QUIET_S = 900              # feed-in clearly positive: nothing to curtail
QUIET_FEED_IN_ABOVE = 0.02  # $/kWh (Amber's unit)
DAYLIGHT_PV_W = 50
FAILURES_BEFORE_PAUSE = 3
# VE-X has refused good keys before (a header bug, fixed by Village): ask for a new key only
# after this many refusals in a row.
REFUSALS_BEFORE_REAUTH = 3
PAUSE_S = 3600             # after FAILURES_BEFORE_PAUSE failures in a row
STALE_S = 1200             # entities unavailable when the last good read is older
TICK_S = 60                # the coordinator wakes each minute; calls only when due
