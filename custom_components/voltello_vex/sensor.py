"""Sensors: the inverter and battery commands Voltello has in force."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VexConfigEntry
from .control_log import ControlState
from .entity import VexEntity


@dataclass(frozen=True, kw_only=True)
class VexSensorDescription(SensorEntityDescription):
    value: Callable[[ControlState], object]


POWER = {"native_unit_of_measurement": UnitOfPower.KILO_WATT, "device_class": SensorDeviceClass.POWER,
         "state_class": SensorStateClass.MEASUREMENT}

SENSORS = [
    VexSensorDescription(key="allowed_export", value=lambda s: s.allowed_export_kw, **POWER),
    # VE-X sign: negative is generation. The output when the command in force was issued.
    VexSensorDescription(key="inverter_current_power", value=lambda s: s.inverter_current_power_kw, **POWER),
    VexSensorDescription(key="inverter_power_setpoint", value=lambda s: s.inverter_power_setpoint_kw, **POWER),
    VexSensorDescription(key="battery_mode", value=lambda s: s.battery_mode),
    VexSensorDescription(key="battery_power_setpoint", value=lambda s: s.battery_power_setpoint_kw, **POWER),
    VexSensorDescription(key="battery_soc_discharge_threshold", value=lambda s: s.battery_soc_discharge_threshold,
                         native_unit_of_measurement=PERCENTAGE),
]


async def async_setup_entry(hass: HomeAssistant, entry: VexConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    add([VexSensor(coordinator, d) for d in SENSORS] + [VexDetail(coordinator), VexFailures(coordinator)])


class VexSensor(VexEntity, SensorEntity):
    entity_description: VexSensorDescription

    def __init__(self, coordinator, description: VexSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        return self.entity_description.value(self.coordinator.data) if self.coordinator.data else None


class VexDetail(VexEntity, SensorEntity):
    """The raw control log: state = when the inverter command in force was issued; the
    `endPoints` attribute is exactly what VE-X sent (the archive keeps this shape)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "vex_detail")

    @property
    def native_value(self):
        data = self.coordinator.data
        return (data.inverter_command_start or "no_inverter_command") if data else None

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        return {"endPoints": data.end_points} if data else {}


class VexFailures(VexEntity, SensorEntity):
    """Consecutive failed VE-X calls (3 or more: one call an hour until one succeeds)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "vex_failures")

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> int:
        return self.coordinator.poll.failures
