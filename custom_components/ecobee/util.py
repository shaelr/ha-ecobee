"""Validation utility functions for ecobee services."""

import calendar
from datetime import date, datetime, timedelta
from typing import Any

import voluptuous as vol

from .const import FURNACE_FILTER_EQUIPMENT_TYPE


def ecobee_date(date_string):
    """Validate a date_string as valid for the ecobee API."""
    try:
        datetime.strptime(date_string, "%Y-%m-%d")
    except ValueError as err:
        raise vol.Invalid("Date does not match ecobee date format YYYY-MM-DD") from err
    return date_string


def ecobee_time(time_string):
    """Validate a time_string as valid for the ecobee API."""
    try:
        datetime.strptime(time_string, "%H:%M:%S")
    except ValueError as err:
        raise vol.Invalid(
            "Time does not match ecobee 24-hour time format HH:MM:SS"
        ) from err
    return time_string


def is_indefinite_hold(start_date_string: str, end_date_string: str) -> bool:
    """Determine if the ecobee API dates represent an indefinite hold.

    This is not documented in the API, so a rough heuristic is
    used where a hold over 1 year is considered indefinite.
    """
    return date.fromisoformat(end_date_string) - date.fromisoformat(
        start_date_string
    ) > timedelta(days=365)


def enforce_heat_cool_min_delta(
    heat_temp: float, cool_temp: float, min_delta: float
) -> tuple[float, float]:
    """Ensure cool_temp is at least min_delta above heat_temp.

    ecobee requires this gap between the heat and cool setpoints whenever
    both are in play -- Heat/Cool (auto) mode holds, and each comfort
    setting's own heat/cool pair. Asking for less gets silently rejected or
    clamped server-side. If the requested pair is too close, spread them
    apart symmetrically around their midpoint rather than favoring whichever
    value happened to be passed first.
    """
    if cool_temp - heat_temp >= min_delta:
        return heat_temp, cool_temp
    midpoint = (heat_temp + cool_temp) / 2
    return midpoint - min_delta / 2, midpoint + min_delta / 2


def furnace_filter_equipment(thermostat: dict[str, Any]) -> dict[str, Any] | None:
    """Return the furnace filter entry from a thermostat's equipment reminders.

    None if the thermostat isn't tracking one (or notificationSettings isn't
    present at all, e.g. include_notifications wasn't enabled).
    """
    equipment_list = thermostat.get("notificationSettings", {}).get("equipment", [])
    for equipment in equipment_list:
        if equipment.get("type") == FURNACE_FILTER_EQUIPMENT_TYPE:
            return equipment
    return None


def add_months(day: date, months: int) -> date:
    """Add (or subtract, for a negative value) whole months to a date.

    Clamps the day-of-month if the target month is shorter (e.g. Jan 31 + 1
    month -> Feb 28/29, not Mar 3).
    """
    total = day.month - 1 + months
    year = day.year + total // 12
    month = total % 12 + 1
    clamped_day = min(day.day, calendar.monthrange(year, month)[1])
    return date(year, month, clamped_day)


def furnace_filter_last_changed_kwargs(
    equipment: dict[str, Any] | None, new_last_changed: date
) -> dict[str, str]:
    """Build set_equipment_reminder kwargs for a new furnace filter last-changed date.

    Also advances remind_me_date by the reminder interval, so the
    countdown actually restarts -- remindMeDate rolls forward on its own
    over time rather than staying anchored to filterLastChanged (confirmed
    against a live account), so leaving it untouched wouldn't reset
    anything. Shared by the last-service-date entity (date.py) and the
    "I changed the filter" button (button.py), which both need exactly
    this same write.
    """
    kwargs: dict[str, str] = {"filter_last_changed": new_last_changed.isoformat()}
    interval_months = equipment.get("filterLife") if equipment else None
    if interval_months is not None:
        kwargs["remind_me_date"] = add_months(
            new_last_changed, interval_months
        ).isoformat()
    return kwargs
