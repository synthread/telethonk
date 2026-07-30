"""Diagnostics support for Telethonk."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.redact import async_redact_data

from .const import (
    CONF_ACCOUNT_SID,
    CONF_AUTH_TOKEN,
    CONF_BUZZER_NUMBER,
    CONF_DID,
    CONF_FALLBACK_NUMBERS,
    CONF_NOTIFICATION_RECIPIENTS,
    CONF_WEBHOOK_ID,
)
from .runtime import TelethonkRuntime

TO_REDACT = {
    CONF_ACCOUNT_SID,
    CONF_AUTH_TOKEN,
    CONF_BUZZER_NUMBER,
    CONF_DID,
    CONF_FALLBACK_NUMBERS,
    CONF_NOTIFICATION_RECIPIENTS,
    CONF_WEBHOOK_ID,
    "call_sid",
    "from",
    "to",
    "transcript",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry[TelethonkRuntime]
) -> dict[str, Any]:
    """Return privacy-safe diagnostics."""
    runtime = entry.runtime_data
    return async_redact_data(
        {
            "entry": {
                "title": entry.title,
                "data": dict(entry.data),
                "options": dict(entry.options),
            },
            "runtime": {
                "auto_unlock": runtime.store.state.auto_unlock,
                "active_calls": len(runtime.active_calls),
                "interactions": runtime.store.interactions(),
            },
        },
        TO_REDACT,
    )
