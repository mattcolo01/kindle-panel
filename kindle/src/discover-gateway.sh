#!/usr/bin/env sh
# Print the gateway IP. With GATEWAY_MAC and GATEWAY_ARP_NETWORK configured,
# recover a changed DHCP address using a bounded ICMP-triggered ARP sweep.
DIR="$(dirname "$0")"
STATE_DIR="$DIR/local/state"
CACHE_FILE="$STATE_DIR/gateway_ip"

mac=$(echo "$GATEWAY_MAC" | tr 'A-F' 'a-f')
network=$GATEWAY_ARP_NETWORK
parallel=$GATEWAY_ARP_PARALLELISM
case "$parallel" in
  '' | *[!0-9]*) parallel=16 ;;
esac
[ "$parallel" -gt 0 ] || parallel=16

ip_for_mac() {
  awk -v wanted="$mac" 'NR > 1 && tolower($4) == wanted { print $1; exit }' /proc/net/arp 2>/dev/null
}

matches_mac() {
  candidate=$1
  [ -n "$candidate" ] || return 1
  ping -c 1 -W 1 "$candidate" >/dev/null 2>&1 || return 1
  [ "$(ip_for_mac)" = "$candidate" ]
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
for candidate in "$cached" "$WIFI_TEST_IP"; do
  if matches_mac "$candidate"; then
    save_and_print "$candidate"
    exit 0
  fi
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
set -- $network
IFS=$old_ifs
if [ "$#" -ne 3 ]; then
  echo "gateway discovery: GATEWAY_ARP_NETWORK must be the first three IPv4 octets" >&2
  echo "$WIFI_TEST_IP"
  exit 0
fi

echo "gateway discovery: scanning $network.0/24 for $mac" >&2
found="$STATE_DIR/gateway_ip.found"
rm -f "$found"
mkdir -p "$STATE_DIR"
i=1
running=0
while [ "$i" -le 254 ]; do
  candidate="$network.$i"
  (
    ping -c 1 -W 1 "$candidate" >/dev/null 2>&1 || exit 0
    [ "$(ip_for_mac)" = "$candidate" ] && echo "$candidate" >"$found"
  ) &
  running=$((running + 1))
  if [ "$running" -ge "$parallel" ]; then
    wait
    [ -s "$found" ] && break
    running=0
  fi
  i=$((i + 1))
done
wait

if [ -s "$found" ]; then
  candidate=$(cat "$found")
  rm -f "$found"
  echo "gateway discovery: found $mac at $candidate" >&2
  save_and_print "$candidate"
  exit 0
fi
rm -f "$found"
echo "gateway discovery: MAC $mac not found; keeping configured IP" >&2
echo "$WIFI_TEST_IP"
