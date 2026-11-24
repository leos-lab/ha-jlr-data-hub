# Entities

One device per car. It's named after the model when JLR reports one, otherwise **JLR vehicle**, so entity IDs look
like `sensor.jlr_vehicle_battery`. Rename the device to change them.

## Sensors

| Entity | Unit | Notes |
|---|---|---|
| Battery | % | As shown in the car |
| Range | km | Change to miles in the entity's settings |
| Charging state | | `charging`, `complete`, `plugged_in`, `unplugged` or `fault`. JLR's raw status is an attribute |
| Charge limit | % | Unavailable when no limit is set |
| Time to full | min | 0 once complete, unavailable when not plugged in |
| Charge session energy | kWh | Added in the current or last session |
| Tyre pressure (×4) | kPa | Change to bar or psi in the entity's settings. The car's tyre warning is an attribute |
| 12 V battery | V | The 12 V battery level % is disabled by default |
| Odometer | km | |
| Distance to service | km | |
| Last trip | km | Attributes: start and end time and place, duration, average speed. With [jlr-server](../advanced/jlr-server.md) also `soc_start`, `soc_end` and `soc_used` |

## Binary sensors

| Entity | On means |
|---|---|
| Plugged in | cable connected |
| Charging | charging now |
| Lock | **unlocked** (Home Assistant's lock convention) |
| Door (×4), Window (×4), Boot, Bonnet | open |
| Tyre pressure warning | the car reports a tyre problem |
| Washer fluid low | top up the washer fluid |

## Device tracker

**Location**: where the car last reported from. Cars report when they're switched off, so this is where it was
parked, not live tracking while driving.

## Diagnostics

**Stream** (live, connecting or dropped), **JLR sign-in** and **Last reported** (when the car last sent anything).
Useful when the data looks stale: see [How fresh is the data?](freshness.md)

!!! note "Unavailable doesn't mean broken"
    Cars send `-1` for values they haven't set (a charge limit you never chose, say). Those show as unavailable
    rather than −1.
