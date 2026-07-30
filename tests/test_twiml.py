"""Tests for deterministic TwiML builders."""

from xml.etree import ElementTree

from custom_components.telethonk.twiml import (
    dial_numbers,
    gather_speech,
    message,
    play_digits,
    response,
    wait_for_decision,
)


def test_response_escapes_values() -> None:
    """Untrusted values are escaped before insertion into XML."""
    play = ElementTree.fromstring(play_digits('w6"6'))
    assert play.attrib["digits"] == 'w6"6'
    assert (
        dial_numbers(["+16045550100", "+1604555<0200"])
        == '<Dial answerOnBridge="true" timeout="25">'
        "<Number>+16045550100</Number><Number>+1604555&lt;0200</Number></Dial>"
    )


def test_gather_uses_absolute_action() -> None:
    """Speech gathering posts to the supplied absolute stage URL."""
    xml = response(
        gather_speech(
            "Who is there?",
            "https://ha.example/api/webhook/private?stage=speech&id=one",
        )
    )
    assert 'input="speech"' in xml
    assert "https://ha.example/api/webhook/private?stage=speech&amp;id=one" in xml
    assert "<Say>Who is there?</Say>" in xml


def test_wait_redirects_after_timeout() -> None:
    """The response remains live before redirecting to fallback."""
    xml = response(
        wait_for_decision(20, "https://ha.example/api/webhook/private?stage=timeout")
    )
    assert '<Pause length="20"/>' in xml
    assert "<Redirect" in xml
    assert "stage=timeout" in xml


def test_sms_message_escapes_content() -> None:
    """Inbound acknowledgement content cannot break TwiML."""
    assert message("Thanks <3") == "<Message>Thanks &lt;3</Message>"
