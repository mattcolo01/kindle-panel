#!/usr/bin/env sh
# Copy to local/device.sh (git-ignored) and fill in. Sourced by local/env.sh.

# LAN IP of the server running kindle-gateway
export WIFI_TEST_IP="192.168.1.10"

# Host name in the gateway certificate (gen-certs.sh), never an IP
export GATEWAY_URL="https://kindle-gateway.local:8443"

# Optional: automatic IP recovery by MAC when the gateway gets a new DHCP IP.
# The scan is used only when WIFI_TEST_IP (or the saved IP) is not this MAC.
# export GATEWAY_MAC="00:11:22:33:44:55"
# export GATEWAY_ARP_NETWORK="192.168.1"  # first three octets of the /24 LAN
