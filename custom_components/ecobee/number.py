"""Support for using number with ecobee thermostats."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
import math
from typing import override

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.unit_conversion import TemperatureConverter

from . import EcobeeConfigEntry, EcobeeData
from .const import FURNACE_FILTER_EQUIPMENT_TYPE
from .entity import EcobeeBaseEntity
from .util import enforce_heat_cool_min_delta, furnace_filter_equipment

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

    entities.extend(
        EcobeeFurnaceFilterReminderInterval(data, index)
        for index, thermostat in enumerate(data.ecobee.thermostats)
        if furnace_filter_equipment(thermostat) is not None
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
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_step = 0.5
    _attr_suggested_display_precision = 1

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
        label = "Heat Temp" if field == "heatTemp" else "Cool Temp"
        self._attr_name = f"{climate_name} {label}"
        self._attr_unique_id = f"{self.base_unique_id}_comfort_{climate_ref}_{field}"
        self.update_without_throttle = False

    @property
    def native_unit_of_measurement(self) -> str:
        """Report values in whatever unit this Home Assistant is configured for.

        ecobee's API is always Fahrenheit. Converting ourselves here, rather
        than declaring FAHRENHEIT as native and letting HA's automatic
        unit conversion handle display, keeps native_step exactly 0.5 in
        whichever unit is actually shown. HA's built-in conversion instead
        multiplies a declared native_step by the F/C ratio, turning a clean
        0.5 into a non-round value (0.5F * 5/9 ~= 0.28C) -- not the clean
        half-degree-in-either-unit stepping ecobee's own app/thermostat use.
        """
        return self.hass.config.units.temperature_unit

    @property
    def native_min_value(self) -> float:
        """Return the minimum value, converted and aligned to the step grid.

        A raw conversion of 7F lands on a non-round value in Celsius
        (-13.8888888888889C). Left as-is, that becomes the baseline
        widgets/browsers step increments from, so every step would land on
        an off-grid decimal instead of a clean multiple of native_step.
        Floor to the step grid so the whole range is step-aligned.
        """
        converted = TemperatureConverter.convert(
            7, UnitOfTemperature.FAHRENHEIT, self.native_unit_of_measurement
        )
        step = self._attr_native_step
        return math.floor(converted / step) * step

    @property
    def native_max_value(self) -> float:
        """Return the maximum value, converted and aligned to the step grid.

        Ceil'd rather than floor'd so the usable range isn't narrowed.
        """
        converted = TemperatureConverter.convert(
            95, UnitOfTemperature.FAHRENHEIT, self.native_unit_of_measurement
        )
        step = self._attr_native_step
        return math.ceil(converted / step) * step

    def _climate(self) -> dict:
        """Return this comfort setting's climate dict."""
        for climate in self.thermostat["program"]["climates"]:
            if climate["climateRef"] == self.climate_ref:
                return climate
        return {}

    def _fahrenheit_to_native(self, fahrenheit: float) -> float:
        """Convert a Fahrenheit value to the active unit, rounded to the step grid.

        ecobee stores in Fahrenheit tenths, so a value that started as a
        clean 0.5-in-some-other-unit setting (e.g. set on the thermostat
        itself while displaying Celsius) doesn't necessarily round-trip back
        to a clean multiple of native_step -- round to the nearest step so
        the box shows 23.5, not 23.5555555555556.
        """
        converted = TemperatureConverter.convert(
            fahrenheit, UnitOfTemperature.FAHRENHEIT, self.native_unit_of_measurement
        )
        step = self._attr_native_step
        return round(converted / step) * step

    async def async_update(self) -> None:
        """Get the latest state from the thermostat."""
        if self.update_without_throttle:
            await self.data.update(no_throttle=True)
            self.update_without_throttle = False
        else:
            await self.data.update()
        climate = self._climate()
        if self.field in climate:
            self._attr_native_value = self._fahrenheit_to_native(climate[self.field] / 10)

    @override
    def set_native_value(self, value: float) -> None:
        """Set new comfort setting temperature."""
        step = self._attr_native_step
        rounded = round(value / step) * step
        requested_fahrenheit = TemperatureConverter.convert(
            rounded, self.native_unit_of_measurement, UnitOfTemperature.FAHRENHEIT
        )

        # Heat Temp and Cool Temp are separate entities/API calls, so
        # enforcing ecobee's minimum heat/cool gap here means looking up
        # the *other* field's current value and sending both together.
        climate = self._climate()
        other_field = "coolTemp" if self.field == "heatTemp" else "heatTemp"
        other_fahrenheit = climate[other_field] / 10

        if self.field == "heatTemp":
            heat_f, cool_f = requested_fahrenheit, other_fahrenheit
        else:
            heat_f, cool_f = other_fahrenheit, requested_fahrenheit
        heat_f, cool_f = enforce_heat_cool_min_delta(
            heat_f, cool_f, self.thermostat["settings"]["heatCoolMinDelta"] / 10.0
        )

        self.data.ecobee.set_climate_temperatures(
            self.thermostat_index, self.climate_ref, heat_temp=heat_f, cool_temp=cool_f
        )
        # Show the rounded value immediately instead of leaving the stale
        # pre-edit reading on screen until the next poll completes. If the
        # delta pushed this field away from what was requested, the sibling
        # Heat/Cool Temp entity picks up its own adjusted value on its next
        # poll -- update_without_throttle makes that happen right away too.
        final_fahrenheit = heat_f if self.field == "heatTemp" else cool_f
        self._attr_native_value = self._fahrenheit_to_native(final_fahrenheit)
        self.update_without_throttle = True
        self.schedule_update_ha_state()


class EcobeeFurnaceFilterReminderInterval(EcobeeBaseEntity, NumberEntity):
    """How many months between furnace filter reminders."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 1
    _attr_native_max_value = 12
    _attr_native_step = 1
    # Not UnitOfTime.MONTHS: that enum's display value is the abbreviation
    # "m", which reads as ambiguous (minutes/months) next to this entity's
    # 1-12 range. No device_class here requires a recognized unit string,
    # so a plain "months" is fine and reads clearly.
    _attr_native_unit_of_measurement = "months"
    _attr_name = "Furnace Filter Reminder Interval"

    def __init__(self, data: EcobeeData, thermostat_index: int) -> None:
        """Initialize the furnace filter reminder interval."""
        super().__init__(data, thermostat_index)
        self._attr_unique_id = f"{self.base_unique_id}_furnace_filter_reminder_interval"
        self.update_without_throttle = False

    async def async_update(self) -> None:
        """Get the latest state from the thermostat."""
        if self.update_without_throttle:
            await self.data.update(no_throttle=True)
            self.update_without_throttle = False
        else:
            await self.data.update()
        equipment = furnace_filter_equipment(self.thermostat)
        if equipment is not None and equipment.get("filterLife") is not None:
            self._attr_native_value = equipment["filterLife"]

    @override
    def set_native_value(self, value: float) -> None:
        """Set the furnace filter reminder interval, in months."""
        months = int(value)
        self.data.ecobee.set_equipment_reminder(
            self.thermostat_index,
            FURNACE_FILTER_EQUIPMENT_TYPE,
            filter_life=months,
            filter_life_units="month",
        )
        self._attr_native_value = months
        self.update_without_throttle = True
        self.schedule_update_ha_state()
