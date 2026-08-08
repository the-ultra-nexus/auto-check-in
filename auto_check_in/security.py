"""Credential redaction helpers."""

from __future__ import annotations

import re

_SENSITIVE_COOKIE_RE = re.compile(
    r"(?i)((?:cf_clearance|[A-Za-z0-9]+_auth|auth))=[^;\s\"'&]+"
)
_HEX_TOKEN_RE = re.compile(r"\b[0-9a-f]{24,}\b")


def redact_text(text: str) -> str:
    """Mask known credential patterns so results and logs stay safe."""
    if not text:
        return text
    redacted = _SENSITIVE_COOKIE_RE.sub(r"\1=***", text)
    redacted = _HEX_TOKEN_RE.sub("***", redacted)
    return redacted
