---
hide:
  - navigation
---

# JLR Data Hub for Home Assistant

Your Jaguar or Land Rover in Home Assistant: battery, range, charging, locks, doors and windows, tyres, the 12 V
battery, mileage, where it's parked and your trips. It uses the **JLR Data Hub**, the official owner data service JLR
runs for the EU Data Act, so there's no scraping and no shared app login.

[Get started :material-arrow-right:](getting-started/index.md){ .md-button .md-button--primary }
[How it works](how-it-works.md){ .md-button }

<div class="grid cards" markdown>

-   :material-battery-charging-high:{ .lg .middle } **Battery and charging**

    ---

    Battery %, range, charging state, charge limit, time to full and energy added.

-   :material-car-door-lock:{ .lg .middle } **Locks, doors and windows**

    ---

    Locked or not, each door and window, the boot and the bonnet.

-   :material-car-tire-alert:{ .lg .middle } **Health**

    ---

    Tyre pressures and warnings, 12 V battery voltage, washer fluid, distance to the next service.

-   :material-map-marker-path:{ .lg .middle } **Location and trips**

    ---

    Where the car was parked, as a device tracker, and its last trip.

</div>

!!! info "Read-only"
    The Data Hub only shares data. It can't lock the car, start climate or change charging, so neither can this
    integration.

## What you need

- A Jaguar or Land Rover with connected services (InControl / JLR Remote), where you're the primary user.
- Your JLR account, which also signs you in to JLR's data portal, [data.jlr.com](https://data.jlr.com/en_xi/index.html).
  It's free.
- A car first sold in the EU or the UK.
- Home Assistant 2026.2 or newer, ideally with [HACS](https://hacs.xyz).

Tested with a UK 2020 Jaguar I-Pace. Any car the Data Hub lists for you should work.

## Two ways to connect

JLR allows **one Data Hub credential per account**. Almost everyone should let Home Assistant hold it:

| | **Direct** (recommended) | **Through jlr-server** (advanced) |
|---|---|---|
| Who holds the JLR credential | This Home Assistant | A small server you run |
| Good for | One Home Assistant | Several Home Assistants, apps or scripts reading one car |
| Updates | Live stream, plus a check every 10 minutes | Reads the server every 30–300 s |
| Extras | | Battery used per trip, history, alerts |

Not sure? Choose **Direct**. You can move to [jlr-server](advanced/jlr-server.md) later.

!!! warning "Not an official JLR product"
    This is an independent open-source project. It isn't made, endorsed or supported by Jaguar Land Rover.
