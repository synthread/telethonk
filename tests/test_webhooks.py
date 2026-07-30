"""Tests for voice webhook routing."""

from types import SimpleNamespace

import pytest

from custom_components.telethonk.const import (
    CONF_BUZZER_NUMBER,
    CONF_DID,
    CONF_SPEECH_PROMPT,
)
from custom_components.telethonk.webhooks import _async_handle_voice


class FakeRuntime:
    """Minimal runtime used to exercise TwiML routing."""

    def __init__(self) -> None:
        self.entry = SimpleNamespace(
            data={
                CONF_DID: "+16045550100",
                CONF_BUZZER_NUMBER: "+16045550200",
            }
        )
        self.store = SimpleNamespace(state=SimpleNamespace(auto_unlock=False))
        self.active_calls = {}
        self.updated: list[tuple[str, dict]] = []

    async def async_record(self, **kwargs):
        """Record test data and echo an item."""
        self.updated.append(("record", kwargs))
        return kwargs

    async def async_update_interaction(self, interaction_id, **changes):
        """Capture an update."""
        self.updated.append((interaction_id, changes))

    async def async_begin_decision(self, **kwargs):
        """Capture decision creation."""
        self.updated.append(("decision", kwargs))

    async def async_timeout_call(self, call_sid):
        """Report an unresolved call."""
        return True

    def option(self, key, default=None):
        """Return deterministic options."""
        if key == CONF_SPEECH_PROMPT:
            return "Who is at the door?"
        return default

    def webhook_url_for(self, stage):
        """Return an absolute stage URL."""
        return f"https://ha.example/api/webhook/private?stage={stage}"

    def fallback_twiml(self):
        """Return recognizable fallback TwiML."""
        return "<Response><Dial>fallback</Dial></Response>"


@pytest.mark.asyncio
async def test_unknown_caller_uses_general_fallback() -> None:
    """Non-buzzer callers bypass the door workflow."""
    runtime = FakeRuntime()
    request = SimpleNamespace(query={})
    result = await _async_handle_voice(
        runtime,
        request,
        {
            "CallSid": "CA123",
            "Direction": "inbound",
            "From": "+16045550999",
            "To": "+16045550100",
        },
    )
    assert "<Dial>fallback</Dial>" in result
    assert runtime.updated[0][1]["action"] == "unknown_caller_bridge"


@pytest.mark.asyncio
async def test_buzzer_call_gathers_speech() -> None:
    """A buzzer call asks for speech while auto-unlock is disabled."""
    runtime = FakeRuntime()
    request = SimpleNamespace(query={})
    result = await _async_handle_voice(
        runtime,
        request,
        {
            "CallSid": "CA123",
            "Direction": "inbound",
            "From": "+16045550200",
            "To": "+16045550100",
        },
    )
    assert "<Gather" in result
    assert "Who is at the door?" in result
    assert "stage=speech" in result


@pytest.mark.asyncio
async def test_timeout_after_restart_still_bridges() -> None:
    """Missing in-memory call state fails safely to the bridge after restart."""
    runtime = FakeRuntime()
    request = SimpleNamespace(
        query={"stage": "timeout", "interaction_id": "interaction"}
    )
    result = await _async_handle_voice(
        runtime,
        request,
        {
            "CallSid": "CA123",
            "Direction": "inbound",
            "From": "+16045550200",
            "To": "+16045550100",
        },
    )
    assert "<Dial>fallback</Dial>" in result
    assert runtime.updated[-1][1]["action"] == "bridged_after_restart"
