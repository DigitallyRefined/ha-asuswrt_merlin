"""Config flow for AsusWrt-Merlin integration."""
from __future__ import annotations

import logging
import os
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_CONSIDER_HOME,
    CONF_MODE,
    CONF_SSH_KEY,
    DEFAULT_CONSIDER_HOME,
    DEFAULT_MODE,
    DEFAULT_PORT,
    DOMAIN,
)
from .ssh_client import AsusWrtSSHClient

_LOGGER = logging.getLogger(__name__)

async def validate_ssh_key_file(hass: HomeAssistant, value: str) -> str:
    """Validate SSH key file path."""
    if not value:
        return value

    if not os.path.exists(value):
        raise vol.Invalid(f"SSH key file not found: {value}")

    if not os.path.isfile(value):
        raise vol.Invalid(f"SSH key path is not a file: {value}")

    # Check if file is readable using async executor
    def _check_file_readable():
        try:
            with open(value, 'r') as f:
                f.read(1)  # Try to read at least one character
        except (OSError, IOError) as ex:
            raise vol.Invalid(f"Cannot read SSH key file: {ex}") from ex

    try:
        await hass.async_add_executor_job(_check_file_readable)
    except vol.Invalid:
        raise

    return value


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Optional(CONF_PASSWORD): str,
        vol.Optional(CONF_SSH_KEY): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_CONSIDER_HOME, default=DEFAULT_CONSIDER_HOME): int,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    # Validate SSH key file if provided
    ssh_key = data.get(CONF_SSH_KEY)
    if ssh_key:
        await validate_ssh_key_file(hass, ssh_key)
    
    ssh_client = AsusWrtSSHClient(
        host=data[CONF_HOST],
        port=data[CONF_PORT],
        username=data[CONF_USERNAME],
        password=data.get(CONF_PASSWORD),
        ssh_key=ssh_key,
    )

    try:
        await hass.async_add_executor_job(ssh_client.connect)
        devices = await hass.async_add_executor_job(ssh_client.get_connected_devices)
        ssh_client.disconnect()
    except Exception as ex:
        raise CannotConnect from ex

    return {"title": f"AsusWrt-Merlin {data[CONF_HOST]}"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AsusWrt-Merlin."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}

        try:
            info = await validate_input(self.hass, user_input)
        except vol.Invalid as ex:
            errors["base"] = str(ex)
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""
