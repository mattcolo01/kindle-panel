#!/usr/bin/env sh
# Fetch a new dashboard image from kindle-gateway, output it to "$1".
# Further arguments are the names of the keys pressed: then the request is
# POST /press, which checks off their tasks and answers with the new image.
# Exit codes: 0 = new image in "$1", 1 = fetch failed, 2 = image unchanged.
DIR="$(dirname "$0")/.."
out=$1
shift

method="get"
url="$GATEWAY_URL/kindle.png"
if [ $# -gt 0 ]; then
  method="post"
  url="$GATEWAY_URL/press"
  # Each key name becomes a query item for xh: button==<name>
  for button in "$@"; do
    set -- "$@" "button==$button"
    shift
  done
fi
STATE_DIR="$DIR/local/state"
LAST_HASH_FILE="$STATE_DIR/last_hash"
TOKEN_FILE="$DIR/local/token"
CA_FILE="$DIR/local/ca.pem"

if [ -z "$KINDLE_TOKEN" ] && [ -f "$TOKEN_FILE" ]; then
  KINDLE_TOKEN=$(tr -d '\r\n' <"$TOKEN_FILE")
fi

if [ -z "$GATEWAY_URL" ] || [ -z "$KINDLE_TOKEN" ] || [ ! -f "$CA_FILE" ]; then
  echo "Missing configuration: GATEWAY_URL (local/env.sh), KINDLE_TOKEN (local/token) or local/ca.pem"
  exit 1
fi

if command -v md5sum >/dev/null 2>&1; then
  hash_cmd="md5sum"
elif command -v sha1sum >/dev/null 2>&1; then
  hash_cmd="sha1sum"
else
  hash_cmd="cksum"
fi

mkdir -p "$STATE_DIR"
tmp="$STATE_DIR/dash.png.tmp"
battery=$(gasgauge-info -c 2>/dev/null | tr -d %)

"$DIR/xh" --ignore-stdin --verify="$CA_FILE" -A bearer -a "$KINDLE_TOKEN" \
  --check-status --timeout 20 -d -q -o "$tmp" \
  "$method" "$url" "$@" X-Kindle-Battery:"$battery"
xh_status=$?
if [ "$xh_status" -ne 0 ]; then
  # xh: 1 = connection/TLS error, 2 = timeout, 4 = HTTP 4xx, 5 = HTTP 5xx
  echo "Fetch failed, xh returned $xh_status"
  rm -f "$tmp"
  exit 1
fi

new_hash=$($hash_cmd <"$tmp")
# An empty hash (hash command failed) never counts as unchanged
if [ -n "$new_hash" ] && [ -f "$LAST_HASH_FILE" ] &&
  [ "$new_hash" = "$(cat "$LAST_HASH_FILE")" ]; then
  rm -f "$tmp"
  echo "Dashboard image unchanged"
  exit 2
fi

mv "$tmp" "$out" || exit 1
echo "$new_hash" >"$LAST_HASH_FILE"
exit 0
