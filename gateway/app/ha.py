"""Minimal Home Assistant client: only GET {ha_url}/api/states/<entity_id>."""

import asyncio
import logging
from collections.abc import Iterable

import httpx

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5.0


class HAUnavailable(Exception):
    """No request reached Home Assistant successfully."""


class HAClient:
    def __init__(self, ha_url: str, token: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=ha_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT_SECONDS,
            # HA lives on the LAN: never route the token through a proxy
            # picked up from the environment.
            trust_env=False,
            follow_redirects=False,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get_state(self, entity_id: str) -> tuple[bool, dict | None]:
        """Return (reached_ha, state). state is None if missing or in error."""
        try:
            response = await self._client.get(f"/api/states/{entity_id}")
        except httpx.HTTPError as e:
            log.warning("HA request for %s failed: %s", entity_id, type(e).__name__)
            return False, None

        if response.status_code == 404:
            log.warning("HA entity not found: %s", entity_id)
            return True, None
        if response.status_code != 200:
            log.warning("HA returned %d for %s", response.status_code, entity_id)
            return False, None

        try:
            state = response.json()
        except ValueError:
            state = None
        if not isinstance(state, dict) or not isinstance(state.get("state"), str):
            log.warning("HA returned an invalid state for %s", entity_id)
            return True, None
        return True, state

    async def get_states(self, entity_ids: Iterable[str]) -> dict[str, dict | None]:
        """Fetch the given entities; None marks a missing or broken entity.

        Raises HAUnavailable when HA could not be reached at all (connection
        errors, timeouts, rejected token or server errors for every entity).
        """
        ids = list(dict.fromkeys(entity_ids))
        results = await asyncio.gather(*(self._get_state(i) for i in ids))
        if not any(reached for reached, _ in results):
            raise HAUnavailable()
        return {i: state for i, (_, state) in zip(ids, results)}
