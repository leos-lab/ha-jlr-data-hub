# Privacy and security

## Where your data goes

**Only between JLR and your own Home Assistant** (or your own jlr-server). There's no third-party service, no
analytics and no telemetry.

## What's stored where

| What | Where |
|---|---|
| Private key | Home Assistant, `config/.storage/jlr_data_hub/`. Never uploaded: JLR only gets the certificate |
| JLR tokens | the same folder. Renewed automatically |
| Car data | Home Assistant's own database, like any other integration |

Removing the integration deletes the key and tokens. Delete the credential in JLR's data portal too
(**Data Access Credentials** on [My data](https://data.jlr.com/en_xi/my-data.html)), so it can't be used again.

## Keep in mind

- The car's **location** is in Home Assistant's history. Exclude the device tracker from the recorder if you'd rather
  not keep it.
- **Home Assistant backups** include the private key. Treat them as private.
- With [jlr-server](../advanced/jlr-server.md), anyone with its `API_TOKEN` can read everything it holds. Keep it
  secret, and use HTTPS outside your home.

## Reporting a security problem

Please don't open a public issue. Use GitHub's
[private vulnerability reporting](https://github.com/leos-lab/ha-jlr-data-hub/security/advisories/new).
