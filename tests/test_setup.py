"""Integration setup tests against the supported Home Assistant release."""

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.telethonk.const import (
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
    CONF_WEBHOOK_ID,
    DOMAIN,
)
from custom_components.telethonk.panel import DATA_PANEL_REGISTERED, DATA_RUNTIMES


async def test_setup_and_unload_entry(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    """A configured receptionist loads its webhook, switch, and panel."""
    hass.config.external_url = "https://ha.example"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Receptionist +16045550100",
        unique_id="+16045550100",
        data={
            CONF_ACCOUNT_SID: "AC00000000000000000000000000000000",
            CONF_AUTH_TOKEN: "secret",
            CONF_DID: "+16045550100",
            CONF_BUZZER_NUMBER: "+16045550200",
            CONF_WEBHOOK_ID: "private-webhook-id",
        },
        options={
            CONF_NOTIFICATION_RECIPIENTS: "mobile_app_kai",
            CONF_FALLBACK_NUMBERS: "+16045550300",
            CONF_RESPONSE_TIMEOUT: 20,
            CONF_UNLOCK_DIGITS: "w666",
            CONF_SPEECH_PROMPT: "Who is at the door?",
            CONF_SMS_ACKNOWLEDGEMENT: "Thank you.",
            CONF_RETENTION_DAYS: 30,
            CONF_SHOW_SIDEBAR: True,
        },
    )
    entry.add_to_hass(hass)

    with patch("custom_components.telethonk.storage.ReceptionistStore.async_load"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.entry_id in hass.data[DOMAIN][DATA_RUNTIMES]
    assert hass.data[DOMAIN][DATA_PANEL_REGISTERED] is True
    registry = er.async_get(hass)
    entity = registry.async_get_entity_id(
        "switch", DOMAIN, f"{entry.entry_id}_auto_unlock"
    )
    assert entity is not None
    assert hass.states.get(entity).state == "off"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.entry_id not in hass.data[DOMAIN][DATA_RUNTIMES]
