#!/usr/bin/env sh
# Map the gateway host name (from GATEWAY_URL) to WIFI_TEST_IP in /etc/hosts,
# so no LAN DNS record is needed. The root filesystem is read-only: it is
# remounted read-write only when the entry is missing or different.
# Plain shell only: the K4 busybox is too old for options like grep -x.
HOSTS=/etc/hosts
TMP_HOSTS=/var/tmp/hosts.new

host=$(echo "$GATEWAY_URL" | sed -n 's#^https*://\([^:/]*\).*#\1#p')
ip=$WIFI_TEST_IP

fail() {
  echo "setup-hosts: $1"
  busybox 2>&1 | head -n 1
  rm -f "$TMP_HOSTS"
  exit 1
}

# True if file $1 has a line "<ip> <host>" (any whitespace, nothing else)
has_entry() {
  [ -f "$1" ] || return 1
  while read -r addr name rest; do
    [ "$addr" = "$ip" ] && [ "$name" = "$host" ] && [ -z "$rest" ] && return 0
  done <"$1"
  return 1
}

# Copy $HOSTS to stdout without the lines mentioning $host
without_host() {
  [ -f "$HOSTS" ] || return 0
  set -f
  while IFS= read -r line; do
    # shellcheck disable=SC2086
    set -- $line
    keep=1
    if [ $# -gt 1 ] && [ "${1#\#}" = "$1" ]; then
      shift
      for name in "$@"; do
        [ "$name" = "$host" ] && keep=0
      done
    fi
    [ "$keep" -eq 1 ] && echo "$line"
  done <"$HOSTS"
  set +f
}

if [ -z "$host" ] || [ -z "$ip" ]; then
  fail "GATEWAY_URL or WIFI_TEST_IP not set"
fi

if has_entry "$HOSTS"; then
  echo "setup-hosts: $HOSTS already maps $host to $ip"
  exit 0
fi

mkdir -p "$(dirname "$TMP_HOSTS")"
{
  without_host
  echo "$ip $host"
} >"$TMP_HOSTS" || fail "could not write $TMP_HOSTS"
# Never overwrite /etc/hosts with a broken temporary file
has_entry "$TMP_HOSTS" || fail "could not prepare $TMP_HOSTS"

mount -o rw,remount / || fail "could not remount / read-write"
# cat > (not mv) so that a symlinked /etc/hosts keeps working
cat "$TMP_HOSTS" >"$HOSTS"
write_status=$?
rm -f "$TMP_HOSTS"
sync
mount -o ro,remount /

if [ "$write_status" -ne 0 ] || ! has_entry "$HOSTS"; then
  fail "could not write $ip $host to $HOSTS"
fi
echo "setup-hosts: added $ip $host to $HOSTS"
