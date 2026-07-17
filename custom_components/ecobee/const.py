"""Constants for the ecobee integration."""

import logging

from homeassistant.components.weather import (
    ATTR_CONDITION_CLOUDY,
    ATTR_CONDITION_FOG,
    ATTR_CONDITION_HAIL,
    ATTR_CONDITION_LIGHTNING_RAINY,
    ATTR_CONDITION_PARTLYCLOUDY,
    ATTR_CONDITION_POURING,
    ATTR_CONDITION_RAINY,
    ATTR_CONDITION_SNOWY,
    ATTR_CONDITION_SNOWY_RAINY,
    ATTR_CONDITION_SUNNY,
    ATTR_CONDITION_WINDY,
)
from homeassistant.const import Platform

_LOGGER = logging.getLogger(__package__)

DOMAIN = "ecobee"
ATTR_AVAILABLE_SENSORS = "available_sensors"
ATTR_ACTIVE_SENSORS = "active_sensors"

CONF_REFRESH_TOKEN = "refresh_token"

ECOBEE_MODEL_TO_NAME = {
    "idtSmart": "ecobee Smart",
    "idtEms": "ecobee Smart EMS",
    "siSmart": "ecobee Si Smart",
    "siEms": "ecobee Si EMS",
    "athenaSmart": "ecobee3 Smart",
    "athenaEms": "ecobee3 EMS",
    "corSmart": "Carrier/Bryant Cor",
    "nikeSmart": "ecobee3 lite Smart",
    "nikeEms": "ecobee3 lite EMS",
    "apolloSmart": "ecobee4 Smart",
    "vulcanSmart": "ecobee4 Smart",
    "aresSmart": "ecobee Smart Premium",
    "artemisSmart": "ecobee Smart Enhanced",
    "attisRetail": "ecobee Smart Thermostat with Voice Control",
}

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.CALENDAR,
    Platform.CLIMATE,
    Platform.DATE,
    Platform.HUMIDIFIER,
    Platform.NOTIFY,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
    Platform.WEATHER,
]

MANUFACTURER = "ecobee"

ECOBEE_AUX_HEAT_ONLY = "auxHeatOnly"

# thermostat["notificationSettings"]["equipment"][n]["type"] for the furnace
# filter reminder. Unverified against a live payload -- if furnace filter
# entities never show up for a system that has this reminder configured in
# the ecobee app, this is the first thing to check.
FURNACE_FILTER_EQUIPMENT_TYPE = "furnaceFilter"

# thermostat["program"]["schedule"] is 7 lists of 48 half-hour climateRefs.
# schedule[0] is actually Monday (not Sunday, as ecobee's API docs were
# read to say when this was first written) -- confirmed against a live
# account: editing a Thursday block with offset=1 applied the change to
# Friday instead. schedule[0]=Monday means the index already matches
# Python's own date.weekday() numbering (Monday=0) directly, so no offset
# is needed.
SCHEDULE_WEEKDAY_TO_ECOBEE_DAY_INDEX_OFFSET = 0

# Translates ecobee API weatherSymbol to Home Assistant usable names
# https://www.ecobee.com/home/developer/api/documentation/v1/objects/WeatherForecast.shtml
ECOBEE_WEATHER_SYMBOL_TO_HASS = {
    0: ATTR_CONDITION_SUNNY,
    1: ATTR_CONDITION_PARTLYCLOUDY,
    2: ATTR_CONDITION_PARTLYCLOUDY,
    3: ATTR_CONDITION_CLOUDY,
    4: ATTR_CONDITION_CLOUDY,
    5: ATTR_CONDITION_CLOUDY,
    6: ATTR_CONDITION_RAINY,
    7: ATTR_CONDITION_SNOWY_RAINY,
    8: ATTR_CONDITION_POURING,
    9: ATTR_CONDITION_HAIL,
    10: ATTR_CONDITION_SNOWY,
    11: ATTR_CONDITION_SNOWY,
    12: ATTR_CONDITION_SNOWY_RAINY,
    13: "snowy-heavy",
    14: ATTR_CONDITION_HAIL,
    15: ATTR_CONDITION_LIGHTNING_RAINY,
    16: ATTR_CONDITION_WINDY,
    17: "tornado",
    18: ATTR_CONDITION_FOG,
    19: "hazy",
    20: "hazy",
    21: "hazy",
    -2: None,
}
