#!/usr/bin/env sh
# Print the gateway IP. With GATEWAY_MAC and GATEWAY_ARP_NETWORK configured,
# recover a changed DHCP address using a bounded ICMP-triggered ARP sweep.
#
# The K4 busybox (1.7.2) ping takes only -q -v -c -s -I -4: no -W or -w, and
# with -c 1 it waits up to 10 s for a host that does not answer. Every ping
# here runs in the background and is killed at a deadline. Sending it makes
# the kernel resolve the IP over ARP: /proc/net/arp then tells the MAC.
# An IP counts only if it also answers the ping: with few neighbours the
# kernel keeps stale ARP entries indefinitely, so the old IP of the gateway
# can still show its MAC long after it moved.
DIR="$(dirname "$0")"
STATE_DIR="$DIR/local/state"
CACHE_FILE="$STATE_DIR/gateway_ip"
PROBE_SECONDS=2 # deadline of the ping to a candidate
SWEEP_SECONDS=1 # time given to each batch of the sweep to answer ARP
WIFI_WAIT_SECONDS=30

mac=$(echo "$GATEWAY_MAC" | tr 'A-F' 'a-f')
network=$GATEWAY_ARP_NETWORK
parallel=$GATEWAY_ARP_PARALLELISM
case "$parallel" in
'' | *[!0-9]*) parallel=16 ;;
esac
[ "$parallel" -gt 0 ] || parallel=16

# The IP the ARP table gives to the MAC, if not one of the IPs in $1
ip_for_mac() {
  awk -v wanted="$mac" -v skip=" $1 " \
    'NR > 1 && tolower($4) == wanted && index(skip, " " $1 " ") == 0 { print $1; exit }' \
    /proc/net/arp 2>/dev/null
}

# True if the ARP table gives the MAC to IP $1
arp_has() {
  awk -v wanted="$mac" -v ip="$1" \
    'NR > 1 && tolower($4) == wanted && $1 == ip { found = 1 } END { exit !found }' \
    /proc/net/arp 2>/dev/null
}

# Ping $1 once, for at most $2 seconds; true if it answered
probe() {
  ping -c 1 "$1" >/dev/null 2>&1 &
  pinger=$!
  # Not on our stdout: callers read it with $(...), which would wait for the
  # watchdog's sleep even after the watchdog is killed
  (
    sleep "$2"
    kill "$pinger" 2>/dev/null
  ) >/dev/null 2>&1 &
  watchdog=$!
  wait "$pinger" 2>/dev/null
  answered=$?
  kill "$watchdog" 2>/dev/null
  return "$answered"
}

matches_mac() {
  [ -n "$1" ] || return 1
  probe "$1" "$PROBE_SECONDS" && arp_has "$1"
}

save_and_print() {
  mkdir -p "$STATE_DIR"
  echo "$1" >"$CACHE_FILE"
  echo "$1"
}

# Without a MAC this remains exactly the previous static-IP behaviour.
if [ -z "$mac" ] || [ -z "$network" ]; then
  echo "$WIFI_TEST_IP"
  exit 0
fi

cached=""
[ -f "$CACHE_FILE" ] && cached=$(cat "$CACHE_FILE")
# What to print when nothing answers: the last IP that matched, if any
last_known=${cached:-$WIFI_TEST_IP}

# Right after a resume Wi-Fi may still be connecting, and every probe would
# fail: wait for wifid first. Without lipc-get-prop (not a Kindle), go on.
waited=0
while state=$(lipc-get-prop com.lab126.wifid cmState 2>/dev/null) &&
  [ "$state" != CONNECTED ]; do
  if [ "$waited" -ge "$WIFI_WAIT_SECONDS" ]; then
    echo "gateway discovery: Wi-Fi not connected ($state); keeping $last_known" >&2
    echo "$last_known"
    exit 0
  fi
  sleep 1
  waited=$((waited + 1))
done

rejected=""
for candidate in "$cached" "$WIFI_TEST_IP"; do
  if matches_mac "$candidate"; then
    save_and_print "$candidate"
    exit 0
  fi
  rejected="$rejected $candidate"
done

case "$network" in
*[!0-9.]* | .* | *.)
  echo "gateway discovery: GATEWAY_ARP_NETWORK must be the first three IPv4 octets" >&2
  echo "$WIFI_TEST_IP"
  exit 0
  ;;
esac
old_ifs=$IFS
IFS=.
# shellcheck disable=SC2086
set -- $network
IFS=$old_ifs
if [ "$#" -ne 3 ]; then
  echo "gateway discovery: GATEWAY_ARP_NETWORK must be the first three IPv4 octets" >&2
  echo "$WIFI_TEST_IP"
  exit 0
fi

echo "gateway discovery: scanning $network.0/24 for $mac" >&2
found=""
i=1
while [ "$i" -le 254 ] && [ -z "$found" ]; do
  # One batch: ping $parallel addresses at once, give them time to answer
  # ARP, stop the pings, look for the MAC
  pingers=""
  batch=0
  while [ "$i" -le 254 ] && [ "$batch" -lt "$parallel" ]; do
    ping -c 1 "$network.$i" >/dev/null 2>&1 &
    pingers="$pingers $!"
    batch=$((batch + 1))
    i=$((i + 1))
  done
  sleep "$SWEEP_SECONDS"
  # shellcheck disable=SC2086
  kill $pingers 2>/dev/null
  wait
  found=$(ip_for_mac "$rejected")
  if [ -n "$found" ] && ! matches_mac "$found"; then
    rejected="$rejected $found"
    found=""
  fi
done

if [ -n "$found" ]; then
  echo "gateway discovery: found $mac at $found" >&2
  save_and_print "$found"
  exit 0
fi
echo "gateway discovery: MAC $mac not found; keeping $last_known" >&2
echo "$last_known"
