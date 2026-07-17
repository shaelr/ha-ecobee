"""Support for the furnace filter last-service date on ecobee thermostats."""

from datetime import date as date_
from typing import override

from homeassistant.components.date import DateEntity
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
    """Set up the ecobee furnace filter last-service-date entity."""
    data = config_entry.runtime_data

    entities = [
        EcobeeFurnaceFilterLastServiceDate(data, index)
        for index, thermostat in enumerate(data.ecobee.thermostats)
        if furnace_filter_equipment(thermostat) is not None
    ]

    async_add_entities(entities, True)


class EcobeeFurnaceFilterLastServiceDate(EcobeeBaseEntity, DateEntity):
    """The last-service date for the furnace filter reminder.

    Confirmed against a live account's diagnostics dump:
    notificationSettings.equipment's furnaceFilter entry has a dedicated
    filterLastChanged field -- this reads/writes that directly, no
    derivation needed (an earlier version of this entity assumed
    remindMeDate minus the interval; that was wrong, since remindMeDate
    turned out to roll forward on its own over time rather than staying
    anchored to the last-changed date).
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "Furnace Filter Last Service Date"

    def __init__(self, data: EcobeeData, thermostat_index: int) -> None:
        """Initialize the furnace filter last service date."""
        super().__init__(data, thermostat_index)
        self._attr_unique_id = (
            f"{self.base_unique_id}_furnace_filter_last_service_date"
        )
        self.update_without_throttle = False

    async def async_update(self) -> None:
        """Get the latest state from the thermostat."""
        if self.update_without_throttle:
            await self.data.update(no_throttle=True)
            self.update_without_throttle = False
        else:
            await self.data.update()
        equipment = furnace_filter_equipment(self.thermostat)
        if equipment is not None and equipment.get("filterLastChanged"):
            self._attr_native_value = date_.fromisoformat(
                equipment["filterLastChanged"]
            )

    @override
    def set_value(self, value: date_) -> None:
        """Set the furnace filter's last service date."""
        equipment = furnace_filter_equipment(self.thermostat)
        kwargs = furnace_filter_last_changed_kwargs(equipment, value)
        self.data.ecobee.set_equipment_reminder(
            self.thermostat_index, FURNACE_FILTER_EQUIPMENT_TYPE, **kwargs
        )
        self._attr_native_value = value
        self.update_without_throttle = True
        self.schedule_update_ha_state()
