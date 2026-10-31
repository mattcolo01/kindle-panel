#!/usr/bin/env sh
# Read the Kindle keys and leave them to dash.sh, which acts on them:
#   Back           -> touch $RUN_DIR/exit (dash.sh closes the dashboard)
#   any other key  -> append its name to $RUN_DIR/presses
# Keys not in key_name are logged and ignored. The power button is not an
# input key: it only wakes the Kindle (dash.sh notices the early wake).
#
# One reader per /dev/input/event*: a long-running dd keeps the device open,
# so no event is lost between two presses, and copies whole 16-byte
# input_event records into a pipe; each record is decoded with od -d (plain
# busybox, no hexdump formats). struct input_event on the 32-bit K4:
#   struct timeval (2 x 4 bytes), __u16 type, __u16 code, __s32 value
# od -d prints the offset, then the record as 8 unsigned 16-bit words.
#
# Usage: buttons.sh <run dir> [input device...]
RUN_DIR=$1
shift
[ $# -gt 0 ] || set -- /dev/input/event*

EV_KEY=1
PRESSED=1 # 0 = released, 2 = autorepeat

# Key codes of the Kindle 4 NT, as in KOReader (event_map_kindle4.lua)
key_name() {
  case $1 in
  191) echo right_next ;;
  109) echo right_prev ;;
  104) echo left_next ;;
  193) echo left_prev ;;
  103) echo up ;;
  108) echo down ;;
  105) echo left ;;
  106) echo right ;;
  194 | 28) echo select ;;
  139) echo menu ;;
  102) echo home ;;
  29) echo keyboard ;;
  158) echo back ;;
  esac
}

read_device() {
  dd if="$1" bs=16 2>/dev/null | while true; do
    # shellcheck disable=SC2046
    set -- $(dd bs=16 count=1 2>/dev/null | od -d)
    # Offset, 8 words, end offset; less means the device went away
    [ $# -ge 9 ] || exit 0
    type=$6 code=$7 value=$8
    if [ "$type" -ne "$EV_KEY" ] || [ "$value" -ne "$PRESSED" ]; then
      continue
    fi
    name=$(key_name "$code")
    if [ -z "$name" ]; then
      echo "Key $code: not a dashboard key"
    elif [ "$name" = back ]; then
      echo "Key $code: back, closing the dashboard"
      : >"$RUN_DIR/exit"
    else
      echo "Key $code: $name"
      echo "$name" >>"$RUN_DIR/presses"
    fi
  done
}

for device in "$@"; do
  [ -c "$device" ] || [ -p "$device" ] || continue
  read_device "$device" &
done
wait
