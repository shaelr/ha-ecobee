"""Diagnostics support for ecobee."""

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.redact import async_redact_data

from . import EcobeeConfigEntry

TO_REDACT = {"identifier", "location"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: EcobeeConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    Dumps the raw thermostat payload as returned by the ecobee API, minus
    the account's location and thermostat identifier. This exists mainly to
    let a real account's data shape be inspected directly (e.g. the
    notificationSettings.equipment schema most of the guesswork in this
    integration's code comments is about) instead of inferring it
    indirectly through what entities display.
    """
    data = entry.runtime_data
    return {
        "thermostats": [
            async_redact_data(thermostat, TO_REDACT)
            for thermostat in data.ecobee.thermostats
        ]
    }
