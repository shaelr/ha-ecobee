"""Support for using select with ecobee thermostats."""

from typing import override

from homeassistant.components.climate import FAN_AUTO, FAN_ON
from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EcobeeConfigEntry, EcobeeData
from .entity import EcobeeBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: EcobeeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ecobee comfort setting fan mode select entity."""
    data = config_entry.runtime_data

    entities = [
        EcobeeComfortFanMode(data, index, climate["climateRef"], climate["name"])
        for index, thermostat in enumerate(data.ecobee.thermostats)
        for climate in thermostat["program"]["climates"]
    ]

    async_add_entities(entities, True)


class EcobeeComfortFanMode(EcobeeBaseEntity, SelectEntity):
    """Fan mode (auto/on) for one comfort setting.

    A comfort setting is one of the named profiles in a thermostat's program
    (e.g. Home, Away, Sleep, or a custom one). ecobee's app exposes a single
    Fan control per comfort setting, so this sets both heatFan and coolFan
    together to match.
    """

    _attr_options = [FAN_AUTO, FAN_ON]

    def __init__(
        self,
        data: EcobeeData,
        thermostat_index: int,
        climate_ref: str,
        climate_name: str,
    ) -> None:
        """Initialize a comfort setting fan mode select."""
        super().__init__(data, thermostat_index)
        self.climate_ref = climate_ref
        self._attr_name = f"{climate_name} Fan"
        self._attr_unique_id = f"{self.base_unique_id}_comfort_{climate_ref}_fan_mode"
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
        self._attr_current_option = self._climate().get("heatFan")

    @override
    def select_option(self, option: str) -> None:
        """Set the fan mode for this comfort setting."""
        self.data.ecobee.set_climate_fan_mode(
            self.thermostat_index, self.climate_ref, option
        )
        self.update_without_throttle = True
