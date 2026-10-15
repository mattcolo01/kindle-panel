"""Load config.yaml and secrets (from env or file)."""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from .i18n import LANGUAGES

DEFAULT_CONFIG_FILE = "/config/config.yaml"
DEFAULT_LANGUAGE = "it"

# Entity ids are interpolated into the HA URL path, so only accept the
# canonical "<domain>.<object_id>" form.
ENTITY_ID_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")

# Dashboard URL path, as in the browser address bar (/dashboard-kindle). The
# characters the HA dashboard dialog accepts (a-zA-Z0-9_-, see
# dialog-lovelace-dashboard-detail.ts), single words included ("lovelace").
DASHBOARD_RE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Row:
    entity: str
    label: str


@dataclass(frozen=True)
class Settings:
    title: str
    timezone: ZoneInfo
    ha_url: str
    rows: tuple[Row, ...]  # empty in dashboard mode
    ha_token: str
    kindle_token: str
    dashboard: str | None = None  # url_path; None in rows mode
    language: str = DEFAULT_LANGUAGE


def read_secret(name: str, env: dict[str, str]) -> str:
    """Read NAME from the environment, or from the file named by NAME_FILE."""
    value = env.get(name)
    file_name = env.get(f"{name}_FILE")
    if value and file_name:
        raise ConfigError(f"Set only one of {name} and {name}_FILE")
    if file_name:
        try:
            value = Path(file_name).read_text(encoding="utf-8")
        except OSError as e:
            raise ConfigError(f"Cannot read {name}_FILE ({file_name}): {e}") from e
    value = (value or "").strip()
    if not value:
        raise ConfigError(f"Missing secret: set {name} or {name}_FILE")
    return value


def parse_rows(raw_rows: object) -> tuple[Row, ...]:
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ConfigError("rows must be a non-empty list")
    rows = []
    for i, raw in enumerate(raw_rows):
        if not isinstance(raw, dict):
            raise ConfigError(f"rows[{i}] must be a mapping")
        entity = raw.get("entity")
        if not isinstance(entity, str) or not ENTITY_ID_RE.match(entity):
            raise ConfigError(f"rows[{i}].entity is not a valid entity id: {entity!r}")
        label = raw.get("label", entity)
        if not isinstance(label, str):
            raise ConfigError(f"rows[{i}].label must be a string")
        rows.append(Row(entity=entity, label=label))
    return tuple(rows)


def parse_config(data: object) -> dict:
    """Validate config.yaml; return the Settings fields other than the secrets."""
    if not isinstance(data, dict):
        raise ConfigError("config.yaml must be a mapping")

    title = data.get("title", "")
    if not isinstance(title, str):
        raise ConfigError("title must be a string")

    tz_name = data.get("timezone")
    if not isinstance(tz_name, str) or not tz_name:
        raise ConfigError("timezone is required")
    try:
        timezone = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise ConfigError(f"Unknown timezone: {tz_name}") from e

    ha_url = data.get("ha_url")
    if not isinstance(ha_url, str) or not re.match(r"^https?://", ha_url):
        raise ConfigError("ha_url must be an http:// or https:// URL")

    if ("rows" in data) == ("dashboard" in data):
        raise ConfigError("Set exactly one of rows (entity list) and dashboard (HA dashboard URL path)")
    rows: tuple[Row, ...] = ()
    dashboard = None
    if "rows" in data:
        rows = parse_rows(data["rows"])
    else:
        dashboard = data["dashboard"]
        if not isinstance(dashboard, str) or not DASHBOARD_RE.match(dashboard):
            raise ConfigError(
                f"dashboard must be the dashboard URL path, e.g. dashboard-kindle: {dashboard!r}"
            )

    language = data.get("language", DEFAULT_LANGUAGE)
    if language not in LANGUAGES:
        raise ConfigError(f"language must be one of {', '.join(LANGUAGES)}: {language!r}")

    return {
        "title": title,
        "timezone": timezone,
        "ha_url": ha_url.rstrip("/"),
        "rows": rows,
        "dashboard": dashboard,
        "language": language,
    }


def load_settings(env: dict[str, str] | None = None) -> Settings:
    env = dict(os.environ) if env is None else env
    config_file = env.get("CONFIG_FILE", DEFAULT_CONFIG_FILE)
    try:
        with open(config_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except OSError as e:
        raise ConfigError(f"Cannot read config file {config_file}: {e}") from e

    return Settings(
        **parse_config(data),
        ha_token=read_secret("HA_TOKEN", env),
        kindle_token=read_secret("KINDLE_TOKEN", env),
    )
