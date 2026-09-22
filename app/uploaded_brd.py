"""Short-lived proof that workflow requirements came from server-extracted BRD text."""

import hashlib
import hmac
import secrets
import time

from app.config import Settings

_PROCESS_KEY = secrets.token_bytes(32)
_RECEIPT_SECONDS = 8 * 60 * 60


def _key(settings: Settings) -> bytes:
    configured = settings.session_secret_value or settings.api_auth_token_value
    return configured.encode() if configured else _PROCESS_KEY


def issue_brd_receipt(text: str, settings: Settings) -> str:
    expires = int(time.time()) + _RECEIPT_SECONDS
    digest = hashlib.sha256(text.encode()).hexdigest()
    payload = f"{expires}.{digest}"
    signature = hmac.new(_key(settings), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def verify_brd_receipt(text: str, receipt: str, settings: Settings) -> bool:
    parts = receipt.split(".")
    if len(parts) != 3 or not parts[0].isdigit():
        return False
    expires, digest, signature = parts
    if int(expires) < int(time.time()) or int(expires) > int(time.time()) + _RECEIPT_SECONDS:
        return False
    if not hmac.compare_digest(digest, hashlib.sha256(text.encode()).hexdigest()):
        return False
    expected = hmac.new(_key(settings), f"{expires}.{digest}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)
