"""Persistent storage for Telethonk."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, MAX_INTERACTIONS, STORAGE_VERSION
from .models import ReceptionistState


class ReceptionistStore:
    """Store the auto-unlock state and receptionist interaction journal."""

    def __init__(self, hass: HomeAssistant, entry_id: str, retention_days: int) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}"
        )
        self._retention_days = retention_days
        self.state = ReceptionistState()

    async def async_load(self) -> None:
        """Load persisted state, failing safely with auto-unlock disabled."""
        data = await self._store.async_load()
        if not isinstance(data, dict):
            return
        interactions = data.get("interactions")
        if isinstance(interactions, list):
            self.state.interactions = [
                item for item in interactions if isinstance(item, dict)
            ]
            self._prune()
        self.state.auto_unlock = data.get("auto_unlock") is True

    async def async_set_auto_unlock(self, enabled: bool) -> None:
        """Persist the auto-unlock state."""
        self.state.auto_unlock = enabled
        await self._save()

    async def async_add_interaction(self, item: dict[str, Any]) -> None:
        """Append an interaction to the bounded journal."""
        self.state.interactions.insert(0, item)
        self._prune()
        await self._save()

    async def async_update_interaction(
        self, interaction_id: str, changes: dict[str, Any]
    ) -> None:
        """Update an existing interaction."""
        for item in self.state.interactions:
            if item.get("id") == interaction_id:
                item.update(changes)
                break
        self._prune()
        await self._save()

    def interactions(self) -> list[dict[str, Any]]:
        """Return a copy of the newest-first interaction journal."""
        self._prune()
        return [dict(item) for item in self.state.interactions]

    def _prune(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(days=self._retention_days)
        retained: list[dict[str, Any]] = []
        for item in self.state.interactions:
            try:
                created_at = datetime.fromisoformat(str(item["created_at"]))
            except KeyError, TypeError, ValueError:
                continue
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            if created_at >= cutoff:
                retained.append(item)
        self.state.interactions = retained[:MAX_INTERACTIONS]

    async def _save(self) -> None:
        await self._store.async_save(
            {
                "auto_unlock": self.state.auto_unlock,
                "interactions": self.state.interactions,
            }
        )
