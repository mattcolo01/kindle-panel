#!/usr/bin/env sh
# Used by the KUAL menu: only works while the Kindle framework is running.
"$(dirname "$0")/stop.sh"
reboot
