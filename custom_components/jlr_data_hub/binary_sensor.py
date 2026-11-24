"""Binary sensors: plugged in, charging, locks, doors, windows, bonnet, boot, warnings, and the JLR sign-in."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import JLRConfigEntry
from .coordinator import JLRData
from .entity import JLREntity
from .vehicle import SIDES


@dataclass(frozen=True, kw_only=True)
class JLRBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[JLRData], bool | None]


def _not(v: bool | None) -> bool | None:
    return None if v is None else not v


BINARY_SENSORS: list[JLRBinarySensorDescription] = [
    JLRBinarySensorDescription(
        key="plugged_in", translation_key="plugged_in", device_class=BinarySensorDeviceClass.PLUG,
        value_fn=lambda d: d.state.plugged_in),
    JLRBinarySensorDescription(
        key="charging", translation_key="charging", device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda d: d.state.is_charging),
    # Home Assistant's lock class is "on" when unlocked.
    JLRBinarySensorDescription(
        key="lock", translation_key="lock", device_class=BinarySensorDeviceClass.LOCK,
        value_fn=lambda d: _not(d.state.locked)),
    *[
        JLRBinarySensorDescription(
            key=f"door_{side}", translation_key=f"door_{side}", device_class=BinarySensorDeviceClass.DOOR,
            value_fn=lambda d, side=side: d.state.door_open(side))
        for side in SIDES
    ],
    *[
        JLRBinarySensorDescription(
            key=f"window_{side}", translation_key=f"window_{side}", device_class=BinarySensorDeviceClass.WINDOW,
            value_fn=lambda d, side=side: d.state.window_open(side))
        for side in SIDES
    ],
    JLRBinarySensorDescription(
        key="boot", translation_key="boot", device_class=BinarySensorDeviceClass.OPENING,
        value_fn=lambda d: d.state.boot_open),
    JLRBinarySensorDescription(
        key="bonnet", translation_key="bonnet", device_class=BinarySensorDeviceClass.OPENING,
        value_fn=lambda d: d.state.bonnet_open),
    JLRBinarySensorDescription(
        key="tyre_warning", translation_key="tyre_warning", device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: d.state.tyre_problem),
    JLRBinarySensorDescription(
        key="washer_fluid_low", translation_key="washer_fluid_low", device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC, value_fn=lambda d: d.state.washer_fluid_low),
    JLRBinarySensorDescription(
        key="signed_in", translation_key="signed_in", entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.signed_in),
]


async def async_setup_entry(hass: HomeAssistant, entry: JLRConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities(JLRBinarySensor(coordinator, d) for d in BINARY_SENSORS)


class JLRBinarySensor(JLREntity, BinarySensorEntity):
    entity_description: JLRBinarySensorDescription

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)
