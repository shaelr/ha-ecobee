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
from .util import furnace_filter_equipment


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

    Unverified field name (see pyecobee's set_equipment_reminder) --
    ecobee's notificationSettings.equipment schema hasn't been checked
    against a live payload for this integration; fix the field name there
    if this doesn't match what a real account returns.
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
        if equipment is not None and equipment.get("remindMeDate"):
            self._attr_native_value = date_.fromisoformat(equipment["remindMeDate"])

    @override
    def set_value(self, value: date_) -> None:
        """Set the furnace filter's last service date."""
        self.data.ecobee.set_equipment_reminder(
            self.thermostat_index,
            FURNACE_FILTER_EQUIPMENT_TYPE,
            last_service_date=value.isoformat(),
        )
        self._attr_native_value = value
        self.update_without_throttle = True
        self.schedule_update_ha_state()
