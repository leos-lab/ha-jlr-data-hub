"""Base entity: one device per car."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import JLRCoordinator
from .vehicle import VehicleState


class JLREntity(CoordinatorEntity[JLRCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: JLRCoordinator, description: EntityDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.vin}_{description.key}"
        state = coordinator.data.state if coordinator.data else VehicleState()
        brand = state.value("Vehicle.VehicleIdentification.Brand")
        model = state.value("Vehicle.VehicleIdentification.Model")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.vin)},
            manufacturer=str(brand) if brand else "Jaguar Land Rover",
            model=str(model) if model else None,
            name=str(model) if model else "JLR vehicle",
            serial_number=coordinator.vin,
        )

    @property
    def state_data(self) -> VehicleState:
        return self.coordinator.data.state
