import logging

from app.config import Settings
from app.main import APP_LOGGER, create_app


def test_app_info_messages_reach_a_handler(settings: Settings) -> None:
    create_app(settings)
    logger = logging.getLogger(f"{APP_LOGGER}.dashboard")
    assert logger.isEnabledFor(logging.INFO)
    assert logging.getLogger(APP_LOGGER).handlers


def test_create_app_twice_adds_one_handler(settings: Settings) -> None:
    create_app(settings)
    create_app(settings)
    assert len(logging.getLogger(APP_LOGGER).handlers) == 1
