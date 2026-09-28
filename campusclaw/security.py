from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any


PBKDF2_ITERATIONS = 210_000
HASH_ALGORITHM = "sha256"


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    if not password:
        raise ValueError("password must not be empty")
    actual_salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        HASH_ALGORITHM,
        password.encode("utf-8"),
        actual_salt,
        PBKDF2_ITERATIONS,
    )
    salt_text = base64.urlsafe_b64encode(actual_salt).decode("ascii")
    digest_text = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"pbkdf2_{HASH_ALGORITHM}${PBKDF2_ITERATIONS}${salt_text}${digest_text}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, iterations_text, salt_text, expected_text = password_hash.split("$", 3)
        if scheme != f"pbkdf2_{HASH_ALGORITHM}":
            return False
        iterations = int(iterations_text)
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(expected_text.encode("ascii"))
    except (ValueError, TypeError):
        return False

    actual = hashlib.pbkdf2_hmac(
        HASH_ALGORITHM,
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)


def _b64_json(data: dict[str, Any]) -> str:
    raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_b64_json(value: str) -> dict[str, Any]:
    padded = value + "=" * (-len(value) % 4)
    raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    decoded = json.loads(raw.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("session payload must be an object")
    return decoded


def sign_session(user: dict[str, Any], secret_key: str, *, ttl_seconds: int = 86_400) -> str:
    payload = {
        "user_id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "class_id": user["class_id"],
        "exp": int(time.time()) + ttl_seconds,
    }
    payload_text = _b64_json(payload)
    signature = hmac.new(
        secret_key.encode("utf-8"),
        payload_text.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload_text}.{signature}"


def verify_session(token: str | None, secret_key: str | None) -> dict[str, Any] | None:
    if not token or not secret_key or "." not in token:
        return None
    payload_text, supplied_signature = token.rsplit(".", 1)
    expected_signature = hmac.new(
        secret_key.encode("utf-8"),
        payload_text.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        return None
    try:
        payload = _decode_b64_json(payload_text)
    except (ValueError, json.JSONDecodeError):
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload
