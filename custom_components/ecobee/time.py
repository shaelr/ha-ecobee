"""Support for comfort setting daily start times on ecobee thermostats."""

from datetime import time as time_
from typing import override

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EcobeeConfigEntry, EcobeeData
from .entity import EcobeeBaseEntity

SLOT_MINUTES = 30
NUM_SCHEDULE_DAYS = 7

# Comfort settings this "one start time, applied to every day" convenience
# entity supports. Unlike the Schedule calendar (which can represent any
# arrangement), a single daily start time only makes sense for a comfort
# setting that occupies one clean block per day -- that's true for a simple
# Home/Sleep daily cycle, but not guaranteed for other/custom settings, so
# this intentionally isn't generalized to every comfort setting.
DAILY_START_TIME_CLIMATES = ("Home", "Sleep")


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: EcobeeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ecobee comfort setting start time entities."""
    data = config_entry.runtime_data

    entities = []
    for index, thermostat in enumerate(data.ecobee.thermostats):
        climate_refs_by_name = {
            climate["name"]: climate["climateRef"]
            for climate in thermostat["program"]["climates"]
        }
        for name in DAILY_START_TIME_CLIMATES:
            if climate_ref := climate_refs_by_name.get(name):
                entities.append(EcobeeComfortStartTime(data, index, climate_ref, name))

    async_add_entities(entities, True)


def _first_transition_slot(day_slots: list[str], climate_ref: str) -> int | None:
    """Return the earliest slot index where day_slots switches to climate_ref.

    ``day_slots[i - 1]`` wraps to the day's last slot at ``i == 0``, which is
    the right comparison for a block (like an overnight Sleep period) that's
    already active at midnight.
    """
    for i, ref in enumerate(day_slots):
        if ref == climate_ref and day_slots[i - 1] != climate_ref:
            return i
    return None


class EcobeeComfortStartTime(EcobeeBaseEntity, TimeEntity):
    """The clock time a comfort setting's daily block begins, applied to every day.

    Reflects (and edits) the first schedule transition into this comfort
    setting each day. Moving it shifts just that one boundary -- shrinking or
    growing the neighboring block -- the same way dragging a block's edge in
    the Schedule calendar would, just repeated across all 7 days at once.
    """

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        data: EcobeeData,
        thermostat_index: int,
        climate_ref: str,
        climate_name: str,
    ) -> None:
        """Initialize a comfort setting start time."""
        super().__init__(data, thermostat_index)
        self.climate_ref = climate_ref
        self._attr_name = f"{climate_name} Start Time"
        self._attr_unique_id = f"{self.base_unique_id}_comfort_{climate_ref}_start_time"
        self.update_without_throttle = False

    async def async_update(self) -> None:
        """Get the latest state from the thermostat."""
        if self.update_without_throttle:
            await self.data.update(no_throttle=True)
            self.update_without_throttle = False
        else:
            await self.data.update()

        day_slots = self.thermostat["program"]["schedule"][0]
        slot = _first_transition_slot(day_slots, self.climate_ref)
        if slot is None:
            self._attr_native_value = None
            return
        minutes = slot * SLOT_MINUTES
        self._attr_native_value = time_(hour=minutes // 60, minute=minutes % 60)

    @override
    def set_value(self, value: time_) -> None:
        """Move this comfort setting's daily start time, on every day."""
        new_slot = (value.hour * 60 + value.minute) // SLOT_MINUTES
        for day_index in range(NUM_SCHEDULE_DAYS):
            self._move_start(day_index, new_slot)
        self.update_without_throttle = True

    def _move_start(self, day_index: int, new_slot: int) -> None:
        """Move the block boundary for this comfort setting on one day.

        Growing the block (new_slot earlier) just extends it backward.
        Shrinking it (new_slot later) has to hand the freed slots back to
        whatever comfort setting preceded it, or they'd be stuck showing
        this setting despite it "starting later".
        """
        day_slots = self.thermostat["program"]["schedule"][day_index]
        old_slot = _first_transition_slot(day_slots, self.climate_ref)
        if old_slot is None or new_slot == old_slot:
            return
        if new_slot < old_slot:
            self.data.ecobee.set_schedule_slots(
                self.thermostat_index, day_index, new_slot, old_slot - 1, self.climate_ref
            )
        else:
            previous_ref = day_slots[old_slot - 1]
            self.data.ecobee.set_schedule_slots(
                self.thermostat_index, day_index, old_slot, new_slot - 1, previous_ref
            )
