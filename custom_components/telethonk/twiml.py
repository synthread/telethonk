"""Small, deterministic TwiML response builders."""

from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr


def response(*verbs: str) -> str:
    """Wrap TwiML verbs in a response document."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?><Response>'
        + "".join(verbs)
        + "</Response>"
    )


def say(text: str) -> str:
    """Build a Say verb."""
    return f"<Say>{escape(text)}</Say>"


def message(text: str) -> str:
    """Build an SMS Message verb."""
    return f"<Message>{escape(text)}</Message>"


def hangup() -> str:
    """Build a Hangup verb."""
    return "<Hangup/>"


def play_digits(digits: str) -> str:
    """Build a Play verb that sends DTMF digits."""
    return f"<Play digits={quoteattr(digits)}/>"


def gather_speech(prompt: str, action_url: str) -> str:
    """Ask the caller a question and collect a speech result."""
    return (
        '<Gather input="speech" speechTimeout="auto" '
        f'action={quoteattr(action_url)} method="POST">'
        f"{say(prompt)}</Gather>"
        f"{say('We did not hear a response.')}{hangup()}"
    )


def wait_for_decision(timeout: int, timeout_url: str) -> str:
    """Keep the call alive until an action or timeout response wins."""
    return (
        f"{say('Please wait while we contact the residents.')}"
        f"<Pause length={quoteattr(str(timeout))}/>"
        f'<Redirect method="POST">{escape(timeout_url)}</Redirect>'
    )


def dial_numbers(numbers: list[str]) -> str:
    """Dial several fallback recipients simultaneously."""
    children = "".join(f"<Number>{escape(number)}</Number>" for number in numbers)
    return f'<Dial answerOnBridge="true" timeout="25">{children}</Dial>'
