"""Constants for the Telethonk integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "telethonk"
NAME = "Telethonk Receptionist"
VERSION = "0.1.0"

PLATFORMS = ["switch"]

CONF_ACCOUNT_SID = "account_sid"
CONF_AUTH_TOKEN = "auth_token"
CONF_DID = "did"
CONF_BUZZER_NUMBER = "buzzer_number"
CONF_WEBHOOK_ID = "webhook_id"

CONF_NOTIFICATION_RECIPIENTS = "notification_recipients"
CONF_RESPONSE_TIMEOUT = "response_timeout"
CONF_FALLBACK_NUMBERS = "fallback_numbers"
CONF_UNLOCK_DIGITS = "unlock_digits"
CONF_UNLOCK_SCRIPT = "unlock_script"
CONF_SPEECH_PROMPT = "speech_prompt"
CONF_SHOW_SIDEBAR = "show_sidebar"
CONF_RETENTION_DAYS = "retention_days"
CONF_SMS_ACKNOWLEDGEMENT = "sms_acknowledgement"

DEFAULT_RESPONSE_TIMEOUT = 20
MIN_RESPONSE_TIMEOUT = 5
MAX_RESPONSE_TIMEOUT = 60
DEFAULT_UNLOCK_DIGITS = "w666"
DEFAULT_SPEECH_PROMPT = "Who is at the door?"
DEFAULT_RETENTION_DAYS = 30
DEFAULT_SMS_ACKNOWLEDGEMENT = "Thank you. Your message has been received."
DEFAULT_SHOW_SIDEBAR = True

WEBHOOK_NAME = "Telethonk Receptionist"
PANEL_URL = "telethonk"
PANEL_TITLE = "Receptionist"
PANEL_ICON = "mdi:desk"
PANEL_MODULE_URL = "/telethonk_static/telethonk-panel.js"
PANEL_STATIC_URL = "/telethonk_static"

STORAGE_VERSION = 1
MAX_INTERACTIONS = 500
ACTIVE_CALL_TTL = timedelta(minutes=10)

EVENT_UPDATED = f"{DOMAIN}_updated"
EVENT_INTERACTION = f"{DOMAIN}_interaction"
EVENT_INBOUND_SMS = f"{DOMAIN}_inbound_sms"
EVENT_NOTIFICATION_ACTION = "mobile_app_notification_action"

ACTION_ACCEPT_PREFIX = f"{DOMAIN}_accept_"
ACTION_DENY_PREFIX = f"{DOMAIN}_deny_"

ATTRIBUTION = "Powered by Twilio"
