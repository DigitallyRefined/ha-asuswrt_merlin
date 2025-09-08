"""Device tracker platform for AsusWrt-Merlin integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.device_tracker import ScannerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ATTR_HOSTNAME,
    ATTR_IP,
    ATTR_LAST_ACTIVITY,
    ATTR_MAC,
    CONF_CONSIDER_HOME,
    DOMAIN,
)
from .ssh_client import AsusWrtSSHClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up device tracker for AsusWrt-Merlin component."""
    # Get coordinator from hass data (created in __init__.py)
    coordinator = hass.data[DOMAIN][entry.entry_id]

    # Initialize known devices with current data
    if coordinator.data:
        coordinator.known_devices = {device[ATTR_MAC] for device in coordinator.data}

        # Create initial entities
        entities = []
        for device in coordinator.data:
            entities.append(AsusWrtMerlinDeviceTracker(coordinator, device))
    else:
        # No data available yet, create empty entities list
        entities = []

    async_add_entities(entities, True)

    # Set up callback for new devices
    async def handle_new_devices(new_devices: list[dict[str, Any]]) -> None:
        """Handle new devices that appear on the router."""
        new_entities = []
        for device in new_devices:
            new_entities.append(AsusWrtMerlinDeviceTracker(coordinator, device))
        
        if new_entities:
            _LOGGER.info("Adding %d new device entities", len(new_entities))
            async_add_entities(new_entities, True)

    coordinator.set_new_devices_callback(handle_new_devices)


class AsusWrtMerlinDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching devices from the AsusWrt-Merlin router."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.hass = hass
        self.ssh_client = AsusWrtSSHClient(
            host=entry.data["host"],
            port=entry.data.get("port", 22),
            username=entry.data["username"],
            password=entry.data.get("password"),
            ssh_key=entry.data.get("ssh_key"),
        )
        self.consider_home = entry.data.get(CONF_CONSIDER_HOME, 180)
        self.last_update_time = None
        self.known_devices: set[str] = set()  # Track known device MAC addresses
        self.new_devices_callback = None  # Callback for new device notifications
        # No need for device registry operations - entities link to main router device

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
        )

    async def _async_update_data(self) -> list[dict[str, Any]]:
        """Update data via SSH."""
        try:
            _LOGGER.debug("Starting data update")
            devices = await self.hass.async_add_executor_job(
                self._get_connected_devices
            )
            self.last_update_time = datetime.now()
            _LOGGER.debug("Retrieved %d devices from router", len(devices) if devices else 0)
            
            # Ensure devices is a list
            if not isinstance(devices, list):
                _LOGGER.warning("Expected list of devices, got %s", type(devices))
                devices = []
            
            # No need to create individual devices - entities will be linked to main router device
            
            # Check for new devices
            if devices:
                _LOGGER.debug("Checking for new devices")
                current_device_macs = {device[ATTR_MAC] for device in devices if isinstance(device, dict) and ATTR_MAC in device}
                new_devices = current_device_macs - self.known_devices
                
                if new_devices:
                    _LOGGER.info("Found %d new devices: %s", len(new_devices), new_devices)
                    self.known_devices.update(new_devices)
                    
                    # Notify about new devices if callback is set
                    if self.new_devices_callback:
                        new_device_data = [device for device in devices if isinstance(device, dict) and device.get(ATTR_MAC) in new_devices]
                        await self.new_devices_callback(new_device_data)
            
            _LOGGER.debug("Data update completed successfully")
            return devices
        except Exception as ex:
            _LOGGER.error("Error in _async_update_data: %s", ex, exc_info=True)
            raise UpdateFailed(f"Error communicating with router: {ex}") from ex

    def _get_connected_devices(self) -> list[dict[str, Any]]:
        """Get connected devices from the router."""
        try:
            _LOGGER.debug("Connecting to SSH client")
            self.ssh_client.connect()
            _LOGGER.debug("Getting connected devices from router")
            devices = self.ssh_client.get_connected_devices()
            _LOGGER.debug("SSH client returned %d devices", len(devices) if devices else 0)
            if devices:
                _LOGGER.debug("First device sample: %s", devices[0] if len(devices) > 0 else "None")
            return devices
        except Exception as ex:
            _LOGGER.error("Failed to get connected devices: %s", ex, exc_info=True)
            return []
        finally:
            self.ssh_client.disconnect()

    def set_new_devices_callback(self, callback) -> None:
        """Set callback for new device notifications."""
        self.new_devices_callback = callback



class AsusWrtMerlinDeviceTracker(ScannerEntity):
    """Representation of a tracked device."""

    def __init__(
        self, coordinator: AsusWrtMerlinDataUpdateCoordinator, device: dict[str, Any]
    ) -> None:
        """Initialize the device tracker."""
        self.coordinator = coordinator
        self._device = device
        self._attr_name = device[ATTR_HOSTNAME]
        self._attr_unique_id = device[ATTR_MAC]
        # New devices are created as disabled by default
        self._attr_entity_registry_enabled_default = False

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if the entity should be enabled when first added to the entity registry."""
        return False

    @property
    def entity_registry_disabled_by(self) -> str | None:
        """Return if the entity should be disabled when first added to the entity registry."""
        return "integration"

    @property
    def is_connected(self) -> bool:
        """Return true if the device is connected to the network."""
        if not self.coordinator.data:
            return False

        # Find the device in the current data
        for device in self.coordinator.data:
            if device[ATTR_MAC] == self._device[ATTR_MAC]:
                # Check if device is currently connected (in ARP table)
                if device.get("is_connected", False):
                    return True

                # Check if device was seen recently (only if last_activity exists)
                last_activity = device.get(ATTR_LAST_ACTIVITY)
                if last_activity is not None:
                    if isinstance(last_activity, str):
                        last_activity = datetime.fromisoformat(last_activity)
                    time_diff = datetime.now() - last_activity
                    if time_diff.total_seconds() < self.coordinator.consider_home:
                        return True
                
                # If last_activity is None, device is not connected
                return False

        return False

    @property
    def state(self) -> str:
        """Return the state of the device."""
        if self.is_connected:
            return "home"
        return "not_home"

    @property
    def source_type(self) -> str:
        """Return the source type of the device."""
        return "router"

    @property
    def ip_address(self) -> str | None:
        """Return the IP address of the device."""
        if not self.coordinator.data:
            return None

        for device in self.coordinator.data:
            if device[ATTR_MAC] == self._device[ATTR_MAC]:
                return device.get(ATTR_IP)

        return None

    @property
    def mac_address(self) -> str:
        """Return the MAC address of the device."""
        return self._device[ATTR_MAC]

    @property
    def hostname(self) -> str:
        """Return the hostname of the device."""
        return self._device[ATTR_HOSTNAME]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        attrs = {
            ATTR_MAC: self.mac_address,
        }

        if self.ip_address:
            attrs[ATTR_IP] = self.ip_address

        return attrs

    @property
    def should_poll(self) -> bool:
        """No need to poll. Coordinator notifies entity of updates."""
        return False

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information - link to main router device."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.entry.entry_id)},
            "name": f"AsusWrt-Merlin router {self.coordinator.entry.data['host']}",
            "manufacturer": "ASUS",
            "model": "AsusWrt-Merlin router",
        }

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        _LOGGER.debug("Device tracker entity %s added to hass with enabled_default=%s", 
                     self.name, self.entity_registry_enabled_default)
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_update(self) -> None:
        """Update the entity.

        Only used by the generic entity update service.
        """
        await self.coordinator.async_request_refresh()
