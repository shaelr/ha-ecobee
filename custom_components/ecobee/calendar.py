"""Support for viewing/editing the ecobee thermostat schedule as a calendar."""

from datetime import date, datetime, time, timedelta, tzinfo
from itertools import groupby
from typing import Any, override

from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEntityFeature,
    CalendarEvent,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import EcobeeConfigEntry, EcobeeData
from .const import DOMAIN, SCHEDULE_WEEKDAY_TO_ECOBEE_DAY_INDEX_OFFSET
from .entity import EcobeeBaseEntity

SLOT_MINUTES = 30
SLOTS_PER_DAY = 24 * 60 // SLOT_MINUTES


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: EcobeeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ecobee schedule calendar entity."""
    data = config_entry.runtime_data

    entities = [
        EcobeeScheduleCalendar(
            data,
            index,
            (await dt_util.async_get_time_zone(thermostat["location"]["timeZone"]))
            or dt_util.get_default_time_zone(),
        )
        for index, thermostat in enumerate(data.ecobee.thermostats)
    ]

    async_add_entities(entities, True)


class EcobeeScheduleCalendar(EcobeeBaseEntity, CalendarEntity):
    """The weekly ecobee program schedule, shown/edited as a calendar.

    Every half-hour slot in the ecobee schedule always belongs to some
    comfort setting (Home/Away/Sleep/custom) -- there's no "empty" state.
    Creating or moving/resizing an event repaints the slots it covers with
    the chosen comfort setting; deleting isn't supported since there's
    nothing meaningful to revert a slot to.
    """

    _attr_name = "Schedule"
    _attr_supported_features = (
        CalendarEntityFeature.CREATE_EVENT | CalendarEntityFeature.UPDATE_EVENT
    )

    def __init__(
        self,
        data: EcobeeData,
        thermostat_index: int,
        operating_timezone: tzinfo,
    ) -> None:
        """Initialize the ecobee schedule calendar."""
        super().__init__(data, thermostat_index)
        self._attr_unique_id = f"{self.base_unique_id}_schedule"
        self._operating_timezone = operating_timezone

    def _climates(self) -> list[dict[str, Any]]:
        """Return the thermostat's comfort setting profiles."""
        return self.thermostat["program"]["climates"]

    def _climate_name(self, climate_ref: str) -> str:
        """Return the display name for a climateRef, falling back to the ref itself."""
        for climate in self._climates():
            if climate["climateRef"] == climate_ref:
                return climate["name"]
        return climate_ref

    def _climate_ref_for_name(self, name: str) -> str:
        """Return the climateRef matching a comfort setting name (case-insensitive)."""
        name_lower = name.strip().lower()
        for climate in self._climates():
            if climate["name"].lower() == name_lower:
                return climate["climateRef"]
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_climate_name",
            translation_placeholders={
                "name": name,
                "options": ", ".join(c["name"] for c in self._climates()),
            },
        )

    def _ecobee_day_index(self, day: date) -> int:
        """Map a Python date to its index into program.schedule."""
        return (day.weekday() + SCHEDULE_WEEKDAY_TO_ECOBEE_DAY_INDEX_OFFSET) % 7

    def _day_start(self, day: date) -> datetime:
        """Return midnight of ``day`` in the thermostat's local timezone."""
        return datetime.combine(day, time.min, tzinfo=self._operating_timezone)

    def _blocks_for_date(self, day: date) -> list[tuple[int, int, str]]:
        """Return (start_slot, end_slot, climate_ref) runs for one date's schedule day."""
        slots = self.thermostat["program"]["schedule"][self._ecobee_day_index(day)]
        blocks = []
        start = 0
        for climate_ref, group in groupby(slots):
            length = len(list(group))
            blocks.append((start, start + length - 1, climate_ref))
            start += length
        return blocks

    def _event_for_block(
        self, day: date, start_slot: int, end_slot: int, climate_ref: str
    ) -> CalendarEvent:
        """Build a CalendarEvent for one schedule block."""
        day_start = self._day_start(day)
        return CalendarEvent(
            start=day_start + timedelta(minutes=start_slot * SLOT_MINUTES),
            end=day_start + timedelta(minutes=(end_slot + 1) * SLOT_MINUTES),
            summary=self._climate_name(climate_ref),
            uid=f"{self.base_unique_id}-{day.isoformat()}-{start_slot}",
        )

    @property
    @override
    def event(self) -> CalendarEvent | None:
        """Return the comfort setting currently scheduled, if any."""
        now = dt_util.now(self._operating_timezone)
        current_slot = (now.hour * 60 + now.minute) // SLOT_MINUTES
        for start_slot, end_slot, climate_ref in self._blocks_for_date(now.date()):
            if start_slot <= current_slot <= end_slot:
                return self._event_for_block(now.date(), start_slot, end_slot, climate_ref)
        return None

    @override
    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return schedule blocks between start_date and end_date."""
        start_local = self._as_local(start_date)
        end_local = self._as_local(end_date)
        events = []
        day = start_local.date()
        while day <= end_local.date():
            for start_slot, end_slot, climate_ref in self._blocks_for_date(day):
                event = self._event_for_block(day, start_slot, end_slot, climate_ref)
                if event.end > start_local and event.start < end_local:
                    events.append(event)
            day += timedelta(days=1)
        return events

    def _iter_day_segments(self, start: datetime, end: datetime):
        """Yield (date, start_slot, end_slot) for each local day [start, end) touches."""
        if end <= start:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_schedule_range"
            )
        current = start
        while current < end:
            day_start = self._day_start(current.date())
            next_day_start = day_start + timedelta(days=1)
            segment_end = min(end, next_day_start)

            start_minute = (current - day_start).seconds // 60
            end_minute = (
                24 * 60 - 1
                if segment_end == next_day_start
                else (segment_end - day_start).seconds // 60 - 1
            )

            start_slot = max(0, min(SLOTS_PER_DAY - 1, start_minute // SLOT_MINUTES))
            end_slot = max(0, min(SLOTS_PER_DAY - 1, end_minute // SLOT_MINUTES))
            yield current.date(), start_slot, end_slot

            current = next_day_start

    def _as_local(self, value: datetime | date) -> datetime:
        """Normalize a create/update-event boundary to a local, tz-aware datetime."""
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=self._operating_timezone)
            return value.astimezone(self._operating_timezone)
        return self._day_start(value)

    async def _async_paint(
        self, dtstart: datetime | date, dtend: datetime | date, summary: str
    ) -> None:
        """Assign a comfort setting to the schedule slots an event covers."""
        climate_ref = self._climate_ref_for_name(summary)
        start = self._as_local(dtstart)
        end = self._as_local(dtend)
        for day, start_slot, end_slot in self._iter_day_segments(start, end):
            await self.hass.async_add_executor_job(
                self.data.ecobee.set_schedule_slots,
                self.thermostat_index,
                self._ecobee_day_index(day),
                start_slot,
                end_slot,
                climate_ref,
            )
        # set_schedule_slots already mutates the local thermostat cache in
        # place before POSTing, so the new schedule is available immediately
        # with no network round trip. Explicitly re-fetching here would risk
        # racing ecobee's own eventual consistency and momentarily showing
        # the stale pre-edit schedule instead.
        self.async_write_ha_state()

    @override
    async def async_create_event(self, **kwargs: Any) -> None:
        """Paint a new schedule block from a created calendar event."""
        await self._async_paint(kwargs["dtstart"], kwargs["dtend"], kwargs["summary"])

    @override
    async def async_update_event(
        self,
        uid: str,
        event: dict[str, Any],
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        """Repaint the schedule to match an edited calendar event.

        No separate "clear the old range" step is needed: the schedule is a
        raw grid of slots, and only the new event's footprint needs to be
        overwritten. Slots left over from the old block simply keep whatever
        was already there, which -- since it was the same comfort setting
        across the whole original block -- correctly reappears as its own
        (now smaller or shifted) block.
        """
        await self._async_paint(event["dtstart"], event["dtend"], event["summary"])
