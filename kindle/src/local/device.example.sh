#!/usr/bin/env sh
# Copy to local/device.sh (git-ignored) and fill in. Sourced by local/env.sh.

# LAN IP of the server running kindle-gateway
export WIFI_TEST_IP="192.168.1.10"

# Host name in the gateway certificate (gen-certs.sh), never an IP
export GATEWAY_URL="https://kindle-gateway.local:8443"
