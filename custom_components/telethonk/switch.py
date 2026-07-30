"""Auto-unlock switch for Telethonk."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .runtime import TelethonkRuntime


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[TelethonkRuntime],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the auto-unlock switch."""
    async_add_entities([AutoUnlockSwitch(entry.runtime_data)])


class AutoUnlockSwitch(SwitchEntity):
    """Control whether recognized buzzer calls unlock immediately."""

    _attr_has_entity_name = True
    _attr_name = "Auto-unlock"
    _attr_icon = "mdi:door-closed-lock"

    def __init__(self, runtime: TelethonkRuntime) -> None:
        """Initialize the integration-owned switch."""
        self.runtime = runtime
        self._attr_unique_id = f"{runtime.entry.entry_id}_auto_unlock"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, runtime.entry.entry_id)},
            manufacturer="Synthread",
            model="Twilio Receptionist",
            name=runtime.entry.title,
        )

    @property
    def is_on(self) -> bool:
        """Return the persisted auto-unlock state."""
        return self.runtime.store.state.auto_unlock

    async def async_added_to_hass(self) -> None:
        """Subscribe to changes made from the Receptionist panel."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_{self.runtime.entry.entry_id}_auto_unlock",
                self._handle_runtime_update,
            )
        )

    @callback
    def _handle_runtime_update(self) -> None:
        """Write runtime changes to the entity state machine."""
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        """Enable automatic unlock."""
        await self.runtime.async_set_auto_unlock(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Disable automatic unlock."""
        await self.runtime.async_set_auto_unlock(False)
        self.async_write_ha_state()
