"""Tests for config validation helpers."""

import pytest
import voluptuous as vol

from custom_components.telethonk.config_flow import (
    _normalise_e164,
    _normalise_options,
)
from custom_components.telethonk.const import (
    CONF_FALLBACK_NUMBERS,
    CONF_NOTIFICATION_RECIPIENTS,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("+16045551234", "+16045551234"),
        ("+1 (604) 555-1234", "+16045551234"),
        ("+44 20 7946 0958", "+442079460958"),
    ],
)
def test_normalise_e164(value: str, expected: str) -> None:
    """Formatting is removed while E.164 semantics are retained."""
    assert _normalise_e164(value) == expected


@pytest.mark.parametrize("value", ["6045551234", "+01234", "+1", "not-a-phone"])
def test_normalise_e164_rejects_invalid(value: str) -> None:
    """Ambiguous or invalid phone numbers are rejected."""
    with pytest.raises(vol.Invalid):
        _normalise_e164(value)


def test_normalise_options() -> None:
    """Recipients and fallback destinations are normalized for runtime use."""
    options = _normalise_options(
        {
            CONF_NOTIFICATION_RECIPIENTS: "notify.mobile_app_kai\nmobile_app_house",
            CONF_FALLBACK_NUMBERS: "+1 (604) 555-1234,\n+16045555678",
        }
    )
    assert options[CONF_NOTIFICATION_RECIPIENTS] == ("mobile_app_kai\nmobile_app_house")
    assert options[CONF_FALLBACK_NUMBERS] == "+16045551234\n+16045555678"


@pytest.mark.parametrize(
    ("recipients", "fallback"),
    [("", "+16045551234"), ("mobile_app_kai", "")],
)
def test_normalise_options_requires_routing(recipients: str, fallback: str) -> None:
    """A receptionist must have both an action target and a call fallback."""
    with pytest.raises(vol.Invalid):
        _normalise_options(
            {
                CONF_NOTIFICATION_RECIPIENTS: recipients,
                CONF_FALLBACK_NUMBERS: fallback,
            }
        )
