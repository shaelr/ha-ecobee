"""Support for using number with ecobee thermostats."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
from typing import override

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EcobeeConfigEntry, EcobeeData
from .entity import EcobeeBaseEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class EcobeeNumberEntityDescription(NumberEntityDescription):
    """Class describing Ecobee number entities."""

    ecobee_setting_key: str
    set_fn: Callable[[EcobeeData, int, int], Awaitable]


VENTILATOR_NUMBERS = (
    EcobeeNumberEntityDescription(
        key="home",
        translation_key="ventilator_min_type_home",
        ecobee_setting_key="ventilatorMinOnTimeHome",
        set_fn=lambda data, id, min_time: data.ecobee.set_ventilator_min_on_time_home(
            id, min_time
        ),
    ),
    EcobeeNumberEntityDescription(
        key="away",
        translation_key="ventilator_min_type_away",
        ecobee_setting_key="ventilatorMinOnTimeAway",
        set_fn=lambda data, id, min_time: data.ecobee.set_ventilator_min_on_time_away(
            id, min_time
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: EcobeeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ecobee thermostat number entity."""
    data = config_entry.runtime_data

    assert data is not None

    entities: list[NumberEntity] = [
        EcobeeVentilatorMinTime(data, index, numbers)
        for index, thermostat in enumerate(data.ecobee.thermostats)
        if thermostat["settings"]["ventilatorType"] != "none"
        for numbers in VENTILATOR_NUMBERS
    ]

    _LOGGER.debug("Adding compressor min temp number (if present)")
    entities.extend(
        (
            EcobeeCompressorMinTemp(data, index)
            for index, thermostat in enumerate(data.ecobee.thermostats)
            if thermostat["settings"]["hasHeatPump"]
        )
    )

    entities.extend(
        EcobeeFanMinOnTime(data, index) for index in range(len(data.ecobee.thermostats))
    )

    entities.extend(
        EcobeeComfortTemp(data, index, climate["climateRef"], climate["name"], field)
        for index, thermostat in enumerate(data.ecobee.thermostats)
        for climate in thermostat["program"]["climates"]
        for field in ("heatTemp", "coolTemp")
    )

    async_add_entities(entities, True)


class EcobeeVentilatorMinTime(EcobeeBaseEntity, NumberEntity):
    """Represent min time for an ecobee thermostat with ventilator."""

    entity_description: EcobeeNumberEntityDescription

    _attr_native_min_value = 0
    _attr_native_max_value = 60
    _attr_native_step = 5
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(
        self,
        data: EcobeeData,
        thermostat_index: int,
        description: EcobeeNumberEntityDescription,
    ) -> None:
        """Initialize ecobee ventilator platform."""
        super().__init__(data, thermostat_index)
        self.entity_description = description
        self._attr_unique_id = f"{self.base_unique_id}_ventilator_{description.key}"
        self.update_without_throttle = False

    async def async_update(self) -> None:
        """Get the latest state from the thermostat."""
        if self.update_without_throttle:
            await self.data.update(no_throttle=True)
            self.update_without_throttle = False
        else:
            await self.data.update()
        self._attr_native_value = self.thermostat["settings"][
            self.entity_description.ecobee_setting_key
        ]

    @override
    def set_native_value(self, value: float) -> None:
        """Set new ventilator Min On Time value."""
        self.entity_description.set_fn(self.data, self.thermostat_index, int(value))
        self.update_without_throttle = True


class EcobeeCompressorMinTemp(EcobeeBaseEntity, NumberEntity):
    """Minimum outdoor temperature at which the compressor will operate.

    This applies more to air source heat pumps than geothermal. This serves as a safety
         feature (compressors have a minimum operating temperature) as well as
        providing the ability to choose fuel in a dual-fuel system (i.e. choose between
        electrical heat pump and fossil auxiliary heat depending on Time of Use, Solar,
        etc.).
        Note that python-ecobee-api refers to this as Aux Cutover Threshold, but Ecobee
        uses Compressor Protection Min Temp.
    """

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_icon = "mdi:thermometer-off"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = -25
    _attr_native_max_value = 66
    _attr_native_step = 5
    _attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT
    _attr_translation_key = "compressor_protection_min_temp"

    def __init__(
        self,
        data: EcobeeData,
        thermostat_index: int,
    ) -> None:
        """Initialize ecobee compressor min temperature."""
        super().__init__(data, thermostat_index)
        self._attr_unique_id = f"{self.base_unique_id}_compressor_protection_min_temp"
        self.update_without_throttle = False

    async def async_update(self) -> None:
        """Get the latest state from the thermostat."""
        if self.update_without_throttle:
            await self.data.update(no_throttle=True)
            self.update_without_throttle = False
        else:
            await self.data.update()

        self._attr_native_value = (
            (self.thermostat["settings"]["compressorProtectionMinTemp"]) / 10
        )

    @override
    def set_native_value(self, value: float) -> None:
        """Set new compressor minimum temperature."""
        self.data.ecobee.set_aux_cutover_threshold(self.thermostat_index, value)
        self.update_without_throttle = True


class EcobeeFanMinOnTime(EcobeeBaseEntity, NumberEntity):
    """Minimum minutes per hour that the fan must run on an ecobee thermostat."""

    _attr_native_min_value = 0
    _attr_native_max_value = 60
    _attr_native_step = 5
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_translation_key = "fan_min_on_time"

    def __init__(
        self,
        data: EcobeeData,
        thermostat_index: int,
    ) -> None:
        """Initialize ecobee fan minimum on time."""
        super().__init__(data, thermostat_index)
        self._attr_unique_id = f"{self.base_unique_id}_fan_min_on_time"
        self.update_without_throttle = False

    async def async_update(self) -> None:
        """Get the latest state from the thermostat."""
        if self.update_without_throttle:
            await self.data.update(no_throttle=True)
            self.update_without_throttle = False
        else:
            await self.data.update()
        self._attr_native_value = self.thermostat["settings"]["fanMinOnTime"]

    @override
    def set_native_value(self, value: float) -> None:
        """Set new fan minimum on time value."""
        step = self._attr_native_step
        aligned_value = int(round(value / step) * step)
        self.data.ecobee.set_fan_min_on_time(self.thermostat_index, aligned_value)
        self.update_without_throttle = True


class EcobeeComfortTemp(EcobeeBaseEntity, NumberEntity):
    """Heat or cool target temperature for one comfort setting.

    A comfort setting is one of the named profiles in a thermostat's program
    (e.g. Home, Away, Sleep, or a custom one) -- what ecobee's app calls
    "Comfort Settings". This is distinct from the live hold/target
    temperature exposed by the climate entity.
    """

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 7
    _attr_native_max_value = 95
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT

    def __init__(
        self,
        data: EcobeeData,
        thermostat_index: int,
        climate_ref: str,
        climate_name: str,
        field: str,
    ) -> None:
        """Initialize a comfort setting temperature."""
        super().__init__(data, thermostat_index)
        self.climate_ref = climate_ref
        self.field = field
        self._attr_name = "Heat Temp" if field == "heatTemp" else "Cool Temp"
        self._attr_unique_id = f"{self.base_unique_id}_comfort_{climate_ref}_{field}"
        self._attr_device_info = self._comfort_device_info(climate_ref, climate_name)
        self.update_without_throttle = False

    def _climate(self) -> dict:
        """Return this comfort setting's climate dict."""
        for climate in self.thermostat["program"]["climates"]:
            if climate["climateRef"] == self.climate_ref:
                return climate
        return {}

    async def async_update(self) -> None:
        """Get the latest state from the thermostat."""
        if self.update_without_throttle:
            await self.data.update(no_throttle=True)
            self.update_without_throttle = False
        else:
            await self.data.update()
        climate = self._climate()
        if self.field in climate:
            self._attr_native_value = climate[self.field] / 10

    @override
    def set_native_value(self, value: float) -> None:
        """Set new comfort setting temperature."""
        heat_temp = value if self.field == "heatTemp" else None
        cool_temp = value if self.field == "coolTemp" else None
        self.data.ecobee.set_climate_temperatures(
            self.thermostat_index, self.climate_ref, heat_temp=heat_temp, cool_temp=cool_temp
        )
        self.update_without_throttle = True
