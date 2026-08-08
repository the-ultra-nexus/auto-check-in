"""Credential redaction helpers."""

from __future__ import annotations

import re

_SENSITIVE_COOKIE_RE = re.compile(
    r"(?i)((?:cf_clearance|[A-Za-z0-9]+_auth|auth))=[^;\s\"'&]+"
)
_HEX_TOKEN_RE = re.compile(r"\b[0-9a-f]{24,}\b")
_PROXY_USERINFO_RE = re.compile(r"(?i)([A-Za-z][A-Za-z0-9+.-]*://)([^/@\s]+@)")


def mask_username(username: str) -> str:
    """Render a username for logs/results without exposing the full value."""
    if not username:
        return ""
    if len(username) <= 1:
        return "*"
    if len(username) <= 4:
        return f"{username[0]}***"
    return f"{username[:2]}***{username[-1]}"


def redact_text(text: str) -> str:
    """Mask known credential patterns so results and logs stay safe."""
    if not text:
        return text
    redacted = _SENSITIVE_COOKIE_RE.sub(r"\1=***", text)
    redacted = _HEX_TOKEN_RE.sub("***", redacted)
    redacted = _PROXY_USERINFO_RE.sub(r"\1***@", redacted)
    return redacted
