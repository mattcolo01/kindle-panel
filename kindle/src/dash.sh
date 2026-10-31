#!/usr/bin/env sh
DEBUG=${DEBUG:-false}
[ "$DEBUG" = true ] && set -x

DIR="$(dirname "$0")"
DASH_PNG="$DIR/dash.png"
FETCH_DASHBOARD_CMD="$DIR/local/fetch-dashboard.sh"
LOW_BATTERY_CMD="$DIR/local/low-battery.sh"
LAST_HASH_FILE="$DIR/local/state/last_hash"
BUTTONS_CMD="$DIR/buttons.sh"
# Key presses live on tmpfs: they never touch the flash
RUN_DIR=/tmp/kindle-dash
PRESSES="$RUN_DIR/presses"
EXIT_FLAG="$RUN_DIR/exit"
GOVERNOR_FILE=/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor

REFRESH_SCHEDULE=${REFRESH_SCHEDULE:-"2,32 8-17 * * MON-FRI"}
FULL_DISPLAY_REFRESH_RATE=${FULL_DISPLAY_REFRESH_RATE:-0}
SLEEP_SCREEN_INTERVAL=${SLEEP_SCREEN_INTERVAL:-3600}
RTC=/sys/devices/platform/mxc_rtc.0/wakeup_enable

# Seconds awake after each refresh (the process can be aborted meanwhile),
# and after the power button wakes the Kindle or a key is pressed.
AWAKE_SECONDS=${AWAKE_SECONDS:-10}
BUTTON_WINDOW_SECONDS=${BUTTON_WINDOW_SECONDS:-30}
KINDLE_BUTTONS=${KINDLE_BUTTONS:-true}
# A wake this many seconds before the RTC alarm was the power button
MANUAL_WAKE_TOLERANCE=5

LOW_BATTERY_REPORTING=${LOW_BATTERY_REPORTING:-false}
LOW_BATTERY_THRESHOLD_PERCENT=${LOW_BATTERY_THRESHOLD_PERCENT:-10}

num_refresh=0
screen=none # what the screen shows: none | dashboard | sleeping

init() {
  if [ -z "$TIMEZONE" ] || [ -z "$REFRESH_SCHEDULE" ]; then
    echo "Missing required configuration."
    echo "Timezone: ${TIMEZONE:-(not set)}."
    echo "Schedule: ${REFRESH_SCHEDULE:-(not set)}."
    exit 1
  fi

  echo "Starting dashboard with $REFRESH_SCHEDULE refresh..."

  # Before stopping the framework, so the Kindle stays usable on failure
  "$DIR/setup-hosts.sh" || exit 1

  /etc/init.d/framework stop
  initctl stop webreader >/dev/null 2>&1
  governor=$(cat "$GOVERNOR_FILE")
  echo powersave >"$GOVERNOR_FILE"
  lipc-set-prop com.lab126.powerd preventScreenSaver 1

  # The screen does not show the dashboard yet: always draw the first fetch
  rm -f "$LAST_HASH_FILE"

  # Keys: started after the framework stops, so it does not see them too
  rm -rf "$RUN_DIR"
  mkdir -p "$RUN_DIR"
  "$BUTTONS_CMD" "$RUN_DIR" &
}

stop_buttons() {
  pkill -f buttons.sh
  pkill -f "dd if=/dev/input/"
}

# Back pressed: give the Kindle back to its own UI, without a reboot
exit_dashboard() {
  echo "Closing the dashboard, starting the Kindle framework"
  stop_buttons
  rm -rf "$RUN_DIR"
  /usr/sbin/eips -c
  /usr/sbin/eips 2 2 "Chiusura dashboard..."
  lipc-set-prop com.lab126.powerd preventScreenSaver 0
  [ -n "$governor" ] && echo "$governor" >"$GOVERNOR_FILE"
  /etc/init.d/framework start
  exit 0
}

# Print the keys pressed since the last call (each once, in order) and
# forget them. Nothing when the dashboard is not on the screen: the keys
# refer to the symbols drawn next to the tasks.
take_presses() {
  [ -s "$PRESSES" ] || return 0
  mv "$PRESSES" "$PRESSES.taken" || return 0
  if [ "$screen" != dashboard ] || [ "$KINDLE_BUTTONS" != true ]; then
    echo "Ignoring keys: $(tr '\n' ' ' <"$PRESSES.taken")" >&2
    rm -f "$PRESSES.taken"
    return 0
  fi
  taken=""
  while read -r name; do
    case " $taken " in
    *" $name "*) ;;
    *) taken="$taken $name" ;;
    esac
  done <"$PRESSES.taken"
  rm -f "$PRESSES.taken"
  echo "$taken"
}

prepare_sleep() {
  echo "Preparing sleep"

  /usr/sbin/eips -f -g "$DIR/sleeping.png"
  screen=sleeping

  # Give screen time to refresh
  sleep 2

  # Ensure a full screen refresh is triggered after wake from sleep
  num_refresh=$FULL_DISPLAY_REFRESH_RATE

  # Ensure the dashboard is redrawn after wake, even if unchanged
  rm -f "$LAST_HASH_FILE"
}

refresh_dashboard() {
  echo "Refreshing dashboard"
  # Revalidate the MAC before every fetch. setup-hosts only remounts / when
  # the mapping changed, so normal refreshes do not write the system rootfs.
  "$DIR/setup-hosts.sh" || return 1
  gateway_ip=$WIFI_TEST_IP
  [ -f "$DIR/local/state/gateway_ip" ] && gateway_ip=$(cat "$DIR/local/state/gateway_ip")
  "$DIR/wait-for-wifi.sh" "$gateway_ip"

  # Keys pressed so far go with this request: the gateway checks off the
  # tasks they had in the image on the screen, and answers with the new one.
  presses=$(take_presses)
  [ -n "$presses" ] && echo "Keys pressed:$presses"
  # shellcheck disable=SC2086
  "$FETCH_DASHBOARD_CMD" "$DASH_PNG" $presses
  fetch_status=$?

  # Unchanged image: the dashboard is what the screen shows already
  [ "$fetch_status" -eq 2 ] && screen=dashboard
  if [ "$fetch_status" -ne 0 ]; then
    echo "Not updating screen, fetch-dashboard returned $fetch_status"
    return 1
  fi

  # Keys pressed while the new image was on its way were aimed at the old
  # one, whose tasks may have moved to other keys: drop them.
  if [ -s "$PRESSES" ]; then
    echo "Ignoring keys pressed during the refresh: $(tr '\n' ' ' <"$PRESSES")"
    rm -f "$PRESSES"
  fi

  if [ "$num_refresh" -eq "$FULL_DISPLAY_REFRESH_RATE" ]; then
    num_refresh=0

    # trigger a full refresh once in every 4 refreshes, to keep the screen clean
    echo "Full screen refresh"
    /usr/sbin/eips -f -g "$DASH_PNG"
  else
    echo "Partial screen refresh"
    /usr/sbin/eips -g "$DASH_PNG"
  fi

  num_refresh=$((num_refresh + 1))
  screen=dashboard
}

# Stay awake for $1 seconds: Back closes the dashboard, the other keys
# check off tasks and keep the Kindle awake for BUTTON_WINDOW_SECONDS more.
awake_window() {
  until=$(($(date +%s) + $1))
  while [ "$(date +%s)" -lt "$until" ] || [ -s "$PRESSES" ]; do
    [ -f "$EXIT_FLAG" ] && exit_dashboard
    if [ -s "$PRESSES" ]; then
      if [ "$screen" = dashboard ] && [ "$KINDLE_BUTTONS" = true ]; then
        if ! refresh_dashboard && [ -s "$PRESSES" ]; then
          # Never retry in a loop (and never suspend) on a failing refresh
          echo "Ignoring keys: $(tr '\n' ' ' <"$PRESSES")"
          rm -f "$PRESSES"
        fi
        until=$(($(date +%s) + BUTTON_WINDOW_SECONDS))
      else
        take_presses
      fi
      continue
    fi
    sleep 1
  done
  [ -f "$EXIT_FLAG" ] && exit_dashboard
}

log_battery_stats() {
  battery_level=$(gasgauge-info -c)
  echo "$(date) Battery level: $battery_level."

  if [ "$LOW_BATTERY_REPORTING" = true ]; then
    battery_level_numeric=${battery_level%?}
    if [ "$battery_level_numeric" -le "$LOW_BATTERY_THRESHOLD_PERCENT" ]; then
      "$LOW_BATTERY_CMD" "$battery_level_numeric"
    fi
  fi
}

# Returns 0 when the Kindle woke before the alarm: the power button
rtc_sleep() {
  duration=$1
  went_to_sleep=$(date +%s)

  if [ "$DEBUG" = true ]; then
    sleep "$duration"
  else
    # shellcheck disable=SC2039
    [ "$(cat "$RTC")" -eq 0 ] && echo -n "$duration" >"$RTC"
    echo "mem" >/sys/power/state
  fi

  slept=$(($(date +%s) - went_to_sleep))
  [ "$slept" -lt $((duration - MANUAL_WAKE_TOLERANCE)) ]
}

main_loop() {
  window=$AWAKE_SECONDS
  while true; do
    log_battery_stats

    next_wakeup_secs=$("$DIR/next-wakeup" --schedule="$REFRESH_SCHEDULE" --timezone="$TIMEZONE")

    if [ "$next_wakeup_secs" -gt "$SLEEP_SCREEN_INTERVAL" ]; then
      action="sleep"
      prepare_sleep
    else
      action="suspend"
      refresh_dashboard
    fi

    # take a bit of time before going to sleep, so this process can be
    # aborted; keys are read meanwhile
    awake_window "$window"

    # The window may have lasted long: count from now
    next_wakeup_secs=$("$DIR/next-wakeup" --schedule="$REFRESH_SCHEDULE" --timezone="$TIMEZONE")
    echo "Going to $action, next wakeup in ${next_wakeup_secs}s"

    if rtc_sleep "$next_wakeup_secs"; then
      echo "Woken up by the power button"
      window=$BUTTON_WINDOW_SECONDS
    else
      window=$AWAKE_SECONDS
    fi
  done
}

init
main_loop
