"""Constants for the AsusWrt-Merlin integration."""

DOMAIN = "asuswrt_merlin"

# Configuration keys
CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_SSH_KEY = "ssh_key"
CONF_PORT = "port"
CONF_MODE = "mode"
# Configuration option: seconds a device can be inactive before marked away
CONF_SECONDS_UNTIL_AWAY = "seconds_until_away"

# Default values
DEFAULT_PORT = 22
DEFAULT_SECONDS_UNTIL_AWAY = 180
DEFAULT_MODE = "ssh"

# SSH commands
CMD_ARP = "cat /proc/net/arp"
CMD_DEVICES = "cat /var/lib/misc/dnsmasq.leases"
CMD_WAN_IFNAME = "nvram get wan_ifname"
CMD_PROC_NET_DEV = "cat /proc/net/dev"

# Device tracker attributes
ATTR_HOSTNAME = "hostname"
ATTR_MAC = "mac"
ATTR_IP = "ip"
ATTR_LAST_SEEN = "last_seen"
