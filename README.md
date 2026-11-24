# JLR Data Hub for Home Assistant

[![Validate](https://github.com/leos-lab/ha-jlr-data-hub/actions/workflows/validate.yml/badge.svg)](https://github.com/leos-lab/ha-jlr-data-hub/actions/workflows/validate.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![Docs](https://img.shields.io/badge/docs-leos--lab.github.io-009688.svg)](https://leos-lab.github.io/ha-jlr-data-hub/)

Your Jaguar or Land Rover in Home Assistant: battery, range, charging, locks, doors and windows, tyres, 12 V battery,
mileage, where it's parked and its last trip. It uses the **JLR Data Hub**, JLR's official owner data service for the
EU Data Act. It's read-only: the Data Hub has no remote commands.

## 📖 [Read the guide](https://leos-lab.github.io/ha-jlr-data-hub/)

- [Getting started](https://leos-lab.github.io/ha-jlr-data-hub/getting-started/): install, create your JLR
  credential, connect
- [Entities](https://leos-lab.github.io/ha-jlr-data-hub/using/entities/) and
  [how fresh the data is](https://leos-lab.github.io/ha-jlr-data-hub/using/freshness/)
- [How it works](https://leos-lab.github.io/ha-jlr-data-hub/how-it-works/)
- [Troubleshooting](https://leos-lab.github.io/ha-jlr-data-hub/help/troubleshooting/)

## Quick install

HACS → ⋮ → **Custom repositories** → add `https://github.com/leos-lab/ha-jlr-data-hub` as an **Integration** →
download **JLR Data Hub** → restart Home Assistant → Settings → Devices & services → **Add integration** →
**JLR Data Hub** → **Connect directly to JLR (recommended)**.

## One credential per account

JLR allows **one Data Hub credential per account**, so normally Home Assistant holds it. To read one car from several
places (two Home Assistants, or Home Assistant plus your own app), run the optional
[**jlr-server**](https://leos-lab.github.io/ha-jlr-data-hub/advanced/jlr-server/) (`server/` here) as a proxy. It also
adds battery used per trip, history and alerts.

## Development

```sh
python3.13 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest                       # the integration
.venv/bin/pip install -r requirements_docs.txt && .venv/bin/mkdocs serve   # the docs
```

`custom_components/jlr_data_hub/jlr_datahub/` is the JLR client (keys, sign-in, DPoP, REST, MQTT), shared with
`server/`. `tests/fixtures/` hold a real jlr-server response with identifying values replaced.

Not affiliated with or endorsed by Jaguar Land Rover. MIT licence.
