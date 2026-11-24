"""Where the car is (its last reported position: the car reports when it's switched off)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import JLRConfigEntry
from .entity import JLREntity

LOCATION = EntityDescription(key="location", translation_key="location")


async def async_setup_entry(hass: HomeAssistant, entry: JLRConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([JLRTracker(entry.runtime_data, LOCATION)])


class JLRTracker(JLREntity, TrackerEntity):
    _attr_source_type = SourceType.GPS

    @property
    def latitude(self) -> float | None:
        loc = self.state_data.location
        return loc[0] if loc else None

    @property
    def longitude(self) -> float | None:
        loc = self.state_data.location
        return loc[1] if loc else None

    @property
    def location_accuracy(self) -> float:
        return 0

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        loc = self.state_data.location
        return {"reported_at": loc[2].isoformat()} if loc and loc[2] else None
