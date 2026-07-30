"""Telethonk Receptionist integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .panel import (
    DATA_RUNTIMES,
    async_refresh_panel,
    async_setup_panel_support,
)
from .runtime import TelethonkRuntime
from .webhooks import async_register_webhook, async_unregister_webhook

type TelethonkConfigEntry = ConfigEntry[TelethonkRuntime]


async def async_setup_entry(hass: HomeAssistant, entry: TelethonkConfigEntry) -> bool:
    """Set up a Telethonk config entry."""
    runtime = TelethonkRuntime(hass, entry)
    await runtime.async_setup()
    entry.runtime_data = runtime

    domain_data = hass.data.setdefault(DOMAIN, {})
    runtimes: dict[str, TelethonkRuntime] = domain_data.setdefault(DATA_RUNTIMES, {})
    runtimes[entry.entry_id] = runtime

    await async_register_webhook(hass, entry, runtime)
    await async_setup_panel_support(hass)
    await async_refresh_panel(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TelethonkConfigEntry) -> bool:
    """Unload a Telethonk config entry."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    runtime = entry.runtime_data
    async_unregister_webhook(hass, runtime)
    await runtime.async_unload()
    hass.data[DOMAIN][DATA_RUNTIMES].pop(entry.entry_id, None)
    await async_refresh_panel(hass)
    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: TelethonkConfigEntry
) -> None:
    """Reload after config-entry options change."""
    await hass.config_entries.async_reload(entry.entry_id)
