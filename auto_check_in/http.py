"""Shared HTTP client helpers (user-agent pool and headers)."""

from __future__ import annotations

import random
from typing import Any

from .config import NetworkConfig

USER_AGENTS = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:128.0) Gecko/20100101 Firefox/128.0",
)


def random_user_agent() -> str:
    """Pick a random user agent from the shared pool."""
    return random.choice(USER_AGENTS)


def ua_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Request headers with a freshly randomized user agent."""
    headers = {"User-Agent": random_user_agent()}
    if extra:
        headers.update(extra)
    return headers


class SessionProvider:
    """Creates HTTP sessions with shared UA/timeout defaults."""

    def __init__(self, network: NetworkConfig):
        self.network = network

    def new_session(self) -> Any:
        import requests

        session = requests.Session()
        session.headers.update({"User-Agent": random_user_agent()})
        return session
