"""Base classes shared among Ecobee entities."""

import logging
from typing import Any, override

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from . import EcobeeData
from .const import DOMAIN, ECOBEE_MODEL_TO_NAME, MANUFACTURER

_LOGGER = logging.getLogger(__name__)


class EcobeeBaseEntity(Entity):
    """Base methods for Ecobee entities."""

    _attr_has_entity_name = True

    def __init__(self, data: EcobeeData, thermostat_index: int) -> None:
        """Initiate base methods for Ecobee entities."""
        self.data = data
        self.thermostat_index = thermostat_index
        thermostat = self.thermostat
        self.base_unique_id = thermostat["identifier"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, thermostat["identifier"])},
            manufacturer=MANUFACTURER,
            model=ECOBEE_MODEL_TO_NAME.get(thermostat["modelNumber"]),
            name=thermostat["name"],
        )

    @property
    def thermostat(self) -> dict[str, Any]:
        """Return the thermostat data for the entity."""
        return self.data.ecobee.get_thermostat(self.thermostat_index)

    def _comfort_device_info(self, climate_ref: str, climate_name: str) -> DeviceInfo:
        """Return device info for a comfort setting's sub-device.

        Groups all entities for one comfort setting (Home/Away/Sleep/custom)
        under their own device, nested under the thermostat via
        ``via_device``, so dashboards render each comfort setting as its own
        clearly separated card instead of one flat list mixing every comfort
        setting's temps and fan mode together.
        """
        thermostat = self.thermostat
        return DeviceInfo(
            identifiers={(DOMAIN, f"{thermostat['identifier']}_comfort_{climate_ref}")},
            manufacturer=MANUFACTURER,
            name=f"{thermostat['name']} {climate_name}",
            via_device=(DOMAIN, thermostat["identifier"]),
        )

    @property
    @override
    def available(self) -> bool:
        """Return if device is available."""
        return self.thermostat["runtime"]["connected"]
