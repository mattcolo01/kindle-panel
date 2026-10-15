from pathlib import Path

import pytest

from app.config import ConfigError, load_settings, read_secret

EXAMPLE_CONFIG = Path(__file__).parent.parent / "config.example.yaml"


def env_for(config_file, **extra):
    return {"CONFIG_FILE": str(config_file), "HA_TOKEN": "ha", "KINDLE_TOKEN": "kindle", **extra}


def test_example_config_loads_in_dashboard_mode():
    settings = load_settings(env_for(EXAMPLE_CONFIG))
    assert settings.dashboard == "dashboard-kindle"
    assert settings.language == "it"
    assert settings.rows == ()
    assert str(settings.timezone) == "Europe/Rome"
    assert settings.ha_url == "http://homeassistant:8123"


def test_example_rows_alternative_loads(tmp_path):
    # The commented rows block of the example, uncommented, instead of dashboard
    lines = []
    for line in EXAMPLE_CONFIG.read_text().splitlines():
        if line.startswith(("dashboard:", "language:")):
            continue
        lines.append(line[2:] if line.startswith(("# title:", "# rows:", "#   ")) else line)
    config = tmp_path / "config.yaml"
    config.write_text("\n".join(lines))
    settings = load_settings(env_for(config))
    assert settings.dashboard is None
    assert settings.title == "Casa"
    assert [r.entity for r in settings.rows] == [
        "sensor.temperatura_soggiorno",
        "sensor.umidita_soggiorno",
        "weather.casa",
    ]
    assert [r.label for r in settings.rows] == ["Soggiorno", "Umidità", "Meteo"]


def test_secret_from_env_and_from_file(tmp_path):
    assert read_secret("HA_TOKEN", {"HA_TOKEN": "abc"}) == "abc"
    secret = tmp_path / "token"
    secret.write_text("from-file\n")
    assert read_secret("HA_TOKEN", {"HA_TOKEN_FILE": str(secret)}) == "from-file"


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"HA_TOKEN": ""},
        {"HA_TOKEN": "a", "HA_TOKEN_FILE": "/x"},
        {"HA_TOKEN_FILE": "/does/not/exist"},
    ],
)
def test_secret_errors(env):
    with pytest.raises(ConfigError):
        read_secret("HA_TOKEN", env)


def test_both_secrets_required():
    with pytest.raises(ConfigError, match="KINDLE_TOKEN"):
        load_settings({"CONFIG_FILE": str(EXAMPLE_CONFIG), "HA_TOKEN": "ha"})


@pytest.mark.parametrize(
    "yaml_text, message",
    [
        ("[]", "mapping"),
        ("timezone: Europe/Rome\nha_url: http://h\nrows: []", "rows"),
        ("timezone: Nowhere/City\nha_url: http://h\nrows: [{entity: sensor.a}]", "timezone"),
        ("timezone: Europe/Rome\nha_url: ftp://h\nrows: [{entity: sensor.a}]", "ha_url"),
        ("timezone: Europe/Rome\nha_url: http://h\nrows: [{entity: ../api/config}]", "entity"),
        ("timezone: Europe/Rome\nha_url: http://h\nrows: [{entity: sensor.a/b}]", "entity"),
        ("timezone: Europe/Rome\nha_url: http://h", "exactly one"),
        ("timezone: Europe/Rome\nha_url: http://h\nrows: [{entity: sensor.a}]\ndashboard: d-k", "exactly one"),
        ("timezone: Europe/Rome\nha_url: http://h\ndashboard: ''", "dashboard"),
        ("timezone: Europe/Rome\nha_url: http://h\ndashboard: dashboard kindle", "dashboard"),
        ("timezone: Europe/Rome\nha_url: http://h\ndashboard: ../config", "dashboard"),
        ("timezone: Europe/Rome\nha_url: http://h\ndashboard: /dashboard-kindle", "dashboard"),
        ("timezone: Europe/Rome\nha_url: http://h\ndashboard: [a]", "dashboard"),
        ("timezone: Europe/Rome\nha_url: http://h\ndashboard: d-k\nlanguage: de", "language"),
    ],
)
def test_invalid_config(tmp_path, yaml_text, message):
    config = tmp_path / "config.yaml"
    config.write_text(yaml_text)
    with pytest.raises(ConfigError, match=message):
        load_settings(env_for(config))


def test_label_defaults_to_entity_id(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("timezone: Europe/Rome\nha_url: http://h/\nrows: [{entity: sensor.a}]")
    settings = load_settings(env_for(config))
    assert settings.rows[0].label == "sensor.a"
    assert settings.ha_url == "http://h"


@pytest.mark.parametrize("url_path", ["dashboard-kindle", "Dashboard-Kindle", "lovelace", "map", "my_dash-1"])
def test_dashboard_url_paths_accepted_by_ha(tmp_path, url_path):
    config = tmp_path / "config.yaml"
    config.write_text(f"timezone: Europe/Rome\nha_url: http://h\ndashboard: {url_path}")
    assert load_settings(env_for(config)).dashboard == url_path
