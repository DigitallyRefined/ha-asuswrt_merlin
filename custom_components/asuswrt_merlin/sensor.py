"""Sensor platform for AsusWrt-Merlin integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .device_tracker import AsusWrtMerlinDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensor platform for AsusWrt-Merlin component."""
    # Get coordinator from hass data (created in __init__.py)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = [
        AsusWrtMerlinRouterSensor(coordinator, entry),
    ]
    
    async_add_entities(entities, True)


class AsusWrtMerlinSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for AsusWrt-Merlin sensors."""

    def __init__(
        self, coordinator: AsusWrtMerlinDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"AsusWrt-Merlin router {entry.data['host']}",
            "manufacturer": "ASUS",
            "model": "AsusWrt-Merlin router",
        }


class AsusWrtMerlinRouterSensor(AsusWrtMerlinSensorBase):
    """Sensor for AsusWrt-Merlin router information."""

    def __init__(
        self, coordinator: AsusWrtMerlinDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_name = "AsusWrt-Merlin router"
        self._attr_unique_id = f"{entry.entry_id}_router_info"
        self._attr_icon = "mdi:router-wireless"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int:
        """Return the number of connected devices as the main value."""
        if not self.coordinator.data:
            return 0
        
        # Count devices that are currently connected
        connected_count = 0
        for device in self.coordinator.data:
            if device.get("is_connected", False):
                connected_count += 1
            else:
                # Check if device was seen recently
                last_activity = device.get("last_activity")
                if last_activity is not None:
                    if isinstance(last_activity, str):
                        last_activity = datetime.fromisoformat(last_activity)
                    time_diff = datetime.now() - last_activity
                    if time_diff.total_seconds() < self.coordinator.consider_home:
                        connected_count += 1
        
        return connected_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return comprehensive state attributes."""
        attrs = {
            # Router connection info
            "router_status": "Connected" if self.coordinator.last_update_success else "Disconnected",
            "host": self._entry.data["host"],
            "update_interval_seconds": self.coordinator.update_interval.total_seconds(),
        }
        
        # Last update information
        if self.coordinator.last_update_time:
            attrs["last_update"] = self.coordinator.last_update_time.strftime("%Y-%m-%d %H:%M:%S")
        else:
            attrs["last_update"] = None
        
        # Device statistics
        if not self.coordinator.data:
            attrs.update({
                "total_devices": 0,
                "active_devices": 0,
                "recently_seen_devices": 0,
                "offline_devices": 0,
                "devices": [],
            })
            return attrs
        
        # Count devices by status
        active_count = 0  # Currently in ARP table (actively communicating)
        recently_seen_count = 0  # Not in ARP but seen within consider_home time
        offline_count = 0
        devices = []
        
        for device in self.coordinator.data:
            is_connected = device.get("is_connected", False)
            
            if is_connected:
                # Device is actively communicating (in ARP table)
                active_count += 1
                recently_seen_count += 1
            else:
                # Check if device was seen recently but not currently active
                last_activity = device.get("last_activity")
                if last_activity is not None:
                    if isinstance(last_activity, str):
                        last_activity = datetime.fromisoformat(last_activity)
                    time_diff = datetime.now() - last_activity
                    if time_diff.total_seconds() < self.coordinator.consider_home:
                        recently_seen_count += 1
                    else:
                        offline_count += 1
                else:
                    offline_count += 1
        
        attrs.update({
            "total_devices": len(self.coordinator.data),
            "active_devices": active_count,
            "recently_seen_devices": recently_seen_count,
            "offline_devices": offline_count,
        })
        
        return attrs
