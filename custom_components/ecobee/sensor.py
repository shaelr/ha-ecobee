"""Support for Ecobee sensors."""

from dataclasses import dataclass
from typing import override

from pyecobee.const import ECOBEE_STATE_CALIBRATING, ECOBEE_STATE_UNKNOWN

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfDensity, UnitOfRatio, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EcobeeConfigEntry, EcobeeData
from .const import DOMAIN, ECOBEE_MODEL_TO_NAME, MANUFACTURER
from .entity import EcobeeBaseEntity


@dataclass(frozen=True, kw_only=True)
class EcobeeSensorEntityDescription(SensorEntityDescription):
    """Represent the ecobee sensor entity description."""

    runtime_key: str | None


SENSOR_TYPES: tuple[EcobeeSensorEntityDescription, ...] = (
    EcobeeSensorEntityDescription(
        key="temperature",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        runtime_key=None,
    ),
    EcobeeSensorEntityDescription(
        key="humidity",
        native_unit_of_measurement=UnitOfRatio.PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        runtime_key=None,
    ),
    EcobeeSensorEntityDescription(
        key="co2PPM",
        native_unit_of_measurement=UnitOfRatio.PARTS_PER_MILLION,
        device_class=SensorDeviceClass.CO2,
        state_class=SensorStateClass.MEASUREMENT,
        runtime_key="actualCO2",
    ),
    EcobeeSensorEntityDescription(
        key="vocPPM",
        device_class=SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS,
        native_unit_of_measurement=UnitOfDensity.MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        runtime_key="actualVOC",
    ),
    EcobeeSensorEntityDescription(
        key="airQuality",
        device_class=SensorDeviceClass.AQI,
        state_class=SensorStateClass.MEASUREMENT,
        runtime_key="actualAQScore",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: EcobeeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up ecobee sensors."""
    data = config_entry.runtime_data
    entities: list[SensorEntity] = [
        EcobeeSensor(data, sensor["name"], index, description)
        for index in range(len(data.ecobee.thermostats))
        for sensor in data.ecobee.get_remote_sensors(index)
        for item in sensor["capability"]
        for description in SENSOR_TYPES
        if description.key == item["type"]
    ]

    entities.extend(
        EcobeeHeatCoolMinDelta(data, index)
        for index in range(len(data.ecobee.thermostats))
    )

    entities.extend(
        EcobeeActiveAlerts(data, index)
        for index in range(len(data.ecobee.thermostats))
    )

    async_add_entities(entities, True)


class EcobeeSensor(SensorEntity):
    """Representation of an Ecobee sensor."""

    _attr_has_entity_name = True

    entity_description: EcobeeSensorEntityDescription

    def __init__(
        self,
        data,
        sensor_name,
        sensor_index,
        description: EcobeeSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        self.entity_description = description
        self.data = data
        self.sensor_name = sensor_name
        self.index = sensor_index
        self._state = None

    @property
    @override
    def unique_id(self) -> str | None:
        """Return a unique identifier for this sensor."""
        for sensor in self.data.ecobee.get_remote_sensors(self.index):
            if sensor["name"] == self.sensor_name:
                if "code" in sensor:
                    return f"{sensor['code']}-{self.device_class}"
                thermostat = self.data.ecobee.get_thermostat(self.index)
                return f"{thermostat['identifier']}-{sensor['id']}-{self.device_class}"
        return None

    @property
    @override
    def device_info(self) -> DeviceInfo | None:
        """Return device information for this sensor."""
        identifier = None
        model = None
        for sensor in self.data.ecobee.get_remote_sensors(self.index):
            if sensor["name"] != self.sensor_name:
                continue
            if "code" in sensor:
                identifier = sensor["code"]
                model = "ecobee Room Sensor"
            else:
                thermostat = self.data.ecobee.get_thermostat(self.index)
                identifier = thermostat["identifier"]
                try:
                    model = (
                        f"{ECOBEE_MODEL_TO_NAME[thermostat['modelNumber']]} Thermostat"
                    )
                except KeyError:
                    # Ecobee model is not in our list
                    model = None
            break

        if identifier is not None and model is not None:
            return DeviceInfo(
                identifiers={(DOMAIN, identifier)},
                manufacturer=MANUFACTURER,
                model=model,
                name=self.sensor_name,
            )
        return None

    @property
    @override
    def available(self) -> bool:
        """Return true if device is available."""
        thermostat = self.data.ecobee.get_thermostat(self.index)
        return thermostat["runtime"]["connected"]

    @property
    @override
    def native_value(self):
        """Return the state of the sensor."""
        if self._state in (
            ECOBEE_STATE_CALIBRATING,
            ECOBEE_STATE_UNKNOWN,
            "unknown",
        ):
            return None

        if self.entity_description.key == "temperature":
            return float(self._state) / 10

        return self._state

    async def async_update(self) -> None:
        """Get the latest state of the sensor."""
        await self.data.update()
        for sensor in self.data.ecobee.get_remote_sensors(self.index):
            if sensor["name"] != self.sensor_name:
                continue
            for item in sensor["capability"]:
                if item["type"] != self.entity_description.key:
                    continue
                if self.entity_description.runtime_key is None:
                    self._state = item["value"]
                else:
                    thermostat = self.data.ecobee.get_thermostat(self.index)
                    self._state = thermostat["runtime"][
                        self.entity_description.runtime_key
                    ]
                break


class EcobeeHeatCoolMinDelta(EcobeeBaseEntity, SensorEntity):
    """Minimum required gap between the heat and cool setpoints in Heat/Cool mode.

    Read-only: this is ecobee's settings.heatCoolMinDelta, thermostat-wide
    (not per comfort setting). Already enforced when writing hold/comfort
    temperatures (see util.enforce_heat_cool_min_delta) -- this just makes
    the value itself visible.
    """

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Heat/Cool Min Delta"
    _attr_suggested_display_precision = 1

    def __init__(self, data, thermostat_index: int) -> None:
        """Initialize the heat/cool minimum delta sensor."""
        super().__init__(data, thermostat_index)
        self._attr_unique_id = f"{self.base_unique_id}_heat_cool_min_delta"

    @property
    def native_unit_of_measurement(self) -> str:
        """Report in whatever unit this Home Assistant is configured for.

        This value is a temperature *delta* (an interval), not an absolute
        reading. Declaring FAHRENHEIT as native and letting HA's automatic
        device_class=TEMPERATURE conversion handle display would be wrong:
        that conversion applies the full (F-32)*5/9 absolute-temperature
        formula, which corrupts a delta -- e.g. a 2F gap would render as
        -16.7C instead of the correct ~1.1C gap. Convert ourselves using a
        pure ratio, no offset.
        """
        return self.hass.config.units.temperature_unit

    async def async_update(self) -> None:
        """Get the latest state from the thermostat."""
        await self.data.update()
        delta_fahrenheit = self.thermostat["settings"]["heatCoolMinDelta"] / 10
        if self.native_unit_of_measurement == UnitOfTemperature.CELSIUS:
            self._attr_native_value = delta_fahrenheit * 5 / 9
        else:
            self._attr_native_value = delta_fahrenheit


class EcobeeActiveAlerts(EcobeeBaseEntity, SensorEntity):
    """Count of ecobee's actual fired alerts/notifications, with details as attributes.

    Distinct from notificationSettings.equipment (the reminder
    *configuration* -- interval, enabled, last-changed): this is what
    actually shows up once a reminder (or any other alert ecobee sends,
    e.g. temperature/humidity limits) fires, via thermostat["alerts"].

    Field names for each alert entry are this integration's best
    understanding, not confirmed against a live alert -- verify via
    Download Diagnostics once a real alert is active, and correct here if
    any of them don't stick.
    """

    _attr_icon = "mdi:bell-alert"
    _attr_name = "Active Alerts"

    def __init__(self, data: EcobeeData, thermostat_index: int) -> None:
        """Initialize the active alerts sensor."""
        super().__init__(data, thermostat_index)
        self._attr_unique_id = f"{self.base_unique_id}_active_alerts"

    async def async_update(self) -> None:
        """Get the latest state from the thermostat."""
        await self.data.update()
        alerts = self.thermostat.get("alerts", [])
        self._attr_native_value = len(alerts)
        self._attr_extra_state_attributes = {
            "alerts": [
                {
                    "text": alert.get("text"),
                    "date": alert.get("date"),
                    "time": alert.get("time"),
                    "severity": alert.get("severity"),
                    "type": alert.get("alertType"),
                }
                for alert in alerts
            ]
        }
