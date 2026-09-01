"""Small stateless browser-session boundary for the application UI."""

import base64
import hashlib
import hmac
import time

from app.config import Settings

SESSION_COOKIE = "quality_lifecycle_session"


def issue_browser_session(username: str, settings: Settings) -> str:
    expires = int(time.time()) + settings.session_ttl_seconds
    encoded_user = base64.urlsafe_b64encode(username.encode()).decode().rstrip("=")
    payload = f"{encoded_user}.{expires}"
    signature = hmac.new(
        settings.session_secret_value.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    return f"{payload}.{signature}"


def valid_session(value: str, settings: Settings) -> bool:
    if not value or not settings.browser_login_enabled:
        return False
    try:
        encoded_user, expires_text, supplied_signature = value.split(".", 2)
        expires = int(expires_text)
        username = base64.urlsafe_b64decode(encoded_user + "=" * (-len(encoded_user) % 4)).decode()
    except (ValueError, UnicodeError):
        return False
    if expires < int(time.time()) or not hmac.compare_digest(username, settings.app_username):
        return False
    payload = f"{encoded_user}.{expires_text}"
    expected = hmac.new(
        settings.session_secret_value.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(supplied_signature, expected)
