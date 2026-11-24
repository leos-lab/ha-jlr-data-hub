# jlr-server (optional, advanced)

Most people don't need this: the Home Assistant integration can hold the JLR credential itself.

JLR allows **one Data Hub credential per account**. jlr-server holds it and acts as a proxy, so several clients (more
than one Home Assistant, an app, scripts) can read the same car. It also stays on the live stream and keeps history,
so trips get the battery % they used, and it raises alerts (12 V battery, charging faults, fault codes).

```sh
cp server/.env.example server/.env        # fill in API_TOKEN and POSTGRES_PASSWORD
docker compose -f server/compose.yml up -d --build
```

Full guide: **https://leos-lab.github.io/ha-jlr-data-hub/advanced/jlr-server/**

The image is built from the same JLR client the integration uses (`custom_components/jlr_data_hub/jlr_datahub`).
Tests: `TEST_DATABASE_URL=postgresql://… python -m pytest server/tests` (the database tests need a throwaway Postgres).
