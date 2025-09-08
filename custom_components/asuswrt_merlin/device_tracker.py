"""Device tracker platform for AsusWrt-Merlin integration."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.device_tracker import ScannerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_HOSTNAME,
    ATTR_IP,
    ATTR_LAST_ACTIVITY,
    ATTR_MAC,
    DOMAIN,
)
from .coordinator import AsusWrtMerlinDataUpdateCoordinator

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


class AsusWrtMerlinDataUpdateCoordinator(AsusWrtMerlinDataUpdateCoordinator):
    """Backwards-compatible alias imported by device_tracker and sensor modules."""

    pass


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
        _LOGGER.debug(
            "Device tracker entity %s added to hass with enabled_default=%s",
            self.name,
            self.entity_registry_enabled_default,
        )
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_update(self) -> None:
        """Update the entity.

        Only used by the generic entity update service.
        """
        await self.coordinator.async_request_refresh()
