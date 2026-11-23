"""Binary sensors: export control, curtailment, and whether VE-X has gone quiet."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VexConfigEntry
from .const import CONF_CURTAILMENT_CONTRACT
from .control_log import curtailment_active
from .entity import VexEntity


async def async_setup_entry(hass: HomeAssistant, entry: VexConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    add([ExportControlActive(coordinator), CurtailmentActive(coordinator), VexStale(coordinator)])


class ExportControlActive(VexEntity, BinarySensorEntity):
    """Voltello holds export to a limit (enableExportControl and a numeric exportPSetPoint)."""

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "export_control_active")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.export_control_active if self.coordinator.data else None


class CurtailmentActive(VexEntity, BinarySensorEntity):
    """The panels produce less than they could: an export limit set by the solar plan.

    The solar plan's contract is the "curtailment contract" option (chosen from the ones
    seen in the log); without it, any export limit counts.
    """

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "curtailment_active")

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        return curtailment_active(self.coordinator.data, self.coordinator.entry.options.get(CONF_CURTAILMENT_CONTRACT))

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        return {"contract_id": data.inverter_contract_id, "allowed_export_kw": data.allowed_export_kw} if data else {}


class VexStale(VexEntity, BinarySensorEntity):
    """On in daylight when the last good read is over 20 min old; off at night by design."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "vex_stale")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        daylight, _ = self.coordinator.daylight_and_feed_in()
        return daylight and not self.coordinator.fresh
