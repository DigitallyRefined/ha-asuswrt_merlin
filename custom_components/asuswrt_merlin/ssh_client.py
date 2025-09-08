"""SSH client for AsusWrt-Merlin integration."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any

import paramiko

from .const import ATTR_HOSTNAME, ATTR_IP, ATTR_LAST_ACTIVITY, ATTR_MAC, CMD_ARP, CMD_DEVICES

_LOGGER = logging.getLogger(__name__)


class AsusWrtSSHClient:
    """SSH client for AsusWrt-Merlin router."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str | None = None,
        ssh_key: str | None = None,
    ) -> None:
        """Initialize the SSH client.

        Args:
            host: Router IP address
            port: SSH port
            username: SSH username
            password: SSH password (optional if using SSH key)
            ssh_key: Path to SSH private key file (optional if using password)
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.ssh_key = ssh_key  # This should be a file path
        self.client: paramiko.SSHClient | None = None

    def connect(self) -> None:
        """Connect to the router via SSH."""
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            if self.ssh_key:
                # Use SSH key authentication
                key = self._load_ssh_key(self.ssh_key)
                self.client.connect(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    pkey=key,
                    timeout=10,
                )
            else:
                # Use password authentication
                self.client.connect(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    timeout=10,
                )
        except Exception as ex:
            self.client.close()
            self.client = None
            raise ConnectionError(f"Failed to connect to {self.host}:{self.port}") from ex

    def disconnect(self) -> None:
        """Disconnect from the router."""
        if self.client:
            self.client.close()
            self.client = None

    def _load_ssh_key(self, key_path: str) -> paramiko.PKey:
        """Load SSH private key from file, supporting multiple key types."""
        try:
            # Try different key types in order of preference
            key_types = [
                paramiko.Ed25519Key,
                paramiko.ECDSAKey,
                paramiko.RSAKey,
                paramiko.DSSKey,
            ]

            for key_type in key_types:
                try:
                    return key_type.from_private_key_file(key_path)
                except (paramiko.SSHException, paramiko.PasswordRequiredException):
                    continue

            # If all key types fail, try with password prompt disabled
            try:
                return paramiko.RSAKey.from_private_key_file(key_path, password=None)
            except paramiko.SSHException:
                pass

            raise paramiko.SSHException(f"Unable to load SSH key from {key_path}")

        except Exception as ex:
            raise ConnectionError(f"Failed to load SSH key from {key_path}: {ex}") from ex

    def _execute_command(self, command: str) -> str:
        """Execute a command on the router."""
        if not self.client:
            raise ConnectionError("Not connected to router")

        try:
            stdin, stdout, stderr = self.client.exec_command(command)
            output = stdout.read().decode("utf-8")
            error = stderr.read().decode("utf-8")

            if error:
                _LOGGER.warning("Command error: %s", error)

            return output
        except Exception as ex:
            raise RuntimeError(f"Failed to execute command: {command}") from ex

    def get_connected_devices(self) -> list[dict[str, Any]]:
        """Get list of connected devices from the router."""
        devices = []

        try:
            # Get DHCP leases
            dhcp_output = self._execute_command(CMD_DEVICES)
            dhcp_devices = self._parse_dhcp_leases(dhcp_output)

            # Get ARP table
            arp_output = self._execute_command(CMD_ARP)
            arp_devices = self._parse_arp_table(arp_output)

            # Merge DHCP and ARP data
            for dhcp_device in dhcp_devices:
                mac = dhcp_device[ATTR_MAC].upper()
                
                # Check if device is in ARP table (active)
                is_connected = any(
                    arp_device[ATTR_MAC].upper() == mac for arp_device in arp_devices
                )
                
                device = {
                    ATTR_MAC: mac,
                    ATTR_HOSTNAME: dhcp_device[ATTR_HOSTNAME],
                    ATTR_IP: dhcp_device[ATTR_IP],
                    "is_connected": is_connected,
                }

                # Only update last_activity for devices that are actually connected (in ARP table)
                if is_connected:
                    device[ATTR_LAST_ACTIVITY] = datetime.now()
                else:
                    # For devices not in ARP table, we don't set last_activity
                    # This will cause them to be marked as away
                    device[ATTR_LAST_ACTIVITY] = None

                devices.append(device)

            _LOGGER.debug("Found %d devices", len(devices))
            connected_count = sum(1 for device in devices if device.get("is_connected", False))
            _LOGGER.debug("Found %d connected devices (in ARP table)", connected_count)
            return devices

        except Exception as ex:
            _LOGGER.error("Failed to get connected devices: %s", ex)
            return []

    def _parse_dhcp_leases(self, output: str) -> list[dict[str, str]]:
        """Parse DHCP leases output."""
        devices = []
        lines = output.strip().split("\n")

        for line in lines:
            if not line.strip():
                continue

            # Format: timestamp mac ip hostname client_id
            parts = line.split()
            if len(parts) >= 4:
                hostname = parts[3]
                # Use MAC address with underscores if hostname is empty, "*", or just whitespace
                if not hostname or hostname == "*" or not hostname.strip():
                    hostname = f"device_{parts[1].replace(':', '_')}"
                
                devices.append({
                    ATTR_MAC: parts[1],
                    ATTR_IP: parts[2],
                    ATTR_HOSTNAME: hostname,
                })

        return devices

    def _parse_arp_table(self, output: str) -> list[dict[str, str]]:
        """Parse ARP table output."""
        devices = []
        lines = output.strip().split("\n")

        for line in lines:
            if not line.strip() or line.startswith("IP address"):
                continue

            # Format: IP address HW type Flags HW address Mask Device
            parts = line.split()
            if len(parts) >= 6 and parts[2] == "0x2":  # 0x2 means reachable
                devices.append({
                    ATTR_IP: parts[0],
                    ATTR_MAC: parts[3],
                    ATTR_HOSTNAME: f"device_{parts[3].replace(':', '_')}",
                })

        return devices
