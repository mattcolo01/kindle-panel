#!/usr/bin/env sh
# Read the Kindle keys and leave them to dash.sh, which acts on them:
#   Back           -> touch $RUN_DIR/exit (dash.sh closes the dashboard)
#   any other key  -> append its name to $RUN_DIR/presses
# The power button is not one of these keys: it only wakes the Kindle
# (dash.sh notices the early wake).
#
# One reader per /dev/input/event*: a long-running dd keeps the device open,
# so no event is lost between two presses, and copies whole 16-byte
# input_event records into a pipe. struct input_event on the 32-bit K4:
#   struct timeval (2 x 4 bytes), __u16 type, __u16 code, __s32 value
#
# The K4 busybox has no od, hexdump or md5sum: records are decoded with tr
# alone, which maps every byte to one character (TR_FROM -> TR_TO): 0x00 to
# "0", 0x01 to "1", the code of each dashboard key to its letter in KEYS,
# any other byte to ".". A key press (type 1, code, value 1) then reads
# "10<letter>01000" after the 8 characters of the timestamp. The raw record
# of a key not in KEYS goes to logs/unknown-keys.bin, to look up its code.
#
# Usage: buttons.sh <run dir> [input device...]
DIR="$(dirname "$0")"
RUN_DIR=$1
shift
[ $# -gt 0 ] || set -- /dev/input/event*
UNKNOWN_KEYS="$DIR/logs/unknown-keys.bin"

# Key codes of the Kindle 4 NT, as in KOReader (event_map_kindle4.lua):
# code:letter. 194 and 28 are both the 5-way center (K4 / K3).
KEYS="191:a 109:b 104:c 193:d 103:e 108:f 105:g 106:h 194:i 28:i 139:j 102:k 29:l 158:m"

key_name() {
  case $1 in
  a) echo right_next ;;
  b) echo right_prev ;;
  c) echo left_next ;;
  d) echo left_prev ;;
  e) echo up ;;
  f) echo down ;;
  g) echo left ;;
  h) echo right ;;
  i) echo select ;;
  j) echo menu ;;
  k) echo home ;;
  l) echo keyboard ;;
  m) echo back ;;
  esac
}

# Every byte as an octal escape (escapes are never ranges or classes for tr).
# One subshell for the 256 printf: forks are slow on the K4.
TR_FROM=$(
  byte=0
  while [ "$byte" -le 255 ]; do
    printf '\\%03o' "$byte"
    byte=$((byte + 1))
  done
)
TR_TO=""
byte=0
while [ "$byte" -le 255 ]; do
  char=.
  [ "$byte" -eq 0 ] && char=0
  [ "$byte" -eq 1 ] && char=1
  for pair in $KEYS; do
    [ "${pair%:*}" -eq "$byte" ] && char=${pair#*:}
  done
  TR_TO="$TR_TO$char"
  byte=$((byte + 1))
done

read_device() {
  raw="$RUN_DIR/raw.${1##*/}"
  dd if="$1" bs=16 2>/dev/null | while true; do
    dd bs=16 count=1 of="$raw" 2>/dev/null
    event=$(tr "$TR_FROM" "$TR_TO" <"$raw")
    # Less than a record: the device went away
    [ ${#event} -eq 16 ] || exit 0
    # Drop the timestamp: type (2 bytes), code (2), value (4) remain
    event=${event#????????}
    case $event in
    10?01000) ;;
    *) continue ;;
    esac
    letter=${event#??}
    letter=${letter%?????}
    if [ "$letter" = . ]; then
      echo "Unknown key: raw event appended to $UNKNOWN_KEYS"
      cat "$raw" >>"$UNKNOWN_KEYS"
      continue
    fi
    name=$(key_name "$letter")
    if [ "$name" = back ]; then
      echo "Key back: closing the dashboard"
      : >"$RUN_DIR/exit"
    else
      echo "Key $name"
      echo "$name" >>"$RUN_DIR/presses"
    fi
  done
}

echo "Reading keys from: $*"
for device in "$@"; do
  [ -c "$device" ] || [ -p "$device" ] || continue
  read_device "$device" &
done
wait
