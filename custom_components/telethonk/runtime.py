"""Runtime orchestration for the Telethonk receptionist."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from twilio.rest import Client

from .const import (
    ACTION_ACCEPT_PREFIX,
    ACTION_DENY_PREFIX,
    CONF_ACCOUNT_SID,
    CONF_AUTH_TOKEN,
    CONF_BUZZER_NUMBER,
    CONF_DID,
    CONF_FALLBACK_NUMBERS,
    CONF_NOTIFICATION_RECIPIENTS,
    CONF_RESPONSE_TIMEOUT,
    CONF_RETENTION_DAYS,
    CONF_SHOW_SIDEBAR,
    CONF_UNLOCK_DIGITS,
    CONF_UNLOCK_SCRIPT,
    CONF_WEBHOOK_ID,
    DEFAULT_RESPONSE_TIMEOUT,
    DEFAULT_RETENTION_DAYS,
    DEFAULT_SHOW_SIDEBAR,
    DEFAULT_UNLOCK_DIGITS,
    DOMAIN,
    EVENT_INTERACTION,
    EVENT_NOTIFICATION_ACTION,
    EVENT_UPDATED,
)
from .models import ActiveCall
from .storage import ReceptionistStore
from .twiml import dial_numbers, hangup, play_digits, response, say

_LOGGER = logging.getLogger(__name__)


class TelethonkRuntime:
    """Coordinate one configured receptionist/DID."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.store = ReceptionistStore(
            hass,
            entry.entry_id,
            int(self.option(CONF_RETENTION_DAYS, DEFAULT_RETENTION_DAYS)),
        )
        self.active_calls: dict[str, ActiveCall] = {}
        self._remove_action_listener: Callable[[], None] | None = None
        self._decision_lock = asyncio.Lock()

    async def async_setup(self) -> None:
        """Load state and begin listening for actionable notifications."""
        await self.store.async_load()
        self._remove_action_listener = self.hass.bus.async_listen(
            EVENT_NOTIFICATION_ACTION, self._async_handle_notification_action
        )

    async def async_unload(self) -> None:
        """Stop runtime listeners."""
        if self._remove_action_listener:
            self._remove_action_listener()
            self._remove_action_listener = None
        self.active_calls.clear()

    def option(self, key: str, default: Any = None) -> Any:
        """Return an option, falling back to immutable config-entry data."""
        return self.entry.options.get(key, self.entry.data.get(key, default))

    @property
    def webhook_id(self) -> str:
        """Return the private Home Assistant webhook ID."""
        return str(self.entry.data[CONF_WEBHOOK_ID])

    @property
    def webhook_url(self) -> str:
        """Return the externally reachable webhook URL."""
        return webhook.async_generate_url(
            self.hass, self.webhook_id, prefer_external=True
        )

    def webhook_url_for(self, stage: str) -> str:
        """Return an absolute webhook stage URL."""
        return f"{self.webhook_url}?stage={stage}"

    async def async_set_auto_unlock(self, enabled: bool) -> None:
        """Change and persist auto-unlock."""
        await self.store.async_set_auto_unlock(enabled)
        async_dispatcher_send(self.hass, f"{DOMAIN}_{self.entry.entry_id}_auto_unlock")
        self.async_signal_updated()

    async def async_record(
        self,
        *,
        interaction_id: str,
        kind: str,
        from_number: str,
        to_number: str,
        call_sid: str | None = None,
        transcript: str | None = None,
        status: str,
        action: str | None = None,
        detail: str | None = None,
    ) -> dict[str, Any]:
        """Record an auditable receptionist interaction."""
        item: dict[str, Any] = {
            "id": interaction_id,
            "profile": self.entry.title,
            "kind": kind,
            "created_at": datetime.now(UTC).isoformat(),
            "from": from_number,
            "to": to_number,
            "status": status,
        }
        if call_sid:
            item["call_sid"] = call_sid
        if transcript:
            item["transcript"] = transcript
        if action:
            item["action"] = action
        if detail:
            item["detail"] = detail
        await self.store.async_add_interaction(item)
        self.hass.bus.async_fire(EVENT_INTERACTION, dict(item))
        self.async_signal_updated()
        return item

    async def async_update_interaction(
        self, interaction_id: str, **changes: Any
    ) -> None:
        """Update a journal entry and notify the panel."""
        changes["updated_at"] = datetime.now(UTC).isoformat()
        await self.store.async_update_interaction(interaction_id, changes)
        self.async_signal_updated()

    async def async_begin_decision(
        self,
        *,
        call_sid: str,
        interaction_id: str,
        from_number: str,
        to_number: str,
        transcript: str,
    ) -> None:
        """Notify residents and track the decision window."""
        self._expire_active_calls()
        timeout = int(self.option(CONF_RESPONSE_TIMEOUT, DEFAULT_RESPONSE_TIMEOUT))
        active = ActiveCall(
            call_sid=call_sid,
            interaction_id=interaction_id,
            from_number=from_number,
            to_number=to_number,
            transcript=transcript,
            deadline=datetime.now(UTC) + timedelta(seconds=timeout),
        )
        self.active_calls[call_sid] = active
        await self.async_update_interaction(
            interaction_id, status="awaiting_decision", transcript=transcript
        )

        accept_id = f"{ACTION_ACCEPT_PREFIX}{self.entry.entry_id}:{interaction_id}"
        deny_id = f"{ACTION_DENY_PREFIX}{self.entry.entry_id}:{interaction_id}"
        data = {
            "actions": [
                {"action": accept_id, "title": "Accept"},
                {"action": deny_id, "title": "Deny", "destructive": True},
            ],
            "tag": f"telethonk-{interaction_id}",
            "group": "telethonk-receptionist",
            "ttl": timeout,
            "priority": "high",
        }
        message = transcript or "Someone is at the door."
        for recipient in self.notification_recipients:
            try:
                await self.hass.services.async_call(
                    "notify",
                    recipient,
                    {
                        "title": "Receptionist",
                        "message": message,
                        "data": data,
                    },
                    blocking=False,
                )
            except HomeAssistantError as err:
                _LOGGER.warning("Unable to notify %s: %s", recipient, err)

    async def async_timeout_call(self, call_sid: str) -> bool:
        """Resolve an undecided call as timed out."""
        async with self._decision_lock:
            active = self.active_calls.get(call_sid)
            if active is None or active.resolved:
                return False
            active.resolved = True
            active.resolution = "fallback"
            await self.async_update_interaction(
                active.interaction_id,
                status="fallback",
                action="bridged_after_timeout",
            )
            return True

    async def async_run_unlock(self, context: dict[str, Any]) -> str:
        """Run the configured unlock implementation and return its audit label."""
        script = str(self.option(CONF_UNLOCK_SCRIPT, "") or "").strip()
        if script:
            await self.hass.services.async_call(
                "script",
                "turn_on",
                {
                    CONF_ENTITY_ID: script,
                    "variables": context,
                },
                blocking=True,
            )
            return f"script:{script}"
        return "twilio_dtmf"

    async def async_update_live_call(self, call_sid: str, twiml: str) -> None:
        """Replace the instructions for an in-progress Twilio call."""
        account_sid = str(self.entry.data[CONF_ACCOUNT_SID])
        auth_token = str(self.entry.data[CONF_AUTH_TOKEN])

        def _update() -> None:
            Client(account_sid, auth_token).calls(call_sid).update(twiml=twiml)

        await self.hass.async_add_executor_job(_update)

    def unlock_twiml(self, message: str = "Access granted.") -> str:
        """Return default DTMF unlock TwiML."""
        digits = str(self.option(CONF_UNLOCK_DIGITS, DEFAULT_UNLOCK_DIGITS))
        return response(say(message), play_digits(digits), hangup())

    def fallback_twiml(self) -> str:
        """Return the fallback bridge response."""
        if not self.fallback_numbers:
            return response(
                say("No receptionist is available. Please try again later."),
                hangup(),
            )
        return response(
            say("Please wait while we connect your call."),
            dial_numbers(self.fallback_numbers),
        )

    @property
    def notification_recipients(self) -> list[str]:
        """Return configured mobile notification service names."""
        return _split_values(self.option(CONF_NOTIFICATION_RECIPIENTS, ""))

    @property
    def fallback_numbers(self) -> list[str]:
        """Return configured simultaneous fallback destinations."""
        return _split_values(self.option(CONF_FALLBACK_NUMBERS, ""))

    def overview(self) -> dict[str, Any]:
        """Return admin-facing summary data."""
        self._expire_active_calls()
        return {
            "entry_id": self.entry.entry_id,
            "title": self.entry.title,
            "did": _mask_number(str(self.entry.data[CONF_DID])),
            "buzzer_number": _mask_number(str(self.entry.data[CONF_BUZZER_NUMBER])),
            "auto_unlock": self.store.state.auto_unlock,
            "webhook_url": self.webhook_url,
            "notification_recipients": self.notification_recipients,
            "fallback_numbers": [
                _mask_number(number) for number in self.fallback_numbers
            ],
            "response_timeout": int(
                self.option(CONF_RESPONSE_TIMEOUT, DEFAULT_RESPONSE_TIMEOUT)
            ),
            "show_sidebar": bool(self.option(CONF_SHOW_SIDEBAR, DEFAULT_SHOW_SIDEBAR)),
            "active_calls": len(
                [call for call in self.active_calls.values() if not call.resolved]
            ),
        }

    @callback
    def async_signal_updated(self) -> None:
        """Notify frontend clients that runtime state changed."""
        self.hass.bus.async_fire(EVENT_UPDATED, {"entry_id": self.entry.entry_id})

    @callback
    def _async_handle_notification_action(self, event: Event) -> None:
        action = str(event.data.get("action", ""))
        accepted: bool | None = None
        prefix = ""
        if action.startswith(ACTION_ACCEPT_PREFIX):
            accepted = True
            prefix = ACTION_ACCEPT_PREFIX
        elif action.startswith(ACTION_DENY_PREFIX):
            accepted = False
            prefix = ACTION_DENY_PREFIX
        if accepted is None:
            return
        try:
            entry_id, interaction_id = action.removeprefix(prefix).split(":", 1)
        except ValueError:
            return
        if entry_id != self.entry.entry_id:
            return
        self.hass.async_create_task(
            self._async_resolve_action(interaction_id, accepted),
            f"Resolve Telethonk action {interaction_id}",
        )

    async def _async_resolve_action(self, interaction_id: str, accepted: bool) -> None:
        async with self._decision_lock:
            active = next(
                (
                    call
                    for call in self.active_calls.values()
                    if call.interaction_id == interaction_id
                ),
                None,
            )
            if active is None or active.resolved or datetime.now(UTC) > active.deadline:
                await self.async_update_interaction(
                    interaction_id,
                    detail="Ignored a late or duplicate notification response.",
                )
                return

            if accepted:
                try:
                    action = await self.async_run_unlock(
                        {
                            "call_sid": active.call_sid,
                            "interaction_id": interaction_id,
                            "from_number": active.from_number,
                            "to_number": active.to_number,
                            "transcript": active.transcript,
                        }
                    )
                    twiml = (
                        response(say("Access has been granted."), hangup())
                        if action.startswith("script:")
                        else self.unlock_twiml()
                    )
                    await self.async_update_live_call(active.call_sid, twiml)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.exception("Unable to accept receptionist call")
                    active.resolved = True
                    active.resolution = "fallback"
                    await self.async_update_interaction(
                        interaction_id,
                        status="fallback",
                        action="unlock_error_bridge",
                        detail=str(err),
                    )
                    try:
                        await self.async_update_live_call(
                            active.call_sid, self.fallback_twiml()
                        )
                    except Exception:  # noqa: BLE001
                        _LOGGER.exception(
                            "Unable to move failed unlock call to fallback"
                        )
                    return
                active.resolved = True
                active.resolution = "accepted"
                await self.async_update_interaction(
                    interaction_id, status="accepted", action=action
                )
            else:
                await self.async_update_live_call(
                    active.call_sid,
                    response(say("We cannot grant access at this time."), hangup()),
                )
                active.resolved = True
                active.resolution = "denied"
                await self.async_update_interaction(
                    interaction_id, status="denied", action="notification_denied"
                )

    def _expire_active_calls(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(minutes=10)
        self.active_calls = {
            sid: call
            for sid, call in self.active_calls.items()
            if call.deadline >= cutoff
        }


def _split_values(value: Any) -> list[str]:
    """Split comma/newline-delimited option values."""
    return [
        item.strip().removeprefix("notify.")
        for item in re.split(r"[,\n]", str(value or ""))
        if item.strip()
    ]


def _mask_number(number: str) -> str:
    """Mask a phone number while retaining a useful suffix."""
    return f"{'*' * max(0, len(number) - 4)}{number[-4:]}"
