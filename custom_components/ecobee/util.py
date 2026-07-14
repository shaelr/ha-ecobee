"""Validation utility functions for ecobee services."""

from datetime import date, datetime, timedelta

import voluptuous as vol


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
