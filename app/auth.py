"""Signed browser sessions checked against current account access."""

import base64
import hashlib
import hmac
import time

from app.config import Settings
from app.users import get_user

SESSION_COOKIE = "quality_lifecycle_session"


def issue_browser_session(username: str, settings: Settings) -> str:
    expires = int(time.time()) + settings.session_ttl_seconds
    encoded_user = base64.urlsafe_b64encode(username.encode()).decode().rstrip("=")
    user = get_user(settings, username)
    version = user["version"] if user else -1
    payload = f"{encoded_user}.{expires}.{version}"
    signature = hmac.new(
        settings.session_secret_value.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    return f"{payload}.{signature}"


def session_username(value: str, settings: Settings) -> str | None:
    if not value or not settings.browser_login_enabled:
        return None
    try:
        fields = value.split(".")
        if len(fields) == 3:
            encoded_user, expires_text, supplied_signature = fields
            version = "0"
        else:
            encoded_user, expires_text, version, supplied_signature = fields
        expires = int(expires_text)
        username = base64.urlsafe_b64decode(encoded_user + "=" * (-len(encoded_user) % 4)).decode()
    except (ValueError, UnicodeError):
        return None
    if expires < int(time.time()):
        return None
    payload = value.rsplit(".", 1)[0]
    expected = hmac.new(
        settings.session_secret_value.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(supplied_signature.encode(), expected.encode()):
        return None
    user = get_user(settings, username)
    if not user or not user["enabled"] or str(user["version"]) != version:
        return None
    return str(user["username"])


def valid_session(value: str, settings: Settings) -> bool:
    return session_username(value, settings) is not None
