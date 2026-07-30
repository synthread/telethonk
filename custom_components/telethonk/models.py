"""Runtime models for Telethonk."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class ActiveCall:
    """An inbound call waiting for a receptionist decision."""

    call_sid: str
    interaction_id: str
    from_number: str
    to_number: str
    transcript: str
    deadline: datetime
    resolved: bool = False
    resolution: str | None = None


@dataclass(slots=True)
class ReceptionistState:
    """Persisted integration state."""

    auto_unlock: bool = False
    interactions: list[dict[str, Any]] = field(default_factory=list)
