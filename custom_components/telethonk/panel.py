"""Admin-only Receptionist sidebar panel."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback

from .const import (
    CONF_SHOW_SIDEBAR,
    DEFAULT_SHOW_SIDEBAR,
    DOMAIN,
    PANEL_ICON,
    PANEL_MODULE_URL,
    PANEL_STATIC_URL,
    PANEL_TITLE,
    PANEL_URL,
)
from .runtime import TelethonkRuntime

DATA_RUNTIMES = "runtimes"
DATA_PANEL_REGISTERED = "panel_registered"
DATA_STATIC_REGISTERED = "static_registered"
DATA_WS_REGISTERED = "ws_registered"


async def async_setup_panel_support(hass: HomeAssistant) -> None:
    """Register the static frontend and websocket commands once."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get(DATA_STATIC_REGISTERED):
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    PANEL_STATIC_URL,
                    str(Path(__file__).parent / "frontend"),
                    False,
                )
            ]
        )
        domain_data[DATA_STATIC_REGISTERED] = True
    if not domain_data.get(DATA_WS_REGISTERED):
        websocket_api.async_register_command(hass, websocket_overview)
        websocket_api.async_register_command(hass, websocket_interactions)
        websocket_api.async_register_command(hass, websocket_set_auto_unlock)
        domain_data[DATA_WS_REGISTERED] = True


async def async_refresh_panel(hass: HomeAssistant) -> None:
    """Register or remove the panel according to loaded entry options."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    runtimes: dict[str, TelethonkRuntime] = domain_data.setdefault(DATA_RUNTIMES, {})
    should_show = any(
        bool(runtime.option(CONF_SHOW_SIDEBAR, DEFAULT_SHOW_SIDEBAR))
        for runtime in runtimes.values()
    )
    registered = bool(domain_data.get(DATA_PANEL_REGISTERED))
    if should_show and not registered:
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL,
            webcomponent_name="telethonk-panel",
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            module_url=PANEL_MODULE_URL,
            require_admin=True,
            config={"domain": DOMAIN},
        )
        domain_data[DATA_PANEL_REGISTERED] = True
    elif not should_show and registered:
        frontend.async_remove_panel(hass, PANEL_URL, warn_if_unknown=False)
        domain_data[DATA_PANEL_REGISTERED] = False


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/overview"})
@websocket_api.require_admin
@callback
def websocket_overview(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return all loaded receptionist profiles."""
    runtimes = hass.data.get(DOMAIN, {}).get(DATA_RUNTIMES, {})
    connection.send_result(
        msg["id"],
        {"profiles": [runtime.overview() for runtime in runtimes.values()]},
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/interactions",
        vol.Optional("entry_id"): str,
        vol.Optional("limit", default=100): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=500)
        ),
    }
)
@websocket_api.require_admin
@callback
def websocket_interactions(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return newest-first journal entries."""
    runtimes: dict[str, TelethonkRuntime] = hass.data.get(DOMAIN, {}).get(
        DATA_RUNTIMES, {}
    )
    entry_id = msg.get("entry_id")
    selected = (
        [runtimes[entry_id]]
        if entry_id and entry_id in runtimes
        else list(runtimes.values())
    )
    interactions = [
        item for runtime in selected for item in runtime.store.interactions()
    ]
    interactions.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    connection.send_result(msg["id"], interactions[: msg["limit"]])


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/set_auto_unlock",
        vol.Required("entry_id"): str,
        vol.Required("enabled"): bool,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_set_auto_unlock(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Change auto-unlock from the Receptionist panel."""
    runtimes: dict[str, TelethonkRuntime] = hass.data.get(DOMAIN, {}).get(
        DATA_RUNTIMES, {}
    )
    runtime = runtimes.get(msg["entry_id"])
    if runtime is None:
        connection.send_error(msg["id"], "not_found", "Receptionist profile not found")
        return
    await runtime.async_set_auto_unlock(msg["enabled"])
    connection.send_result(msg["id"], {"auto_unlock": msg["enabled"]})
