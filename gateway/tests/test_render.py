from zoneinfo import ZoneInfo

import pytest

from app.config import Row
from app.render import MISSING, View, build_view, format_number, format_state, parse_battery, render
from conftest import STATES

ROME = ZoneInfo("Europe/Rome")
ROWS = (
    Row("sensor.temperatura_soggiorno", "Soggiorno"),
    Row("sensor.umidita_soggiorno", "Umidità"),
    Row("weather.casa", "Meteo"),
)


@pytest.mark.parametrize(
    "value, expected",
    [
        ("21.47", "21.5"),
        ("21.45", "21.5"),  # half up, on the decimal string
        ("21.44", "21.4"),
        ("45", "45.0"),
        ("-0.04", "0.0"),
        ("-3.25", "-3.3"),
        ("1e3", "1000.0"),
        (18.25, "18.3"),
        (7, "7.0"),
        ("on", None),
        ("nan", None),
        ("inf", None),
        ("1_000", None),
        ("", None),
        (True, None),
        (None, None),
    ],
)
def test_format_number(value, expected):
    assert format_number(value) == expected


def test_format_state_numeric_with_unit():
    assert format_state("sensor.temperatura_soggiorno", STATES["sensor.temperatura_soggiorno"]) == "21.5 °C"
    assert format_state("sensor.umidita_soggiorno", STATES["sensor.umidita_soggiorno"]) == "45.0 %"


def test_format_state_non_numeric_is_raw():
    assert format_state("binary_sensor.porta", {"state": "on", "attributes": {}}) == "on"
    assert format_state("sensor.x", {"state": "home"}) == "home"


def test_format_state_weather_shows_condition_and_temperature():
    assert format_state("weather.casa", STATES["weather.casa"]) == "cloudy, 18.3 °C"
    assert format_state("weather.casa", {"state": "sunny", "attributes": {}}) == "sunny"


@pytest.mark.parametrize("state", [None, {"state": "unavailable"}, {"state": "unknown"}])
def test_format_state_missing_or_in_error_is_dash(state):
    assert format_state("sensor.x", state) == MISSING == "—"


def test_missing_entity_appears_as_dash_in_view():
    states = dict(STATES, **{"weather.casa": None})
    view = build_view("Casa", ROWS, states, ROME, None)
    assert view.rows == (("Soggiorno", "21.5 °C"), ("Umidità", "45.0 %"), ("Meteo", "—"))


def test_data_time_is_latest_last_changed_in_timezone():
    view = build_view("Casa", ROWS, STATES, ROME, None)
    # Latest last_changed is 15:42 UTC = 17:42 in Rome (CEST).
    # weather.casa has a later last_updated (15:00) but older last_changed.
    assert view.data_time == "17:42"


def test_data_time_without_data_is_none():
    states = {row.entity: None for row in ROWS}
    assert build_view("Casa", ROWS, states, ROME, None).data_time is None


@pytest.mark.parametrize(
    "header, expected",
    [
        ("0", 0),
        ("2", 0),
        ("3", 5),
        ("84", 85),
        ("86", 85),
        ("87", 85),
        ("88", 90),
        ("100", 100),
        (" 50 ", 50),
        (None, None),
        ("", None),
        ("101", None),
        ("-1", None),
        ("50%", None),
        ("5.5", None),
    ],
)
def test_parse_battery(header, expected):
    assert parse_battery(header) == expected


def test_render_is_deterministic():
    view = build_view("Casa", ROWS, STATES, ROME, 85)
    assert render(view) == render(view)


def test_render_handles_long_text():
    view = build_view("Casa " * 20, ROWS, STATES, ROME, 85)
    long_row = ("Etichetta molto lunga " * 5, "valore lunghissimo " * 5)
    view = View(view.title, view.rows + (long_row,), view.data_time, view.battery)
    assert render(view).startswith(b"\x89PNG")


def test_render_many_rows():
    rows = tuple((f"Riga {i}", f"{i}.0") for i in range(30))
    assert render(View("Casa", rows, None, None)).startswith(b"\x89PNG")
