#!/usr/bin/env sh
# Map the gateway host name (from GATEWAY_URL) to WIFI_TEST_IP in /etc/hosts,
# so no LAN DNS record is needed. The root filesystem is read-only: it is
# remounted read-write only when the entry is missing or different.
HOSTS=/etc/hosts
TMP_HOSTS=/var/tmp/hosts.new

host=$(echo "$GATEWAY_URL" | sed -n 's#^https*://\([^:/]*\).*#\1#p')
ip=$WIFI_TEST_IP

if [ -z "$host" ] || [ -z "$ip" ]; then
  echo "setup-hosts: GATEWAY_URL or WIFI_TEST_IP not set"
  exit 1
fi

entry="$ip $host"
if grep -q -x "$entry" "$HOSTS" 2>/dev/null; then
  echo "setup-hosts: $HOSTS already maps $host to $ip"
  exit 0
fi

# Drop any other line for this host name, then append the entry
mkdir -p "$(dirname "$TMP_HOSTS")"
host_re=$(echo "$host" | sed 's/\./\\./g')
grep -v "[[:space:]]$host_re\$" "$HOSTS" >"$TMP_HOSTS" 2>/dev/null
echo "$entry" >>"$TMP_HOSTS"
# Never overwrite /etc/hosts with a broken temporary file
if ! grep -q -x "$entry" "$TMP_HOSTS" 2>/dev/null; then
  echo "setup-hosts: could not prepare $TMP_HOSTS"
  rm -f "$TMP_HOSTS"
  exit 1
fi

mount -o rw,remount /
# cat > (not mv) so that a symlinked /etc/hosts keeps working
cat "$TMP_HOSTS" >"$HOSTS"
write_status=$?
sync
mount -o ro,remount /
rm -f "$TMP_HOSTS"

if [ "$write_status" -ne 0 ] || ! grep -q -x "$entry" "$HOSTS"; then
  echo "setup-hosts: could not write $entry to $HOSTS"
  exit 1
fi
echo "setup-hosts: added $entry to $HOSTS"
