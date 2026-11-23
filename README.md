# Voltello (VE-X, unofficial) for Home Assistant

A Home Assistant integration that reads what your Voltello
plans are doing to your battery and inverter, through Village Energy's VE-X customer API:
whether export is being limited and to what, the battery mode and set-points in force,
and the raw control log.

Read-only: it changes nothing on your system. Unofficial: not made or endorsed by Village
Energy.

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=david00769&repository=voltello-home-assistant&category=integration)

## Why you might want it

Voltello runs your battery and solar export through "plans", for example charging from
the grid when the wholesale price is low, or limiting export when exporting would cost
you money. The Voltello app shows what it decided, but Home Assistant can't see it, so
your automations can't respond to it.

With this integration, Home Assistant knows, every five minutes in daylight:

- **when your solar is being held back** (an export limit is in force). That is spare
  energy you could use instead: pre-cool or pre-heat the house, heat water, charge a car.
  For example, an automation can start the air conditioner when
  `binary_sensor.voltello_curtailment_active` turns on.
- **what the battery has been told to do** (self-consume, idle, charge, discharge, and at
  what power), so a dashboard can show it and a charging plan can be checked against it;
- **a record over time**, so you can see how often your solar was curtailed and how your
  plans behaved.

It was written for one household on Amber Electric with a BLUETTI battery,
which uses it to soak up curtailed solar with air-conditioning and to work out when a grid
top-up of the battery pays. It should work for any Voltello customer with VE-X API
access; nothing in it is specific to that house.

## What it gives you

One device per Voltello service point, with:
- **Export control:** `binary_sensor.voltello_export_control_active`;
  `binary_sensor.voltello_curtailment_active`, an export limit set by your solar plan's
  contract (the option below; without it, any export limit counts), with attribute
  `contract_id`; `sensor.voltello_allowed_export` (kW, unknown when no limit applies).
- **Inverter command in force:** `sensor.voltello_inverter_current_power` (kW; VE-X sign,
  negative is generation); `sensor.voltello_inverter_power_setpoint`.
- **Battery command:** `sensor.voltello_battery_mode` (scm, idle, ...);
  `sensor.voltello_battery_power_setpoint`; `sensor.voltello_battery_soc_discharge_threshold`.
- **Diagnostic:** `sensor.voltello_vex_detail` (raw control log as the `endPoints`
  attribute); `binary_sensor.voltello_vex_stale`; `sensor.voltello_vex_failures`.
- **Diagnostics download:** the key, customer id, service point, endpoint and contract ids,
  NMI and address are all redacted.

Entities go unavailable 20 minutes after the last good read (overnight, during backoff).

## Setup

1. In the Voltello app, create an API key: Menu, Manage Access, API Access. Ask Village
   Energy support for your customer id (the app does not show it).
2. Install it, then restart Home Assistant:
   - **HACS:** use the button above, or HACS, the three-dot menu, Custom repositories,
     add `https://github.com/david00769/voltello-home-assistant` as type Integration, then
     download "Voltello (VE-X, unofficial)";
   - **or by hand:** copy `custom_components/voltello_vex/` into your HA
     `config/custom_components/`.
3. Add the integration and enter the key, customer id and (normally unchanged) base URL.
   The service point and the inverter, battery and meter endpoints are discovered.
4. Optional, under the integration's options:
   - a feed-in price sensor (slows polling to 15 min while feed-in is above 2 c);
   - a PV power sensor (a daylight fallback);
   - **the solar plan contract** (e.g. Solar for Amber), chosen from the contracts seen in
     the control log. The customer API has no contract types, so it cannot tell which plan
     is the solar one by itself. Set it if more than one plan can limit export.

## Polling (fixed in code)

- One call per 5 minutes in daylight, nothing overnight (except the very first read after
  you add it, so a new install shows its state at once).
- 15 minutes while feed-in is above 2 c.
- After 3 failures in a row, one call an hour until one succeeds.
- A refused key (401/403) asks for a new one (re-authentication) after 3 refusals in a row:
  about 10 minutes of daylight polling, or the next morning if it happens at night.
- An answer without a control log is a failed call; the last good state is kept.
- The last call time is stored, so a restart, reload or options change adds no call.
- At most 12 calls an hour.

## Tests

Home Assistant's test harness, pinned so it matches one HA release (Python 3.14 with
`pytest-homeassistant-custom-component` 0.13.375 = HA 2026.10.4; `requirements_test.txt`):

    python -m pip install -r requirements_test.txt
    python -m pytest -q

They cover the polling rule, control-log parsing and discovery, the config flow (setup,
reauth, options), entities and ids, staleness, restarts, and diagnostics redaction. All
fixtures are hand-written with made-up ids; no test calls VE-X. CI also runs `hassfest`
and the HACS check.

## License

PolyForm Noncommercial 1.0.0 (see `LICENSE`): free for personal and other noncommercial
use. Commercial licenses from david00769 (davidsiroky@me.com). Because HACS does not
recognise this license, install it as a HACS custom repository; it is not in the HACS
default list.
