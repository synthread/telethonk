"""UI configuration for Telethonk."""

from __future__ import annotations

import re
import secrets
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from twilio.base.exceptions import TwilioException
from twilio.rest import Client

from .const import (
    CONF_ACCOUNT_SID,
    CONF_AUTH_TOKEN,
    CONF_BUZZER_NUMBER,
    CONF_DID,
    CONF_FALLBACK_NUMBERS,
    CONF_NOTIFICATION_RECIPIENTS,
    CONF_RESPONSE_TIMEOUT,
    CONF_RETENTION_DAYS,
    CONF_SHOW_SIDEBAR,
    CONF_SMS_ACKNOWLEDGEMENT,
    CONF_SPEECH_PROMPT,
    CONF_UNLOCK_DIGITS,
    CONF_UNLOCK_SCRIPT,
    CONF_WEBHOOK_ID,
    DEFAULT_RESPONSE_TIMEOUT,
    DEFAULT_RETENTION_DAYS,
    DEFAULT_SHOW_SIDEBAR,
    DEFAULT_SMS_ACKNOWLEDGEMENT,
    DEFAULT_SPEECH_PROMPT,
    DEFAULT_UNLOCK_DIGITS,
    DOMAIN,
    MAX_RESPONSE_TIMEOUT,
    MIN_RESPONSE_TIMEOUT,
)


async def _async_validate_credentials(
    hass: HomeAssistant, account_sid: str, auth_token: str
) -> None:
    """Validate Twilio credentials without retaining an API result."""

    def _validate() -> None:
        Client(account_sid, auth_token).api.accounts(account_sid).fetch()

    await hass.async_add_executor_job(_validate)


def _normalise_e164(value: str) -> str:
    """Normalise common phone-number formatting to strict E.164."""
    value = re.sub(r"[\s().-]", "", value)
    if not re.fullmatch(r"\+[1-9]\d{6,14}", value):
        raise vol.Invalid("Phone numbers must use E.164 format, such as +16045551234")
    return value


def _user_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_ACCOUNT_SID, default=defaults.get(CONF_ACCOUNT_SID, "")
            ): str,
            vol.Required(
                CONF_AUTH_TOKEN, default=defaults.get(CONF_AUTH_TOKEN, "")
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_DID, default=defaults.get(CONF_DID, "")): str,
            vol.Required(
                CONF_BUZZER_NUMBER, default=defaults.get(CONF_BUZZER_NUMBER, "")
            ): str,
        }
    )


def _options_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_NOTIFICATION_RECIPIENTS,
                default=defaults.get(CONF_NOTIFICATION_RECIPIENTS, ""),
            ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
            vol.Required(
                CONF_FALLBACK_NUMBERS,
                default=defaults.get(CONF_FALLBACK_NUMBERS, ""),
            ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
            vol.Required(
                CONF_RESPONSE_TIMEOUT,
                default=defaults.get(CONF_RESPONSE_TIMEOUT, DEFAULT_RESPONSE_TIMEOUT),
            ): vol.All(
                vol.Coerce(int),
                vol.Range(min=MIN_RESPONSE_TIMEOUT, max=MAX_RESPONSE_TIMEOUT),
            ),
            vol.Required(
                CONF_UNLOCK_DIGITS,
                default=defaults.get(CONF_UNLOCK_DIGITS, DEFAULT_UNLOCK_DIGITS),
            ): str,
            vol.Optional(
                CONF_UNLOCK_SCRIPT,
                description={"suggested_value": defaults.get(CONF_UNLOCK_SCRIPT)},
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="script")),
            vol.Required(
                CONF_SPEECH_PROMPT,
                default=defaults.get(CONF_SPEECH_PROMPT, DEFAULT_SPEECH_PROMPT),
            ): str,
            vol.Required(
                CONF_SMS_ACKNOWLEDGEMENT,
                default=defaults.get(
                    CONF_SMS_ACKNOWLEDGEMENT, DEFAULT_SMS_ACKNOWLEDGEMENT
                ),
            ): str,
            vol.Required(
                CONF_RETENTION_DAYS,
                default=defaults.get(CONF_RETENTION_DAYS, DEFAULT_RETENTION_DAYS),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=365)),
            vol.Required(
                CONF_SHOW_SIDEBAR,
                default=defaults.get(CONF_SHOW_SIDEBAR, DEFAULT_SHOW_SIDEBAR),
            ): bool,
        }
    )


def _normalise_options(user_input: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalise receptionist options."""
    fallback = [
        _normalise_e164(number.strip())
        for number in re.split(r"[,\n]", user_input[CONF_FALLBACK_NUMBERS])
        if number.strip()
    ]
    recipients = [
        value.strip().removeprefix("notify.")
        for value in re.split(r"[,\n]", user_input[CONF_NOTIFICATION_RECIPIENTS])
        if value.strip()
    ]
    if not fallback or not recipients:
        raise vol.Invalid(
            "At least one notification recipient and fallback number are required"
        )
    user_input[CONF_FALLBACK_NUMBERS] = "\n".join(fallback)
    user_input[CONF_NOTIFICATION_RECIPIENTS] = "\n".join(recipients)
    return user_input


class TelethonkConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a Telethonk receptionist."""

    VERSION = 1
    _pending_data: dict[str, Any]

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Create an integration entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                user_input[CONF_DID] = _normalise_e164(user_input[CONF_DID])
                user_input[CONF_BUZZER_NUMBER] = _normalise_e164(
                    user_input[CONF_BUZZER_NUMBER]
                )
                await _async_validate_credentials(
                    self.hass,
                    user_input[CONF_ACCOUNT_SID],
                    user_input[CONF_AUTH_TOKEN],
                )
            except vol.Invalid:
                errors["base"] = "invalid_phone_number"
            except TwilioException:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(user_input[CONF_DID])
                self._abort_if_unique_id_configured()
                user_input[CONF_WEBHOOK_ID] = secrets.token_urlsafe(32)
                self._pending_data = user_input
                return await self.async_step_receptionist()
        return self.async_show_form(
            step_id="user", data_schema=_user_schema(user_input), errors=errors
        )

    async def async_step_receptionist(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure routing and behaviour before creating the entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                options = _normalise_options(user_input)
            except vol.Invalid:
                errors["base"] = "invalid_options"
            else:
                did = self._pending_data[CONF_DID]
                return self.async_create_entry(
                    title=f"Receptionist {did}",
                    data=self._pending_data,
                    options=options,
                )
        return self.async_show_form(
            step_id="receptionist",
            data_schema=_options_schema(user_input or {}),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Update credentials and routing identifiers."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                user_input[CONF_DID] = _normalise_e164(user_input[CONF_DID])
                user_input[CONF_BUZZER_NUMBER] = _normalise_e164(
                    user_input[CONF_BUZZER_NUMBER]
                )
                await _async_validate_credentials(
                    self.hass,
                    user_input[CONF_ACCOUNT_SID],
                    user_input[CONF_AUTH_TOKEN],
                )
            except vol.Invalid:
                errors["base"] = "invalid_phone_number"
            except TwilioException:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(user_input[CONF_DID])
                self._abort_if_unique_id_mismatch()
                user_input[CONF_WEBHOOK_ID] = entry.data[CONF_WEBHOOK_ID]
                return self.async_update_reload_and_abort(
                    entry,
                    data=user_input,
                    title=f"Receptionist {user_input[CONF_DID]}",
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_user_schema(user_input or dict(entry.data)),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow."""
        return TelethonkOptionsFlow()


class TelethonkOptionsFlow(config_entries.OptionsFlow):
    """Manage receptionist behaviour."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Update behavioural options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                options = _normalise_options(user_input)
            except vol.Invalid:
                errors["base"] = "invalid_options"
            else:
                return self.async_create_entry(title="", data=options)
        defaults = dict(self.config_entry.options)
        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(user_input or defaults),
            errors=errors,
        )
