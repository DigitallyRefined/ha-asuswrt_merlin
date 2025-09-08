"""Constants for the AsusWrt-Merlin integration."""

DOMAIN = "asuswrt_merlin"

# Configuration keys
CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_SSH_KEY = "ssh_key"
CONF_PORT = "port"
CONF_MODE = "mode"
CONF_CONSIDER_HOME = "consider_home"

# Default values
DEFAULT_PORT = 22
DEFAULT_CONSIDER_HOME = 180
DEFAULT_MODE = "ssh"

# SSH commands
CMD_ARP = "cat /proc/net/arp"
CMD_DEVICES = "cat /var/lib/misc/dnsmasq.leases"

# Device tracker attributes
ATTR_HOSTNAME = "hostname"
ATTR_MAC = "mac"
ATTR_IP = "ip"
ATTR_LAST_ACTIVITY = "last_activity"
