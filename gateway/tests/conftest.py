from zoneinfo import ZoneInfo

import pytest
import respx
from fastapi.testclient import TestClient

from app.config import Row, Settings
from app.main import create_app

HA_URL = "http://ha.test:8123"
KINDLE_TOKEN = "kindle-secret-token"
HA_TOKEN = "ha-secret-token"

STATES = {
    "sensor.temperatura_soggiorno": {
        "entity_id": "sensor.temperatura_soggiorno",
        "state": "21.47",
        "attributes": {"unit_of_measurement": "°C", "friendly_name": "Temperatura"},
        "last_changed": "2026-10-12T15:40:12.123456+00:00",
        "last_updated": "2026-10-12T15:40:12.123456+00:00",
    },
    "sensor.umidita_soggiorno": {
        "entity_id": "sensor.umidita_soggiorno",
        "state": "45",
        "attributes": {"unit_of_measurement": "%"},
        "last_changed": "2026-10-12T15:42:00+00:00",
        "last_updated": "2026-10-12T15:42:00+00:00",
    },
    "weather.casa": {
        "entity_id": "weather.casa",
        "state": "cloudy",
        "attributes": {"temperature": 18.25, "temperature_unit": "°C"},
        "last_changed": "2026-10-12T12:00:00+00:00",
        "last_updated": "2026-10-12T15:00:00+00:00",
    },
}


@pytest.fixture
def settings() -> Settings:
    return Settings(
        title="Casa",
        timezone=ZoneInfo("Europe/Rome"),
        ha_url=HA_URL,
        rows=(
            Row("sensor.temperatura_soggiorno", "Soggiorno"),
            Row("sensor.umidita_soggiorno", "Umidità"),
            Row("weather.casa", "Meteo"),
        ),
        ha_token=HA_TOKEN,
        kindle_token=KINDLE_TOKEN,
    )


@pytest.fixture
def ha():
    """Mocked Home Assistant; every entity in STATES exists by default."""
    with respx.mock(base_url=HA_URL, assert_all_called=False) as mock:
        for entity_id, state in STATES.items():
            mock.get(f"/api/states/{entity_id}", name=entity_id).respond(json=state)
        yield mock


@pytest.fixture
def client(settings, ha):
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {KINDLE_TOKEN}"}
