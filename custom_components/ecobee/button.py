"""Support for an "I changed the filter" button on ecobee thermostats."""

from datetime import date
from typing import override

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EcobeeConfigEntry, EcobeeData
from .const import FURNACE_FILTER_EQUIPMENT_TYPE
from .entity import EcobeeBaseEntity
from .util import furnace_filter_equipment, furnace_filter_last_changed_kwargs


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: EcobeeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ecobee furnace filter changed button."""
    data = config_entry.runtime_data

    entities = [
        EcobeeFurnaceFilterChanged(data, index)
        for index, thermostat in enumerate(data.ecobee.thermostats)
        if furnace_filter_equipment(thermostat) is not None
    ]

    async_add_entities(entities, True)


class EcobeeFurnaceFilterChanged(EcobeeBaseEntity, ButtonEntity):
    """Set the furnace filter's last-service date to today.

    A shortcut for the common case of "I just changed the filter" --
    equivalent to setting date.EcobeeFurnaceFilterLastServiceDate to today
    without having to open the date picker.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:air-filter"
    _attr_name = "Furnace Filter Changed"

    def __init__(self, data: EcobeeData, thermostat_index: int) -> None:
        """Initialize the furnace filter changed button."""
        super().__init__(data, thermostat_index)
        self._attr_unique_id = f"{self.base_unique_id}_furnace_filter_changed"

    @override
    def press(self) -> None:
        """Set the furnace filter's last-service date to today."""
        equipment = furnace_filter_equipment(self.thermostat)
        kwargs = furnace_filter_last_changed_kwargs(equipment, date.today())
        self.data.ecobee.set_equipment_reminder(
            self.thermostat_index, FURNACE_FILTER_EQUIPMENT_TYPE, **kwargs
        )
