# Changelog

## 0.1.1 (2026-11-23)

- A refused key (401/403) asks for a new one only after 3 refusals in a row; until then it
  is an ordinary failed call (backoff, last reading kept, one warning). VE-X has refused
  good keys before, and one bad answer should not stop the integration.
- The base URL must be https (the API key is sent with every request); plain http is
  accepted only for a test server on this machine.
- Failure reasons are logged once (warning) and the recovery once (info).

## 0.1.0 (2026-11-23)

First release.

- Config flow: API key and customer id; the service point and the inverter, battery and
  meter endpoints are discovered.
- Export control, curtailment (by your solar plan's contract), inverter and battery
  commands, the raw control log, staleness and failure count.
- Polling fixed in code: every 5 minutes in daylight, 15 minutes while feed-in is above
  2 c, hourly after 3 failures, none overnight except a new install's first read. The last
  call is stored, so restarts add no call; the last reading is shown again after a restart.
- Diagnostics with every id, the key, the NMI and the address redacted.
