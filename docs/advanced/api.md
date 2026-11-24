# jlr-server API

!!! abstract "Advanced"
    For your own apps and scripts. Home Assistant uses `/api/state`, `/api/journeys` and `/api/status`.

Every endpoint except `/healthz` needs `Authorization: Bearer <API_TOKEN>`. Times are ISO 8601 in UTC.

## Car data

| Method | Path | Returns |
|---|---|---|
| `GET` | `/api/state` | `{"signals": [{"name", "value", "unit", "timestamp"}], "reportedAt", "receivedAt"}`: the latest value of every signal |
| `POST` | `/api/refresh` | asks JLR for the latest now, then answers like `/api/state` |
| `GET` | `/api/journeys?days=30` | `{"items": [...]}`: trips, newest first, with `socStart`, `socEnd`, `socUsed` where the history allows |
| `GET` | `/api/charges?days=30` | `{"items": [{"start", "end", "socStart", "socEnd", "socAdded", "energyKWh"}]}` |
| `GET` | `/api/history?path=<signal>&days=7` | `{"points": [{"t", "v"}]}` for one signal |
| `GET` | `/api/alerts?days=365` | `{"items": [{"title", "body", "severity", "startedAt", "clearedAt", "active"}], "push", "devices"}` |

Signal names are JLR's VSS paths, for example `Vehicle.Powertrain.TractionBattery.StateOfCharge.Displayed`. Values
come as JLR sends them, mostly text (`"90"`, `"LOCKED"`).

## Set-up and status

| Method | Path | Does |
|---|---|---|
| `GET` | `/api/status` | sign-in, stream, polling and last error |
| `GET` | `/api/certificate` | the certificate to upload to the JLR portal (PEM text) |
| `PUT` | `/api/config` | `{"clientId", "vin", "streamUsername", "accountId"}` |
| `POST` | `/api/signin` | starts the JLR sign-in: `{"userCode", "verificationUri", "verificationUriComplete"}` |
| `GET` | `/api/signin` | its progress: `pending`, `done` or `error` |
| `POST` | `/api/signout` | forgets the JLR sign-in |
| `POST` | `/api/push/register` | `{"token", "environment"}`: an iOS device token for alert pushes |
| `POST` | `/api/alerts/test` | sends a test push to every registered device |
| `GET` | `/healthz` | `{"ok": true}`, no token needed |

## Example

```sh
curl -s -H "Authorization: Bearer $T" https://jlr.example.com/api/state \
  | jq -r '.signals[] | select(.name | endswith("StateOfCharge.Displayed")) | .value'
```
