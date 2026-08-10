"""Persistent cookie cache so valid sessions can be reused across runs."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SessionCacheStats:
    """Per-site session-cache reuse counters for observability.

    Intended for single-threaded use inside one adapter instance; use
    :meth:`bump` to produce updated copies and :meth:`merge` to aggregate
    per-site stats in the runner.
    """

    restored: int = 0
    rejected: int = 0
    saved: int = 0

    def bump(
        self,
        *,
        restored: int = 0,
        rejected: int = 0,
        saved: int = 0,
    ) -> "SessionCacheStats":
        return SessionCacheStats(
            restored=self.restored + restored,
            rejected=self.rejected + rejected,
            saved=self.saved + saved,
        )

    @classmethod
    def merge(cls, *stats: "SessionCacheStats") -> "SessionCacheStats":
        return cls(
            restored=sum(item.restored for item in stats),
            rejected=sum(item.rejected for item in stats),
            saved=sum(item.saved for item in stats),
        )


def session_path(session_dir: Path, site_name: str, username: str) -> Path:
    digest = hashlib.md5(username.encode("utf-8")).hexdigest()
    return session_dir / f"{site_name}_{digest}.json"


def load_cookies(
    session_dir: Path,
    site_name: str,
    username: str,
    max_age_seconds: float = 0.0,
) -> dict[str, str]:
    path = session_path(session_dir, site_name, username)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        saved_at = float(data.get("saved_at", 0) or 0)
        if max_age_seconds > 0 and saved_at and (time.time() - saved_at) > max_age_seconds:
            return {}
        return {str(key): str(value) for key, value in data.get("cookies", {}).items()}
    except Exception:
        return {}


def save_cookies(
    session_dir: Path,
    site_name: str,
    username: str,
    cookies: dict[str, str],
) -> None:
    path = session_path(session_dir, site_name, username)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"saved_at": time.time(), "cookies": cookies}, ensure_ascii=False),
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    os.chmod(path, 0o600)
