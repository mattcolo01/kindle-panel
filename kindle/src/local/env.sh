#!/usr/bin/env sh

# Export environment variables here

# REQUIRED: LAN IP of the server running kindle-gateway. Used only to check
# that Wi-Fi is up (ping), so it must be the IP, not the host name.
export WIFI_TEST_IP=${WIFI_TEST_IP:-""}

# REQUIRED: kindle-gateway URL. Use the host name in the server certificate
# (gen-certs.sh), resolved by the LAN DNS: the bundled xh cannot do HTTPS to
# an IP address. Example: https://homeserver.lan:8443
export GATEWAY_URL=${GATEWAY_URL:-""}

# The Kindle token goes in local/token (one line, not committed to git).
# Setting KINDLE_TOKEN here instead also works.

export REFRESH_SCHEDULE=${REFRESH_SCHEDULE:-"*/15 7-23 * * *"}
export TIMEZONE=${TIMEZONE:-"Europe/Rome"}

# By default, partial screen updates are used to update the screen,
# to prevent the screen from flashing. After a few partial updates,
# the screen will start to look a bit distorted (due to e-ink ghosting).
# This number determines when a full refresh is triggered. By default it's
# triggered after 4 partial updates.
export FULL_DISPLAY_REFRESH_RATE=${FULL_DISPLAY_REFRESH_RATE:-4}

# When the time until the next wakeup is greater or equal to this number,
# the dashboard will not be refreshed anymore, but instead show a
# 'kindle is sleeping' screen. This can be useful if your schedule only runs
# during the day, for example.
export SLEEP_SCREEN_INTERVAL=3600

export LOW_BATTERY_REPORTING=${LOW_BATTERY_REPORTING:-false}
export LOW_BATTERY_THRESHOLD_PERCENT=10
