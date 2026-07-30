"""Signed Twilio webhook handling for Telethonk."""

from __future__ import annotations

import logging
from uuid import uuid4

from aiohttp import web
from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from twilio.request_validator import RequestValidator

from .const import (
    CONF_AUTH_TOKEN,
    CONF_BUZZER_NUMBER,
    CONF_DID,
    CONF_RESPONSE_TIMEOUT,
    CONF_SMS_ACKNOWLEDGEMENT,
    CONF_SPEECH_PROMPT,
    DEFAULT_RESPONSE_TIMEOUT,
    DEFAULT_SMS_ACKNOWLEDGEMENT,
    DEFAULT_SPEECH_PROMPT,
    DOMAIN,
    EVENT_INBOUND_SMS,
    WEBHOOK_NAME,
)
from .runtime import TelethonkRuntime
from .twiml import gather_speech, hangup, message, response, say, wait_for_decision

_LOGGER = logging.getLogger(__name__)


async def async_register_webhook(
    hass: HomeAssistant, entry: ConfigEntry, runtime: TelethonkRuntime
) -> None:
    """Register a signed Twilio webhook."""

    async def _handle(
        hass: HomeAssistant,
        webhook_id: str,
        request: web.Request,
    ) -> web.Response:
        del hass, webhook_id
        if request.method != "POST":
            raise web.HTTPMethodNotAllowed(request.method, ["POST"])
        form = await request.post()
        signature = request.headers.get("X-Twilio-Signature", "")
        signature_url = runtime.webhook_url
        if request.query_string:
            signature_url = f"{signature_url}?{request.query_string}"
        if not RequestValidator(str(entry.data[CONF_AUTH_TOKEN])).validate(
            signature_url, dict(form), signature
        ):
            _LOGGER.warning("Rejected an invalid Twilio signature")
            raise web.HTTPForbidden(text="Invalid Twilio signature")

        payload = {key: str(value) for key, value in form.items()}
        if payload.get("MessageSid") or payload.get("SmsSid"):
            twiml = await _async_handle_sms(runtime, payload)
        else:
            twiml = await _async_handle_voice(runtime, request, payload)
        return web.Response(text=twiml, content_type="application/xml")

    webhook.async_register(
        hass,
        DOMAIN,
        WEBHOOK_NAME,
        runtime.webhook_id,
        _handle,
        allowed_methods=["POST"],
    )


def async_unregister_webhook(hass: HomeAssistant, runtime: TelethonkRuntime) -> None:
    """Unregister a webhook."""
    webhook.async_unregister(hass, runtime.webhook_id)


async def _async_handle_voice(
    runtime: TelethonkRuntime, request: web.Request, payload: dict[str, str]
) -> str:
    """Route an inbound voice webhook stage."""
    call_sid = payload.get("CallSid", "")
    from_number = payload.get("From", "")
    to_number = payload.get("To", "")
    if not call_sid:
        raise web.HTTPBadRequest(text="CallSid is required")
    if payload.get("Direction", "inbound") != "inbound":
        raise web.HTTPForbidden(text="Only inbound calls are accepted")
    if to_number != str(runtime.entry.data[CONF_DID]):
        raise web.HTTPForbidden(text="Unexpected destination number")

    stage = request.query.get("stage", "incoming")
    if stage == "incoming":
        if from_number != str(runtime.entry.data[CONF_BUZZER_NUMBER]):
            interaction_id = uuid4().hex
            await runtime.async_record(
                interaction_id=interaction_id,
                kind="voice",
                from_number=from_number,
                to_number=to_number,
                call_sid=call_sid,
                status="fallback",
                action="unknown_caller_bridge",
            )
            return runtime.fallback_twiml()

        interaction_id = uuid4().hex
        if runtime.store.state.auto_unlock:
            try:
                action = await runtime.async_run_unlock(
                    {
                        "call_sid": call_sid,
                        "interaction_id": interaction_id,
                        "from_number": from_number,
                        "to_number": to_number,
                        "transcript": "",
                    }
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.exception("Automatic unlock failed")
                await runtime.async_record(
                    interaction_id=interaction_id,
                    kind="buzzer",
                    from_number=from_number,
                    to_number=to_number,
                    call_sid=call_sid,
                    status="fallback",
                    action="auto_unlock_error_bridge",
                    detail=str(err),
                )
                return runtime.fallback_twiml()
            await runtime.async_record(
                interaction_id=interaction_id,
                kind="buzzer",
                from_number=from_number,
                to_number=to_number,
                call_sid=call_sid,
                status="accepted",
                action=action,
                detail="Automatically accepted because auto-unlock was enabled.",
            )
            if action.startswith("script:"):
                return response(say("Access has been granted."), hangup())
            return runtime.unlock_twiml()

        await runtime.async_record(
            interaction_id=interaction_id,
            kind="buzzer",
            from_number=from_number,
            to_number=to_number,
            call_sid=call_sid,
            status="gathering_speech",
        )
        prompt = str(runtime.option(CONF_SPEECH_PROMPT, DEFAULT_SPEECH_PROMPT))
        return response(
            gather_speech(
                prompt,
                f"{runtime.webhook_url_for('speech')}&interaction_id={interaction_id}",
            )
        )

    interaction_id = request.query.get("interaction_id", "")
    if not interaction_id:
        raise web.HTTPBadRequest(text="interaction_id is required")

    if stage == "speech":
        transcript = payload.get("SpeechResult", "").strip()
        if not transcript:
            await runtime.async_update_interaction(interaction_id, status="no_speech")
            return response(say("We did not hear a response."), hangup())
        await runtime.async_begin_decision(
            call_sid=call_sid,
            interaction_id=interaction_id,
            from_number=from_number,
            to_number=to_number,
            transcript=transcript,
        )
        timeout = int(runtime.option(CONF_RESPONSE_TIMEOUT, DEFAULT_RESPONSE_TIMEOUT))
        return response(
            wait_for_decision(
                timeout,
                f"{runtime.webhook_url_for('timeout')}&interaction_id={interaction_id}",
            )
        )

    if stage == "timeout":
        if call_sid not in runtime.active_calls:
            await runtime.async_update_interaction(
                interaction_id,
                status="fallback",
                action="bridged_after_restart",
            )
            return runtime.fallback_twiml()
        if await runtime.async_timeout_call(call_sid):
            return runtime.fallback_twiml()
        return response(hangup())

    raise web.HTTPBadRequest(text="Unknown webhook stage")


async def _async_handle_sms(runtime: TelethonkRuntime, payload: dict[str, str]) -> str:
    """Record and acknowledge an inbound SMS."""
    from_number = payload.get("From", "")
    to_number = payload.get("To", "")
    if to_number != str(runtime.entry.data[CONF_DID]):
        raise web.HTTPForbidden(text="Unexpected destination number")
    interaction_id = uuid4().hex
    body = payload.get("Body", "").strip()
    await runtime.async_record(
        interaction_id=interaction_id,
        kind="sms",
        from_number=from_number,
        to_number=to_number,
        status="received",
        transcript=body,
        action="home_assistant_event",
    )
    runtime.hass.bus.async_fire(
        EVENT_INBOUND_SMS,
        {
            "entry_id": runtime.entry.entry_id,
            "interaction_id": interaction_id,
            "from": from_number,
            "to": to_number,
            "body": body,
        },
    )
    acknowledgement = str(
        runtime.option(CONF_SMS_ACKNOWLEDGEMENT, DEFAULT_SMS_ACKNOWLEDGEMENT) or ""
    )
    if not acknowledgement:
        return response()
    return response(message(acknowledgement))
