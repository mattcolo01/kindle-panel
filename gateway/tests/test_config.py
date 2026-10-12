from pathlib import Path

import pytest

from app.config import ConfigError, load_settings, read_secret

EXAMPLE_CONFIG = Path(__file__).parent.parent / "config.example.yaml"


def env_for(config_file, **extra):
    return {"CONFIG_FILE": str(config_file), "HA_TOKEN": "ha", "KINDLE_TOKEN": "kindle", **extra}


def test_example_config_loads():
    settings = load_settings(env_for(EXAMPLE_CONFIG))
    assert settings.title == "Casa"
    assert str(settings.timezone) == "Europe/Rome"
    assert settings.ha_url == "http://homeassistant:8123"
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
