# Telethonk Receptionist

Telethonk is a Home Assistant-native Twilio receptionist. It accepts signed
inbound Twilio webhooks, handles a building buzzer workflow, exposes a
persistent auto-unlock switch, and keeps a local interaction journal in an
admin-only Home Assistant sidebar panel.

## Features

- UI configuration for Twilio credentials, the active DID, and the recognized
  buzzer caller number.
- A native `switch.telethonk_receptionist_auto_unlock` entity that remains
  available in dashboards and the Home Assistant mobile app.
- Automatic DTMF unlock or an optional Home Assistant script override.
- Speech gathering and actionable Accept/Deny mobile notifications.
- Configurable decision timeout followed by simultaneous call bridging to
  fallback phone numbers.
- General inbound-call fallback routing and inbound SMS events.
- An admin-only **Receptionist** sidebar panel with profile status and a
  retained transcript/action journal.
- Twilio signature validation using the exact externally configured webhook
  URL.

## Install with HACS

1. In HACS, add `https://github.com/synthread/telethonk` as a custom
   **Integration** repository.
2. Download **Telethonk Receptionist** and restart Home Assistant.
3. Go to **Settings > Devices & services > Add integration**, search for
   **Telethonk Receptionist**, and enter your Twilio credentials and phone
   numbers.
4. Open the integration's **Configure** dialog to set mobile notification
   recipients, fallback phone numbers, timeout, unlock digits or script, and
   retention.
5. Copy the webhook URL shown on the Receptionist page to both the **A call
   comes in** and **A message comes in** settings for the Twilio DID. Use
   `HTTP POST`.

Home Assistant must have a correct externally reachable HTTPS URL. Twilio
signs the complete public URL, so a mismatched internal URL, reverse-proxy URL,
or query string causes the request to be rejected.

## Door workflow

When the configured buzzer number calls:

1. If auto-unlock is enabled, Telethonk immediately runs the configured unlock
   script or plays the configured DTMF digits into the call.
2. Otherwise, Twilio asks who is at the door and sends the transcript to each
   configured Home Assistant mobile notification service.
3. **Accept** unlocks and ends the live call. **Deny** refuses and ends it.
4. If nobody responds before the configured timeout, Twilio rings all fallback
   phone numbers simultaneously and bridges the first answer.

Other inbound callers are bridged to the same fallback group immediately,
providing a base for broader receptionist routing in future releases.

## Script override

The optional script replaces Twilio DTMF and receives these variables:

- `call_sid`
- `interaction_id`
- `from_number`
- `to_number`
- `transcript`

The integration waits for the Home Assistant script service call to complete
before confirming access.

## Events

- `telethonk_interaction` is fired whenever a new journal item is created.
- `telethonk_inbound_sms` contains `entry_id`, `interaction_id`, `from`, `to`,
  and `body`.
- `telethonk_updated` indicates panel-visible state changed.

## Privacy and recovery

Transcripts and action history are stored only in Home Assistant's integration
storage, bounded to 500 records and the configured retention window. Diagnostic
downloads redact Twilio credentials, webhook IDs, phone numbers, call IDs, and
transcripts. Auto-unlock defaults off on a new installation.

If Home Assistant is unavailable, Twilio cannot reach this integration. Keep a
Twilio number-level fallback or recovery procedure appropriate to your
household.

## Development

```console
uv sync
uv run ruff check .
uv run pytest
```

Releases attach `telethonk.zip`, containing the contents of
`custom_components/telethonk/`, for deterministic HACS installation.

