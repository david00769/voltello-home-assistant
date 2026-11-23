"""Base entity: one device per service point; unavailable once the last good read is stale."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN
from .coordinator import VexCoordinator


class VexEntity(CoordinatorEntity[VexCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: VexCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.unique_id)},
            name=DEFAULT_NAME,
            manufacturer="Village Energy (unofficial integration)",
            model="Voltello VE-X",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def available(self) -> bool:
        return self.coordinator.fresh and self.coordinator.data is not None
