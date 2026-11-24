# JLR Data Hub for Home Assistant

Read-only data from a Jaguar or Land Rover in Home Assistant, through the **JLR Data Hub**: the owner API JLR set up
for the EU Data Act. Battery, range, charging, locks, doors and windows, tyres, 12 V battery, odometer, service, the
car's position and its last trip. There are no remote commands, because the Data Hub has none.

Tested with a UK 2020 Jaguar I-Pace (November 2026).

## Two ways to connect

JLR allows **one Data Hub credential per account**, so pick one:

| | Direct | Via jlr-server |
|---|---|---|
| Who holds the JLR credential | This Home Assistant | A [jlr-server](#via-jlr-server) you already run |
| Updates | Live stream (MQTT), plus a REST poll every 10 minutes | Polls the server every 60 s (30–300 s) |
| Last trip | Distance, time, speed | Also the battery it used (`soc_used`), from the server's history |
| Needs | A JLR account with the car added | The server's address and API token |

If a jlr-server already holds your credential, use it: setting up direct mode means deleting the server's credential
in the portal, and the server stops working.

## Install

**HACS:** HACS → ⋮ → Custom repositories → add this repository as an *Integration* → install **JLR Data Hub** →
restart Home Assistant.

**By hand:** copy `custom_components/jlr_data_hub` into your `config/custom_components/` folder and restart.

Then Settings → Devices & services → Add integration → **JLR Data Hub**.

## Direct

1. Choose **Connect directly to JLR**. Home Assistant makes its own RSA key and shows a certificate. Copy it into a
   file (`jlr.pem`). The key stays in Home Assistant (`config/.storage/jlr_data_hub/`, readable only by Home
   Assistant) and is deleted with the integration.
2. In the [JLR Data Hub portal](https://developer.jlr.com), delete any existing credential (only one is allowed), then
   create one: **device-based**, your car, every category (Status, EV, Position, Journeys…), uploading `jlr.pem`.
   Note the **client ID**.
3. To stream, also create a **stream configuration** with every streamable signal and note its **username**. Without
   it the integration polls every 10 minutes.
4. Back in Home Assistant, enter the client ID, the VIN and the stream username (the account ID is optional: it's read
   from JLR after sign-in).
5. Home Assistant shows a link and a code. Open it, sign in with your JLR account and approve. Setup finishes by
   itself.

The sign-in refreshes itself (the 10-minute poll keeps it alive). If it ever lapses, Home Assistant asks you to sign
in again with the same credential; you don't need to touch the portal.

Options: change the stream username or account ID.

## Via jlr-server

`jlr-server` is a small always-on service (FastAPI, in the `Utils-ios` repository under `jlr-server/`) that holds the
credential, stays on the stream, and records history in SQLite, which is how it knows the battery % before and after
each trip.

1. Choose **Read from my jlr-server**.
2. Enter its address, for example `http://192.168.1.10:9293`, and its API token (`API_TOKEN` in the server's
   `.env`, e.g. `/opt/stacks/jlr/.env`).

The integration reads `/api/state`, `/api/journeys` and `/api/status`. If the token changes, Home Assistant asks for
the new one. Options: how often to read the server.

## Entities

One device per car.

| Entity | Notes |
|---|---|
| Battery | % as shown in the car |
| Range | km |
| Charging state | charging, complete, plugged in, unplugged, fault; the raw JLR status is an attribute |
| Charge limit | % (unavailable when the car hasn't set one) |
| Time to full | minutes; 0 once complete, unavailable when not plugged in |
| Charge session energy | kWh added in the current or last session |
| Tyre pressure ×4 | kPa (change the unit to bar or psi in the entity settings); the tyre warning is an attribute |
| 12 V battery | volts (12 V battery level %, if the car sends it, is disabled by default) |
| Odometer | km (the car sends metres) |
| Distance to service | km |
| Last trip | distance in km; attributes: start and end time and place, duration, average speed, and with jlr-server `soc_start`, `soc_end`, `soc_used` (from the server's `socStart`/`socEnd`/`socUsed`) |
| Plugged in, Charging | |
| Lock | Home Assistant's lock class: **on means unlocked** |
| Doors ×4, Windows ×4, Boot, Bonnet | on means open |
| Tyre pressure warning, Washer fluid low | problems |
| Location | `device_tracker`, the last position the car reported (it reports when switched off) |
| Stream, JLR sign-in, Last reported | diagnostics |

The car sends `-1` for values it hasn't set; those show as unavailable/unknown rather than −1.

`socUsed` is left out when the server can't work it out: when there's no battery reading close enough before and
after the trip, or the battery went up in between (it was charged).

## How JLR really behaves

Learned against a real I-Pace; where this differs from JLR's docs, this is what works:

- Every value arrives as a string (`"90"`, `"CLOSED"`, `"LOCKED"`), with no units. Odometer is in metres. Tyre
  pressure is in kPa (the catalogue says hPa; values over 600 are read as hPa).
- The MQTT client ID must be the stream username; only exact `account/{id}/vehicles/{vin}/{category}` topics are
  allowed, one per SUBSCRIBE; use MQTT 5. The streaming password is a 5-minute client-credentials token, so the
  stream reconnects with a fresh token whenever the broker drops it.
- Everything is signed with PS256 (RSASSA-PSS, SHA-256, 32-byte salt): the portal certificate, the client assertion
  (`private_key_jwt`, there's no client secret) and the DPoP proofs.

## Development

`custom_components/jlr_data_hub/jlr_datahub/` is the Python client from `Utils-ios/jlr-server`, vendored with two
small changes (see its `__init__.py`). `vehicle.py` turns signals into readings; it's a port of the Swift package's
`VehicleState` accessors.

```sh
python3.13 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest
```

The fixtures in `tests/fixtures/` are a real jlr-server response with the VIN and positions replaced.
